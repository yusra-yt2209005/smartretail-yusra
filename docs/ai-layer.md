# SmartRetail AI Layer

## Embeddings and Vector Similarity

Traditional keyword search mainly depends on matching words in the
customer's query with words stored in the product catalog. This can miss
relevant products when the same idea is expressed using different words.

For example, a customer may search for "a phone for taking good pictures",
while a product description may say that it has a "48MP camera". The
phrases are different, but they have similar meaning.

An embedding is a numerical representation of text. An embedding model
takes text as input and converts it into a fixed-length vector, which is a
list of numbers. The individual numbers are not meaningful on their own.
Instead, the vector as a whole represents characteristics of the text.

Texts with similar meanings should have vectors that are closer together
than texts about unrelated subjects.

SmartRetail embeds both product content and the customer's search query
using the same embedding provider. Product vectors are stored in
PostgreSQL using pgvector. When a customer searches, the query is also
converted into a vector and compared with the stored product vectors.

SmartRetail uses cosine distance for retrieval. A smaller cosine distance
means two vectors are closer together. The search service converts this
into a similarity score using:

    similarity = 1 - cosine_distance

A higher similarity therefore represents a stronger match between the
customer query and the product.

This allows SmartRetail to move beyond exact keyword matching and perform
semantic product retrieval.


## Chunking Strategy

SmartRetail uses one enriched semantic chunk per product rather than
splitting product text at a fixed number of characters.

Each chunk combines:

- product title
- category
- variant attributes/specifications
- product description

For example, an indexed laptop chunk may look like:

    Title: M2 Lenovo ThinkPad Laptop
    Category: Laptops
    Specifications: brand: Lenovo, memory: 16GB,
    processor: Intel Core i7, storage: 512GB SSD
    Description: Professional business laptop with a fast processor
    and lightweight design.

Attributes such as brand, storage, connector type, memory, camera
specifications, or colour are included because customers may search for
these concepts even when they do not appear directly in the product
title.

Price, stock, availability and product status are deliberately excluded
from the semantic text. These values change frequently and are better
stored as retrieval metadata.

This separation is important because a price-only or stock-only change
does not change what the product means. SmartRetail can therefore update
the metadata without paying to generate the same embedding again.

This approach also avoids blind fixed-length character splitting, which
could separate the product name from the specifications or description
that provide its meaning.


## Embedding Provider

The AI layer uses an `EmbeddingProvider` interface rather than calling a
specific external provider directly.

The main operation is:

    embed_batch(texts: list[str]) -> list[list[float]]

This gives the application one common interface for both production and
testing.

Two implementations currently exist:

### OpenAIEmbeddingProvider

`OpenAIEmbeddingProvider` is the real implementation. It sends batches of
texts to the configured OpenAI embedding model and returns one vector per
input text.

The provider, model name and vector dimensions are configured through
environment settings rather than being hard-coded.

API keys are stored only in environment variables and are never committed
to the repository.

### FakeEmbeddings

`FakeEmbeddings` is a deterministic offline implementation used for tests
and local development.

It tokenizes the text and hashes meaningful tokens into vector positions.
The resulting vector is L2-normalized.

Because it is deterministic:

- the same text always produces the same vector
- tests do not require network access
- tests do not spend API credit
- retrieval tests are repeatable

The fake provider can recognize shared words, but it does not have the
same semantic understanding as a real embedding model. For example, it
may understand that two texts both contain "laptop", but it does not
reliably understand that "cheap" and "affordable" have similar meanings.


## Indexing Pipeline

Embedding is part of the existing Temporal product publishing workflow.

The Week 4 publishing flow is:

    validate product
        ->
    process media
        ->
    build enriched catalog text
        ->
    create/update content chunk
        ->
    generate embedding
        ->
    store vector and metadata
        ->
    mark product PUBLISHED

The embedding step runs inside a Temporal Activity.

This means provider failures can use Temporal's retry policy instead of
leaving the product partially published. The workflow status also exposes
the current `embedding` step while embedding is taking place.

A product is only marked `PUBLISHED` after the chunk and embedding stages
have completed successfully.


## Batched Embedding

The embedding interface accepts multiple texts at once.

Chunks are processed using a configurable batch size rather than making
one provider request for every chunk.

For example:

    batch size = 32

Batching reduces:

- HTTP round trips
- provider overhead
- latency when indexing many products/chunks
- the risk of unnecessarily expensive repeated API calls

Although SmartRetail currently creates one enriched chunk per product,
the Activity is implemented using batches so the design will still work
if the chunking strategy later produces multiple chunks.


## Vector Storage and Metadata

Vectors are stored directly in the existing PostgreSQL database using
pgvector.

The current vector dimension is:

    1536

Each `ContentChunk` stores:

- `product_id`
- `variant_id` when applicable
- `category_id`
- semantic text
- `text_hash`
- embedding vector
- price
- product status
- availability flag
- in-stock flag
- `embedded_at`

SmartRetail currently creates a product-level chunk, so `variant_id` may
be NULL because the vector represents the product rather than one
specific variant.

For product-level results, the search service returns the cheapest
currently active and in-stock variant as the representative buyable
variant and price.


## Re-Publishing and Re-Indexing

Published products can be published again after catalog changes.

This is necessary for changes such as:

- title or description edits
- variant attribute changes
- price changes
- stock changes

Re-publishing does not create duplicate vectors.

SmartRetail keeps one chunk with `chunk_index = 0` for the current
product-level chunk. Stale extra chunks are removed.

