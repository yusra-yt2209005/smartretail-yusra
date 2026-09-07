# SmartRetail System Design - Weeks 1 to 5






## 1. Design Goal

SmartRetail is a backend-only commerce platform built in five layers of capability:

1. authenticated product/catalog foundation
2. durable publishing and order workflows with concurrency-safe inventory
3. background jobs, event-driven analytics, and observability
4. semantic indexing and retrieval
5. a grounded streaming AI assistant and merchant content generation

The design keeps transactional correctness in PostgreSQL, workflow durability in Temporal, background work in Celery, event distribution in Kafka, caching/rate limiting in Redis, and AI retrieval vectors in pgvector.

The AI layer is deliberately additive. It does not become the source of truth for products, stock, prices, orders, or payments.

---

## 2. High-Level Architecture

```text
                         +----------------------+
                         | Swagger / curl client |
                         +----------+-----------+
                                    |
                                    v
                           +--------+--------+
                           | FastAPI API      |
                           | auth / products  |
                           | orders / search  |
                           | assistant / AI   |
                           +---+---+---+---+--+
                               |   |   |   |
             +-----------------+   |   |   +--------------------+
             |                     |   |                        |
             v                     v   v                        v
      +------+-------+      +------+---+------+          +------+-------+
      | PostgreSQL   |      | Redis           |          | Prometheus   |
      | + pgvector   |      | cache/idempot.  |          | /metrics     |
      | source truth |      | rate limit      |          +------+-------+
      +---+-------+--+      +-----------------+                 |
          |       |                                                   v
          |       |                                            +------+--+
          |       |                                            | Grafana |
          |       |                                            +---------+
          |       |
          |       +-------------------+
          |                           |
          v                           v
 +--------+---------+        +--------+---------+
 | Temporal          |        | Outbox publisher |
 | workflows/worker  |        | -> Kafka         |
 +---+------------+--+        +--------+---------+
     |            |                    |
     |            |                    v
     |            |             +------+-------+
     |            |             | Kafka        |
     |            |             +------+-------+
     |            |                    |
     |            v                    v
     |      +-----+------+      +------+-------+
     |      | Celery     |      | Consumer     |
     |      | worker     |      | analytics    |
     |      +------------+      +--------------+
     |
     +--> product publish -> chunk -> embed -> pgvector
     +--> order saga -> reserve -> pay -> ship -> notify -> confirm

AI path:
FastAPI -> retrieval service -> pgvector/live catalog -> versioned prompt
        -> async LLMProvider -> SSE -> ai_interactions/generated_content
```

---

## 3. Layered Application Structure

### `app/api/v1/`

FastAPI routers are HTTP translation layers. They parse requests, resolve dependencies, call services, and return/stream responses. They should not own SQL or core business rules.

Important router areas now include:

- authentication
- categories
- products and publishing
- inventory
- orders
- analytics
- search
- assistant
- merchant AI generation
- health/readiness

### `app/services/`

Services contain business rules and database operations, including:

- product ownership and lifecycle rules
- inventory reservation
- order creation
- semantic search
- grounded assistant orchestration
- AI interaction persistence
- merchant generation
- AI analytics

### `app/models/`

SQLAlchemy models define durable data shape only.

### `app/schemas/`

Pydantic schemas validate request/response and structured AI outputs.

### `app/core/`

Cross-cutting concerns include:

- environment settings
- auth/security dependencies
- application exceptions
- Redis helpers
- idempotency
- correlation IDs
- logging
- Prometheus metrics
- AI rate limiting and answer caching

### `app/temporal/`

Contains durable product publishing and order saga workflows plus Activities.

### `app/events/`

Contains the transactional outbox, Kafka producer/publisher, consumer, event envelope, and event handlers.

### `app/workers/`

Contains Celery configuration and background jobs such as notifications.

### `app/ai/`

Contains provider abstractions and prompt definitions:

- embeddings provider + FakeEmbeddings
- LLM provider + FakeLLM
- centralized versioned prompt builders

---

## 4. Core Data Model

