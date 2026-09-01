# SmartRetail AI Layer

## Embeddings and Vector Similarity

Traditional keyword search mainly depends on matching words in the
customer's query with words stored in the product catalog. This can miss
relevant products when the same idea is expressed using different words.
For example, a customer may search for "a phone for taking good pictures",
while a product description may say that it has a "48MP camera". The
phrases are different, but they have similar meaning.

An embedding is a numerical representation of text. An embedding model
takes text as input and converts it into a vector, which is a list of
numbers. The individual numbers are not meaningful on their own. Instead,
the vector as a whole represents features of the meaning of the text.
Texts with similar meanings should have vectors that are closer together
than texts about unrelated subjects.

SmartRetail can use this by embedding both product content and the
customer's search query using the same embedding model. Product chunks
can contain useful information such as the product title, description,
category and variant attributes. Their vectors are stored in the vector
database. When a customer searches, their query is also converted into a
vector and compared with the stored product vectors.

Vector similarity measures how close these vectors are. One common
method is cosine similarity, which compares the direction of two vectors.
A higher similarity means the query and product are more semantically
related. This allows SmartRetail to perform semantic search and retrieve
products based on meaning instead of requiring exact keyword matches.


## Chunking Strategy

SmartRetail uses one enriched semantic chunk per product rather than
splitting product text at a fixed number of characters. Each chunk
combines the product title, category, variant attributes/specifications,
and description.

For example, attributes such as brand, storage, connector type, camera
specifications, or colour are included because customers may search for
these concepts even when they do not appear in the product title.

Price, stock, and product status are not included in the semantic chunk.
They change frequently and are better treated as retrieval metadata.
This also means that a price-only or stock-only update can refresh the
metadata without generating a new embedding when the product's semantic
text has not changed.

This approach gives every embedding enough context to represent what the
product is, while avoiding blind fixed-length splitting that could
separate a product name from the specifications that give it meaning.