Each chunk also stores a SHA-256 `text_hash` of its semantic text.


### Semantic text changed

If the new hash differs from the stored hash:

    old text hash != new text hash
        ->
    semantic content changed
        ->
    old embedding is cleared
        ->
    embedding Activity generates a new vector

This prevents a vector generated from old product content from remaining
attached to newly edited text.


### Semantic text unchanged

If the hashes are identical:

    old text hash == new text hash
        ->
    semantic text unchanged
        ->
    existing embedding is kept
        ->
    only metadata is refreshed

For example, changing an iPhone price from:

    3199.99 -> 999.99

does not change its title, category, specifications or description.

During the test, the chunk kept the same:

- chunk ID
- text hash
- embedding timestamp

while its stored price changed.

This demonstrates that price-only updates do not unnecessarily regenerate
the embedding.


## Semantic Retrieval

SmartRetail exposes:

    POST /search

The request includes:

- natural-language query
- configurable `top_k`

The default value is:

    top_k = 5

The search flow is:

    customer query
        ->
    EmbeddingProvider
        ->
    query vector
        ->
    pgvector cosine-distance comparison
        ->
    correctness filters
        ->
    similarity threshold
        ->
    top-k results

Each returned item includes:

- product ID
- source variant ID
- title
- category ID
- price
- similarity score


## Buyability Filtering

Retrieval filtering is treated as a correctness requirement, not only a
ranking requirement.

Customer search only returns products that are currently buyable.

The SQL retrieval path checks:

    Product.status = PUBLISHED
    AND ContentChunk.status = published
    AND ContentChunk.available = true
    AND ContentChunk.in_stock = true
    AND ProductVariant.is_active = true
    AND ProductVariant.stock > 0
    AND embedding IS NOT NULL

The live `ProductVariant.stock` check is important.

For example, the vector metadata could say that a product was in stock
when it was indexed, but another customer could buy the final unit before
the vector metadata is refreshed.

Checking the live variant table ensures that stale index metadata cannot
cause an out-of-stock product to be recommended.


## Similarity Threshold

Nearest-neighbour search will always find the mathematically closest
vector, even if the query is unrelated to every product in the catalog.

SmartRetail therefore uses a minimum similarity threshold.

The current development value is:

    SEARCH_SIMILARITY_THRESHOLD = 0.10

Results below the threshold are discarded.

If no result passes both the buyability filters and similarity threshold,
the endpoint returns:

    {
      "items": [],
      "message": "No matching products found."
    }

This no-match outcome is intentional and is later used by the Week 5
assistant to avoid inventing products.


## Retrieval Evaluation

A small retrieval evaluation set was created with 10
query/expected-product pairs.

The script runs every query through the same `search_products()` service
used by the API and checks whether the expected product appears in the
top 5 results.

### Evaluation Results

| # | Query | Expected Product | Rank | Result |
|---|---|---|---:|---|
| 1 | Apple iPhone 16 phone | M2 Apple iPhone 16 | 1 | HIT |
| 2 | Apple USB-C charger | M2 Apple USB-C Charger | 1 | HIT |
| 3 | Dell Inspiron 14 laptop | M2 Dell Inspiron 14 Laptop | 1 | HIT |
| 4 | Google Pixel 9 phone | M2 Google Pixel 9 | 1 | HIT |
| 5 | Lenovo ThinkPad laptop | M2 Lenovo ThinkPad Laptop | 1 | HIT |
| 6 | Samsung fast charger | M2 Samsung Charger | 1 | HIT |
| 7 | Samsung Galaxy A56 phone | M2 Samsung Galaxy A56 | 1 | HIT |
| 8 | Samsung Galaxy S25 phone | M2 Samsung Galaxy S25 | 1 | HIT |
| 9 | USB-C fast charging cable | M2 USB-C Fast Charging Cable | 1 | HIT |
| 10 | Apple OLED 5G iPhone | M2 Apple iPhone 16 | 1 | HIT |

Summary:

    Evaluation queries: 10
    Hits: 10/10
    Top-5 hit rate: 100%
    Expected product ranked #1: 10/10

This evaluation currently uses `FakeEmbeddings`, so the strong result
mainly demonstrates correct indexing, vector comparison, filtering and
ranking for queries with meaningful lexical overlap.

A real embedding model is expected to perform better on queries involving
synonyms or different wording.


## Out-of-Stock Correctness Test

An indexed product was deliberately kept in the vector store while its
stock metadata indicated that it was sold out:

    M2 Logitech Wireless Mouse
    embedding = present
    in_stock = false

The following search was performed:

    Logitech Wireless Mouse

Even though the query strongly matched the indexed product, `/search`
returned:

    {
      "query": "Logitech Wireless Mouse",
      "items": [],
      "message": "No matching products found."
    }

This demonstrates that semantic similarity cannot override catalog
correctness rules.

An out-of-stock product is excluded even when it is the strongest vector
match.


## Current Limitations

The current development environment uses `FakeEmbeddings`.

The fake provider is useful for deterministic tests and for exercising
the complete retrieval pipeline, but it mainly recognizes shared tokens.
It does not provide the full semantic understanding of a hosted embedding
model.

Retrieval quality should therefore be evaluated again when the real
embedding provider is enabled.

The current implementation also uses one enriched chunk per product.
This is appropriate for the current catalog size and structure, but a
larger catalog or products with very large descriptions may benefit from
a more granular documented chunking strategy in the future.