```text
USER
  | owns
  v
PRODUCT ---------> CATEGORY
  |
  +----> PRODUCT_VARIANT      (price, stock, SKU, attributes)
  +----> PRODUCT_MEDIA
  +----> CONTENT_CHUNK        (semantic text, embedding, retrieval metadata)
  +----> GENERATED_CONTENT    (description/SEO/FAQ, model, prompt version)

USER(customer)
  |
  +----> ORDER
           |
           +----> ORDER_ITEM ------> PRODUCT_VARIANT
           +----> INVENTORY_RESERVATION
           +----> PAYMENT
           +----> SHIPMENT
           +----> ORDER_STATUS_HISTORY

AI_INTERACTION
  +---- user_id (when authenticated)
  +---- question / intent / answer / refused / status
  +---- product_ids / variant_ids
  +---- model / prompt_version / tokens / latency / correlation_id

Operational/event records:
OUTBOX_EVENT -> Kafka -> PROCESSED_EVENT / analytics aggregates
FAILED_JOB
NOTIFICATION
```

---

## 5. User Roles and Authorization

SmartRetail has three roles:

```text
customer
merchant
admin
```

Authentication and authorization are separate concerns.

```text
request
  -> JWT authentication
  -> active user lookup
  -> role check
  -> ownership check when resource-scoped
```

Examples:

- missing token on a protected endpoint -> `401`
- customer calling merchant generation -> `403`
- merchant generating content for another merchant's product -> `403`
- admin may perform privileged operations according to endpoint policy

Passwords are stored only as secure hashes. JWTs carry subject, role, and expiry, but the backend also reloads the user so deactivated/deleted users are not trusted solely because they still possess a token.

---

## 6. Product and Variant Design

A `Product` is the catalog concept. A `ProductVariant` is the sellable unit.

```text
Product: Phone
  +-- Variant A: 128GB / Black / SKU-A / price / stock
  +-- Variant B: 256GB / Silver / SKU-B / price / stock
```

Price and inventory live on `ProductVariant`, never on the general product.

Important constraints:

- SKU is unique
- price uses fixed-precision numeric storage
- stock cannot be negative
- variant attributes use JSONB
- inactive variants cannot be purchased

---

## 7. Product Lifecycle

The lifecycle now includes workflow states:

```text
draft
  -> publishing
       -> published
       -> publish_failed

published -> inactive
publish_failed -> publishing (retry)
```

The API guards illegal entry actions while the Temporal workflow drives internal progression.

A product is not marked published until all required publishing Activities, including Part B embedding, succeed.

---

## 8. Product Publishing Workflow

The current product publishing architecture is a Temporal workflow.

```text
POST /products/{id}/publish
        |
        v
status = PUBLISHING
        |
        v
Temporal ProductPublishWorkflow
        |
        +--> validate_product_activity
        +--> process_media_activity
        +--> build_catalog_activity
        +--> chunk/update content chunk
        +--> embedding Activity (batched, retryable)
        +--> store vector + metadata
        +--> mark_product_published_activity
        |
        +--> on permanent failure -> mark PUBLISH_FAILED
```

Workflow status queries expose the current step, including embedding progress.

### Why Temporal

Temporal records workflow history and retries Activities. If the worker crashes, the workflow resumes from durable history rather than restarting ad hoc logic inside an HTTP request.

### Activity idempotency

Activities must tolerate retries. Examples:

- media processing sets a final state again safely
- chunk/index code replaces/updates current derived records instead of blindly appending duplicates
- publish finalization does not unpublish an already published product

---

## 9. Content Chunks, Embeddings, and Re-Indexing

One enriched semantic chunk is currently created per product. It contains title/category/description/specification signal sufficient for semantic retrieval.

pgvector stores the embedding alongside metadata used for correctness filtering.

Re-publishing handles two cases:

```text
semantic text changed -> re-embed
semantic text unchanged -> keep vector, refresh metadata
```

A SHA-256 text hash supports this optimization and avoids unnecessary provider cost.

No stale duplicated vectors should remain after re-publish.

---

## 10. Semantic Search

```text
POST /search
```

Customer search:

```text
query
 -> embedding provider
 -> pgvector cosine distance
 -> published/available/in-stock filters
 -> live active variant stock check
 -> minimum similarity threshold
 -> top-k results (default 5)
```

The live catalog remains authoritative. Vector similarity is never allowed to make an unavailable product buyable.

Current development similarity threshold is 0.20.

---

## 11. Inventory Concurrency

Overselling is prevented at the database layer with an atomic conditional update:

```sql
UPDATE product_variants
SET stock = stock - :qty
WHERE id = :variant_id
  AND stock >= :qty
RETURNING id;
```

If no row is returned, the reservation fails because sufficient stock was not available at the instant of the update.

This avoids the classic race condition:

```text
SELECT stock
check in Python
UPDATE later
```

Two concurrent requests cannot both "win" the final unit because PostgreSQL evaluates the condition atomically during the update.

Inventory reservations are durable records so retries do not decrement the same reservation twice.

---

## 12. Order Idempotency

Clients send an `Idempotency-Key` when creating an order.

Redis stores the key/result mapping with a TTL so retrying the same customer request returns the original order rather than creating another order/payment.

This solves a different problem from the atomic stock update:

- atomic update prevents concurrent oversell
- idempotency key prevents duplicate logical requests

Both are required.

---

## 13. Order Saga

Order processing runs as a Temporal saga rather than inside the HTTP request.

Forward path:

```text
reserve inventory
 -> authorize payment
 -> create shipment
 -> queue notification
 -> confirm order
```

Compensation examples:

```text
payment fails after reservation
 -> release inventory
 -> cancel/reject order

post-payment step fails
 -> cancel order
 -> refund payment
 -> release inventory
 -> final refunded state
```

The saga preserves an auditable order history rather than deleting failed/cancelled orders.

---

## 14. Notifications and Celery

Temporal does not directly perform the final notification I/O. The notification Activity enqueues a Celery task:

```text
Temporal Activity
    -> send_order_notification.delay(...)
    -> Redis/Celery broker
    -> Celery worker
    -> notifications task/service
    -> notifications table
```

This separates durable business workflow orchestration from retryable background notification delivery.

---

## 15. Transactional Outbox and Kafka

Business events use a transactional outbox.

```text
business database change
   + outbox enqueue in same DB transaction
        |
        v
outbox_events
        |
        | periodic publisher
        v
Kafka producer
        |
        v
smartretail.events
        |
        v
consumer
        |
        +--> idempotency check (processed_events)
        +--> analytics/event handlers
        +--> commit Kafka offset only after successful processing
```

The outbox avoids the dual-write problem where a database commit succeeds but the corresponding Kafka publish is lost.

The consumer assumes at-least-once delivery, not exactly-once delivery. `processed_events.event_id` makes duplicate deliveries safe.

---

## 16. Analytics and Reconciliation

Part A commerce analytics are maintained through event-driven aggregates and exposed through analytics endpoints.

A reconciliation endpoint compares aggregate values with raw transactional tables to detect drift.

Week 5 adds `GET /analytics/ai`, including:

- answered/refused counts
- intent breakdown
- average/p95 latency
- total tokens
- conversion-after-AI

AI interactions retain user/retrieved-variant information so a later order can be checked against products recommended before that purchase.

---

## 17. Observability

### Structured logging

Application logs are JSON structured and carry a correlation ID where possible.

The correlation ID is propagated across:

- HTTP request handling
- Temporal Activities
- event envelopes
- consumer processing
- persisted AI interaction records

This allows a single request/order/AI interaction to be followed across asynchronous components.

### Prometheus

`/metrics` exposes HTTP and domain metrics, including:

```text
http_requests_total
http_request_duration_seconds
orders_placed_total
inventory_oversell_prevented_total
events_consumed_total
events_failed_total
ai_requests_total
ai_failures_total
ai_request_latency_seconds
ai_tokens_total
```

Prometheus scrapes these metrics and Grafana visualizes them.

### Readiness

`/health/ready` checks dependencies such as PostgreSQL, Redis, Kafka, and Temporal so "process is running" is not confused with "service is ready".

---

## 18. AI Assistant Architecture

The customer assistant is retrieval-augmented generation (RAG).

```text
POST /assistant/ask
  |
  +--> authenticate customer
  +--> per-user Redis rate limit
  +--> identical-question Redis cache lookup
  +--> validate question / injection guard
  +--> deterministic intent routing
       |
       +--> discovery -> semantic retrieval
       +--> guidance  -> semantic retrieval
       +--> comparison -> resolve the two named buyable products
  +--> refuse if required grounded data is unavailable
  +--> build centralized/versioned prompt
  +--> async LLMProvider.stream()
  +--> SSE text chunks
  +--> application-generated citations
  +--> terminal done
  +--> persist AIInteraction
  +--> metrics / analytics
  +--> cache successful completed answer
```

The LLM is never the authority for whether a product exists or is buyable.

---

## 19. Grounded Comparison Design

Comparison is stricter than generic semantic retrieval.

The request names two products. Each target is resolved independently against real buyable catalog records. If either named product is missing or unavailable, SmartRetail refuses the comparison.

This prevents a nearest-neighbor search from silently replacing a missing product with something that happens to be semantically similar.

---

## 20. Prompt Safety

Prompts are centralized and versioned in `app/ai/prompts.py`.

The design uses:

- explicit system grounding rules
- clearly delimited catalog context
- clearly delimited customer question
- retrieved text treated as untrusted data
- deterministic application-level prompt-injection pattern checks
- application-generated citations rather than trusting model-created identifiers

This is a basic prompt-injection defense, not a claim of perfect prompt security.

---

## 21. SSE Streaming and Non-Blocking I/O

AI endpoints return `text/event-stream` responses.

Assistant sequence:

```text
text* -> citations -> done
```

Merchant generation sequence varies by content type but always ends with metadata/validated content followed by a terminal done event.

The real LLM provider uses an asynchronous SDK client so waiting for AI output does not intentionally block the FastAPI event loop.

Client disconnects are handled by persisting partial assistant output as `truncated`.

The provider currently has timeout and retry configuration. Final 5.14 hardening still needs complete clean-SSE error framing for every provider failure after a stream has started.

---

## 22. Merchant AI Generation

Merchant generation is protected by both role and ownership checks.

```text
POST /products/{id}/generate/description
POST /products/{id}/generate/seo
POST /products/{id}/generate/faq
```

Description streams text.

SEO and FAQ are structured outputs. The server collects model JSON internally, validates it, and only exposes validated structures.

FAQ allows one repair attempt after malformed output. It does not loop indefinitely.

Successful generated content is stored with product, type, model, prompt version, and accepted flag.

---

## 23. AI Interaction Data Model

`AIInteraction` supports auditing and analytics.

```text
id
user_id (nullable where appropriate)
correlation_id
question
intent
answer
refused
status
prompt_version
model
product_ids (JSONB)
variant_ids (JSONB)
input_tokens
output_tokens
latency_ms
created_at / updated_at
```

Statuses distinguish completed, refused, failed, and truncated behavior.

---

## 24. Generated Content Data Model

`GeneratedContent` stores merchant AI output:

```text
id
product_id
type: description | seo | faq
content JSONB
model
prompt_version
accepted
created_at / updated_at
```

This makes generated content reviewable and reproducible instead of treating it as ephemeral model text.

---

## 25. Redis Caching and Rate Limiting

### Product list cache

Public product listing uses Redis with an explicit TTL and version-based invalidation.

### Assistant answer cache

Completed identical assistant questions are cached by a deterministic normalized-question key plus catalog version. Cache hits still create an AI interaction record but use zero new LLM tokens.

Current documented TTL is 60 seconds.

### AI rate limit

A fixed-window Redis counter limits AI requests per authenticated user.

Normal development configuration:

```text
20 requests / 60 seconds / user
```

A test with a temporary limit of 3 verified that the fourth request returns `429 rate_limit_exceeded`.

---

## 26. Error Model

Service logic raises application exceptions rather than embedding FastAPI-specific `HTTPException` behavior throughout the domain layer.

Examples now include:

- `NotFoundError`
- `UnauthorizedError`
- `ForbiddenError`
- `ConflictError`
- `ValidationFailedError`
- `AIOutputValidationError`
- `TooManyRequestsError`
- `AIProviderUnavailableError`

A centralized handler converts application errors into a consistent JSON response shape.

---

## 27. Key Design Decisions and Tradeoffs

### PostgreSQL + pgvector rather than a separate vector service

Benefits:

- one source database and one operational stack
- easy joins/filtering with current product/variant state
- straightforward correctness filtering

Tradeoff:

- very large-scale ANN tuning may eventually favor a dedicated vector engine

### One enriched chunk per product

Benefits:

- product name, specs, category, and description stay together
- simple re-index semantics
- appropriate for the current catalog size

Tradeoff:

- very long future product content may need smaller semantically coherent chunks

### Database/live stock as authority

Vector metadata is deliberately not trusted as the final availability truth. This adds a live relational check but prevents stale index state from recommending a sold-out product.

### Deterministic intent routing

Simple keyword/rule routing avoids paying for an additional LLM classification call and keeps tests deterministic.

Tradeoff:

- nuanced natural-language intent classification is less flexible than a model router

### Refusal before LLM call

When required catalog context does not exist, the service refuses without calling the LLM.

Benefits:

- lower cost
- lower latency
- smaller hallucination surface

### Redis cache keyed by catalog version

This avoids expensive key scans on every product change. Old cache keys expire naturally while new requests use the new catalog version.

### Async LLM client

An async provider avoids intentionally blocking the event loop during network waits.

---

## 28. Security and Secret Handling

- `.env` must remain ignored by Git
- API keys are environment variables only
- tests default to fake providers and require no secret
- JWT-protected endpoints resolve an active database user
- merchant AI generation requires merchant/admin role plus product ownership
- assistant access is authenticated so per-user rate limiting and conversion analytics can identify the customer

---

## 29. Testing Strategy

The current suite reports:

```text
116 passed
```

Testing spans:

- auth and role enforcement
- product ownership
- inventory concurrency and oversell prevention
- order idempotency and compensation
- search filtering/threshold/re-index behavior
- FakeEmbeddings and FakeLLM
- assistant grounding/refusal/comparison
- malformed input
- FAQ structured validation and repair
- SSE shape and disconnect handling
- merchant AI access control
- AI persistence/analytics behavior

The full suite is designed to run without real AI-provider network calls.

---

## 30. Current Completion State

Completed through Week 5 task 5.13:

```text
5.1  LLMProvider + FakeLLM
5.2  versioned prompts
5.3  discovery assistant
5.4  strict grounded comparison/refusal
5.5  buying guidance
5.6  input validation/injection awareness
5.7  ai_interactions persistence
5.8  SSE assistant streaming/disconnect persistence
5.9  merchant description/SEO/FAQ + validation/repair
5.10 generated_content persistence
5.11 AI analytics + Prometheus metrics
5.12 Redis answer cache + per-user rate limit
5.13 deterministic/access-control/streaming tests
```

Partially complete 5.14:

- async provider implemented
- provider timeout configured
- provider retry count configured
- provider errors translated to application error
- remaining: clean terminal SSE error behavior in every provider-failure path, README/.env.example updates, and clean-clone one-command verification

Final documentation/demonstration tasks remain to be finished after that hardening pass.

---

## 31. Assignment Alignment

The updated architecture is aligned with the Part B emphasis on groundedness and correctness:

- only real, buyable catalog products may be recommended
- impossible/missing-product requests are refused
- comparison uses two real named products
- vectors are derived data, not catalog authority
- all AI work is observable and auditable
- structured outputs are validated
- long output streams progressively
- Redis reduces repeated AI work and enforces per-user limits
- fake providers keep tests deterministic and network-free

The project intentionally prioritizes a cautious grounded answer over a fluent invented answer.

