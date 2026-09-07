# SmartRetail Domain Events

## 1. Purpose

SmartRetail uses domain events to communicate important business changes
between parts of the application without tightly coupling those components.

The main event flow is:

```text
Business operation / Temporal Activity
                |
                | enqueue(...)
                v
          outbox_events
                |
                | Celery Beat every 5 seconds
                v
       outbox_publisher.py
                |
                v
           producer.py
                |
                v
      Kafka: smartretail.events
                |
                v
           consumer.py
                |
                v
           handlers.py
                |
                v
      analytics projections
```

SmartRetail uses:

- plain JSON events;
- one Kafka topic: `smartretail.events`;
- an `event_type` field to distinguish event types;
- a transactional outbox for reliable publishing;
- an idempotent Kafka consumer;
- correlation IDs for tracing an operation across services.

The required domain events are:

1. `product.published`
2. `order.placed`
3. `inventory.reserved`
4. `payment.succeeded`
5. `shipment.created`
6. `order.confirmed`
7. `refund.processed`

---

# 2. Common Event Envelope

Every domain event uses the same envelope.

Example:

```json
{
  "event_id": "4f83b15f-e62a-4257-9c5d-954637ea1019",
  "event_type": "order.placed",
  "occurred_at": "2026-09-02T16:42:38.000000+00:00",
  "version": 1,
  "correlation_id": "c2f4451b-70d1-41f0-9cb6-72322feb2696",
  "data": {
    "order_id": "d5c53ad8-91bc-4046-a328-fc35238d7430"
  }
}
```

## Envelope fields

| Field | Meaning |
|---|---|
| `event_id` | Unique UUID for this event. It is also used for consumer idempotency. |
| `event_type` | Name of the business event, for example `order.confirmed`. |
| `occurred_at` | UTC timestamp indicating when the event was created. |
| `version` | Version of the event contract. Current events use version `1`. |
| `correlation_id` | Trace ID shared across the operation that produced the event. |
| `data` | Event-specific business data. |

The envelope separates common event metadata from the event-specific
business payload.

---

# 3. Event Creation

Events are created through:

```text
app/events/outbox.py
```

Business code calls:

```python
enqueue(
    db,
    event_type="...",
    data={...},
    correlation_id="...",
)
```

`enqueue()` does **not** directly send the event to Kafka.

It:

1. creates the standard event envelope;
2. creates an `outbox_events` row;
3. adds that row to the caller's current database transaction.

The caller then commits the transaction.

For example:

```text
business database change
        +
outbox event
        |
        v
one database transaction
```

This means the business change and the record saying that an event must
be published become durable together.

---

# 4. Transactional Outbox

SmartRetail uses the transactional outbox pattern.

The relevant table is:

```text
outbox_events
```

Important columns include:

```text
id
event_id
event_type
payload
correlation_id
published_at
created_at
```

The important state is:

```text
published_at IS NULL
```

which means:

> The event has been saved safely in the database but Kafka delivery has
> not yet been confirmed.

When Kafka confirms delivery:

```text
published_at = <UTC timestamp>
```

The event is then considered published.

---

## Why the outbox is needed

Without an outbox, code might try to do:

```text
1. Commit business change to Postgres
2. Publish event directly to Kafka
```

These are two independent systems.

A failure could occur between them:

```text
database commit succeeds
        |
        v
application crashes
        |
        v
Kafka publish never happens
```

The database would say the business action happened, but Kafka consumers
would never know about it.

This is the **dual-write problem**.

SmartRetail avoids it by doing:

```text
Postgres transaction:
    business change
    +
    outbox event
            |
            v
          COMMIT
```

Kafka publishing happens afterward from the durable outbox.

If Kafka is temporarily unavailable, the event remains in the outbox
with `published_at = NULL` and can be retried later.

---

# 5. Outbox Publishing

The publishing path is:

```text
Celery Beat
    |
    | every 5 seconds
    v
app/workers/tasks/outbox_publisher.py
    |
    v
app/events/producer.py
    |
    v
Kafka
```

`outbox_publisher.py` is a Celery background task.

It calls:

```python
publish_pending_outbox(db)
```

in `producer.py`.

The producer searches for events where:

```text
published_at IS NULL
```

and publishes those events to:

```text
smartretail.events
```

After Kafka confirms delivery, the producer fills in `published_at`.

Therefore:

```text
enqueue()
= save event

outbox_publisher.py
= periodically start publication

producer.py
= send event TO Kafka
```

---

# 6. Kafka Producer

File:

```text
app/events/producer.py
```

The Kafka producer is responsible for sending events **to Kafka**.

```text
outbox_events
      |
      v
producer.py
      |
      v
smartretail.events
```

The producer does not calculate analytics.

Its responsibility is event transport.

The event remains pending until Kafka delivery is confirmed.

---

# 7. Kafka Consumer

File:

```text
app/events/consumer.py
```

The consumer subscribes to:

```text
smartretail.events
```

The consumer:

1. polls Kafka for a message;
2. decodes the JSON envelope;
3. reads the `event_type`;
4. restores the event's `correlation_id`;
5. passes the event to `handlers.py`;
6. commits the Kafka offset only after processing succeeds.

Flow:

```text
Kafka
  |
  v
consumer.py
  |
  v
process_event(...)
  |
  v
handlers.py
```

Therefore:

```text
Producer = sends TO Kafka
Consumer = receives FROM Kafka
Handler  = decides what the event changes
```

---

# 8. Kafka Delivery Semantics and Idempotency

SmartRetail is designed for **at-least-once delivery**.

At-least-once means an event may occasionally be delivered more than
once.

For example:

```text
order.confirmed
      |
      v
consumer processes it
      |
      v
DB transaction succeeds
      |
      X
consumer crashes before offset commit
      |
      v
Kafka delivers the event again
```

Without duplicate protection, the second delivery could increase revenue
twice.

SmartRetail prevents this using:

```text
processed_events
```

Before applying an event, the handler checks whether its `event_id` has
already been processed by that consumer.

If it has already been processed:

```text
duplicate event
      |
      v
skip business changes
```

The duplicate is considered safely handled.

This means replaying an event such as `order.confirmed` does not
double-count revenue.

---

## Kafka offset rule

SmartRetail disables automatic offset commits.

The offset is committed only after:

```text
event received
     ↓
database processing succeeds
     ↓
offset committed
```

If processing fails:

```text
event received
     ↓
processing fails
     ↓
offset NOT committed
     ↓
Kafka can redeliver
```

The `processed_events` table makes this retry safe.

---

# 9. Domain Event Catalogue

| Event | Meaning |
|---|---|
| `product.published` | A product successfully completed the publishing workflow. |
| `order.placed` | A customer order was created. |
| `inventory.reserved` | Stock was successfully reserved for an order item. |
| `payment.succeeded` | Payment authorization succeeded. |
| `shipment.created` | A shipment was created for an order. |
| `order.confirmed` | The order successfully reached its completed state. |
| `refund.processed` | A successful payment was refunded during saga compensation. |

---

# 10. `product.published`

## Meaning

Emitted when the product publishing workflow successfully completes and
the product becomes `PUBLISHED`.

Produced from the product publishing flow.

## Data

```json
{
  "product_id": "2ae7a12d-204f-497b-96e0-6111cae33bdf",
  "published_at": "2026-09-02T16:40:00.000000+00:00"
}
```

### Fields

| Field | Meaning |
|---|---|
| `product_id` | UUID of the published product. |
| `published_at` | UTC timestamp when the product became published. |

## Transaction boundary

The product status change and `product.published` outbox event are
committed together.

Conceptually:

```text
product.status = PUBLISHED
        +
product.published outbox event
        |
        v
      COMMIT
```

## Analytics use

This event allows the analytics projection to track how many products
have been published.

The daily aggregate contains:

```text
analytics_daily.products_published
```

---

# 11. `order.placed`

## Meaning

Emitted after a new customer order has been created.

This represents the beginning of the order lifecycle.

The normal order success path is:

```text
PLACED
  ↓
RESERVED
  ↓
PAID
  ↓
SHIPPED
  ↓
DELIVERED
  ↓
COMPLETED
```

## Data

The payload contains the identity and placement information for the new
order.

Example:

```json
{
  "order_id": "d5c53ad8-91bc-4046-a328-fc35238d7430",
  "customer_id": "5c78ca0a-6e67-4da1-a683-e31f86c7190e",
  "total": "2499.99"
}
```

Money is serialized safely in JSON rather than relying on binary
floating-point values.

## Transaction boundary

The new order and the `order.placed` outbox event are committed as part
of the order-creation database operation.

## Analytics use

The Kafka handler uses order events to maintain the daily order
projection.

Revenue is based on successfully confirmed/completed orders rather than
treating payment authorization alone as final revenue.

---

# 12. `inventory.reserved`

## Meaning

Emitted when inventory has been successfully reserved for a variant in
an order.

The reservation Activity performs an atomic stock decrement.

## Data

```json
{
  "order_id": "d5c53ad8-91bc-4046-a328-fc35238d7430",
  "variant_id": "174c06ef-806e-49a5-85c6-1a570cc7e4a4",
  "qty": 1,
  "stockout": false,
  "reserved_at": "2026-09-02T16:42:38.000000+00:00"
}
```

### Fields

| Field | Meaning |
|---|---|
| `order_id` | Order that requested the stock. |
| `variant_id` | Product variant whose stock was reserved. |
| `qty` | Quantity reserved. |
| `stockout` | `true` if the successful reservation reduced remaining stock to zero. |
| `reserved_at` | UTC reservation timestamp. |

## Transaction boundary

These are committed together:

```text
1. decrement variant stock
2. create InventoryReservation
3. create inventory.reserved outbox event
```

This ensures that a reservation cannot become durable without its
corresponding domain event.

## Analytics use

The event can contribute to inventory/stockout analytics.

The `stockout` field records whether this reservation caused the
variant to reach zero stock.

---

# 13. `payment.succeeded`

## Meaning

Emitted when the simulated `PaymentAuthorizer` successfully authorizes
payment for an order.

A failed authorization does **not** emit `payment.succeeded`.

## Data

```json
{
  "order_id": "d5c53ad8-91bc-4046-a328-fc35238d7430",
  "payment_id": "9039b923-c960-4c73-83ed-a535ae33af91",
  "amount": "2499.99"
}
```

### Fields

| Field | Meaning |
|---|---|
| `order_id` | Order being paid for. |
| `payment_id` | UUID of the payment record. |
| `amount` | Authorized payment amount. |

## Transaction boundary

The following are committed together:

```text
payment row
    +
order transition to PAID
    +
payment.succeeded outbox event
```

## Important distinction

`payment.succeeded` means:

> Payment was successfully authorized.

It does not by itself mean the complete order lifecycle succeeded.

If a later saga step fails, compensation can refund the payment.

---

# 14. `shipment.created`

## Meaning

Emitted when a new shipment is created for an order.

The shipment Activity is retry-safe: if the shipment already exists,
the Activity reuses it rather than creating another shipment.

The event is emitted only when a new shipment is actually created.

## Data

```json
{
  "order_id": "d5c53ad8-91bc-4046-a328-fc35238d7430",
  "shipment_id": "35b1bb4f-c3cb-4995-b96e-c41df75fe4ca"
}
```

### Fields

| Field | Meaning |
|---|---|
| `order_id` | Order being shipped. |
| `shipment_id` | UUID of the newly created shipment. |

## Order transition

The normal flow moves the order into the shipped portion of the saga:

```text
PAID
 ↓
SHIPPED
```

The shipment itself progresses through shipment states such as:

```text
CREATED
   ↓
DISPATCHED
   ↓
DELIVERED
```

---

# 15. `order.confirmed`

## Meaning

Emitted when the order saga successfully reaches its final successful
state.

The confirmation Activity moves the successful order through:

```text
SHIPPED
   ↓
DELIVERED
   ↓
COMPLETED
```

Reserved inventory is also marked as committed because the order has
successfully consumed it.

## Data

```json
{
  "order_id": "d5c53ad8-91bc-4046-a328-fc35238d7430",
  "customer_id": "5c78ca0a-6e67-4da1-a683-e31f86c7190e",
  "total": "2499.99"
}
```

### Fields

| Field | Meaning |
|---|---|
| `order_id` | Completed order. |
| `customer_id` | Customer who placed the order. |
| `total` | Final order total. |

## Transaction boundary

The completed order state and `order.confirmed` outbox event are
committed together.

## Analytics use

This is one of the most important events for business analytics.

Confirmed/completed orders are used for metrics such as:

```text
orders over time
revenue trend
average order value
most popular products
```

Product-level analytics are maintained in:

```text
analytics_product
```

with values such as:

```text
units_sold
revenue
```

Daily analytics are maintained in:

```text
analytics_daily
```

with values such as:

```text
orders
revenue
```

Because the consumer is idempotent, replaying the same
`order.confirmed` event does not increase revenue or units sold twice.

---

# 16. `refund.processed`

## Meaning

Emitted when the order saga compensates for a payment that had already
been authorized.

This can happen when a later post-payment step fails.

The compensation path is conceptually:

```text
payment already succeeded
        |
        v
later saga step fails
        |
        v
cancel order
        |
        v
refund payment
        |
        v
release inventory
```

## Data

```json
{
  "order_id": "d5c53ad8-91bc-4046-a328-fc35238d7430",
  "payment_id": "9039b923-c960-4c73-83ed-a535ae33af91",
  "amount": "2499.99"
}
```

### Fields

| Field | Meaning |
|---|---|
| `order_id` | Order associated with the refund. |
| `payment_id` | Refunded payment record. |
| `amount` | Refunded amount. |

The payment state becomes:

```text
REFUNDED
```

and the event provides a durable record that the compensation occurred.

---

# 17. Successful Order Event Sequence

A normal successful order produces this event sequence:

```text
POST /orders
     |
     v
order.placed
     |
     v
inventory.reserved
     |
     v
payment.succeeded
     |
     v
shipment.created
     |
     v
order.confirmed
```

All of these events for the same request/order carry the same
correlation ID so the operation can be followed through distributed
logs.

Example:

```text
correlation_id:
c2f4451b-70d1-41f0-9cb6-72322feb2696

order.placed
inventory.reserved
payment.succeeded
shipment.created
order.confirmed
```

---

# 18. Failure / Compensation Event Sequence

Not every saga emits all success events.

For example, if inventory cannot be reserved:

```text
order.placed
     |
     v
inventory reservation fails
     |
     v
release any partial reservation
     |
     v
order REJECTED
```

There is no `payment.succeeded` because payment was never successfully
authorized.

If payment authorization fails after inventory was reserved:

```text
order.placed
     |
     v
inventory.reserved
     |
     v
payment fails
     |
     v
release inventory
     |
     v
order CANCELLED
```

If payment succeeds but a later saga step fails:

```text
order.placed
     |
     v
inventory.reserved
     |
     v
payment.succeeded
     |
     v
later step fails
     |
     v
cancel order
     |
     v
refund payment
     |
     v
refund.processed
     |
     v
release inventory
```

---

# 19. Analytics Projection

Kafka events are consumed by:

```text
app/events/consumer.py
```

and passed to:

```text
app/events/handlers.py
```

The handlers maintain pre-aggregated analytics tables.

The two main projection tables are:

```text
analytics_daily
analytics_product
```

## `analytics_daily`

Stores business totals grouped by day.

Examples include:

```text
date
orders
revenue
stockouts
products_published
```

Instead of scanning every historical order each time the analytics API
is called, these values are already summarized.

Example conceptually:

```text
date         orders    revenue    stockouts    products_published
------------------------------------------------------------------
2026-09-01      5       9400.00       1                3
2026-09-02      8      15750.00       0                2
```

## `analytics_product`

Stores product-level aggregates.

Examples include:

```text
product_id
units_sold
revenue
```

Conceptually:

```text
product_id       units_sold      revenue
-----------------------------------------
product A             12         7200.00
product B              7         3500.00
```

This supports metrics such as:

```text
most popular products
product revenue
```

---

# 20. What Is an Aggregate?

An **aggregate** is a summarized value calculated from multiple
individual records.

For example, raw orders may be:

```text
Order A = 100 QAR
Order B = 250 QAR
Order C = 150 QAR
```

Aggregates are:

```text
order count = 3
revenue     = 500 QAR
average     = 166.67 QAR
```

SmartRetail stores pre-aggregated values so the analytics API does not
need to recalculate the entire order history on every request.

---

# 21. Kafka Analytics vs Celery Rollup

SmartRetail has two ways to keep analytics accurate.

## Kafka consumer: incremental updates

Kafka events allow analytics to be updated shortly after each business
event occurs.

```text
new Kafka event
      |
      v
consumer.py
      |
      v
handlers.py
      |
      v
update relevant aggregate
```

This is an **incremental aggregation**.

For example:

```text
current orders = 10
new relevant event arrives
current orders = 11
```

Only the change caused by the new event needs to be applied.

---

## Celery: periodic recomputation

A Celery analytics task runs every five minutes.

It recomputes analytics using the raw source-of-truth database tables.

```text
Celery Beat
     |
     | every 5 minutes
     v
analytics task
     |
     v
raw database tables
     |
     v
recompute aggregates
     |
     v
analytics_daily
analytics_product
```

This acts as a safety/correction mechanism if an event-driven projection
ever drifts from the raw data.

Therefore:

```text
Kafka consumer
= fast incremental analytics updates

Celery rollup
= periodic recalculation from raw data
```

They support the same business analytics, but for different reasons.

---

# 22. Analytics Reconciliation

SmartRetail also exposes an analytics reconciliation operation.

Reconciliation compares:

```text
pre-aggregated analytics
          VS
raw source-of-truth database
```

Example:

```text
analytics_daily.orders = 5
raw completed orders   = 5

drift = 0
matches = true
```

If they disagree:

```text
analytics_daily.orders = 4
raw completed orders   = 5

drift = -1
matches = false
```

The purpose is to detect silent projection drift.

---

# 23. Correlation IDs

Every event contains:

```text
correlation_id
```

This allows one operation to be traced across multiple processes.

For an order, the same correlation ID can appear in:

```text
FastAPI logs
     ↓
Temporal Workflow
     ↓
Temporal Activities
     ↓
Celery task
     ↓
outbox event
     ↓
Kafka producer
     ↓
Kafka consumer
     ↓
analytics handler
```

Example log sequence:

```text
correlation_id = abc-123

Reserving inventory for order ...
Authorizing payment for order ...
Creating shipment for order ...
Confirming order ...
Publishing Kafka event ...
Received Kafka event ...
Analytics updated from event ...
```

This is useful because the application is distributed across multiple
workers and services.

---

# 24. Event Versioning

The current event envelope uses:

```json
{
  "version": 1
}
```

The version describes the event contract.

Compatible additions can normally remain on the same version, but a
breaking change to the meaning or required structure of an event should
introduce a new version so consumers can distinguish contracts.

---

# 25. Relevant Files

```text
app/events/envelope.py
    Creates the common event envelope.

app/events/outbox.py
    enqueue() stores events in the transactional outbox.

app/models/outbox_event.py
    SQLAlchemy model for outbox_events.

app/workers/tasks/outbox_publisher.py
    Celery task that triggers outbox publication.

app/events/producer.py
    Kafka producer. Sends pending outbox events TO Kafka.

app/events/consumer.py
    Kafka consumer. Receives events FROM Kafka.

app/events/handlers.py
    Applies the business/analytics reaction to each event.

app/models/processed_event.py
    Records processed event IDs for consumer idempotency.

app/models/analytics.py
    Defines analytics_daily and analytics_product.

app/services/analytics_service.py
    Reads/reconciles/recomputes analytics.

app/temporal/activities.py
    Produces several order/product domain events.
```

---

# 26. Operational Checks

## View recent outbox events

```bash
docker compose exec postgres sh -lc '
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
    event_type,
    correlation_id,
    created_at,
    published_at
FROM outbox_events
ORDER BY created_at DESC
LIMIT 20;
"
'
```

A null `published_at` means the event is still waiting for confirmed
Kafka publication.

---

## Watch Kafka events from the command line

```bash
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic smartretail.events
```

Start this command before creating an order to watch new events arrive.

To view existing events from the beginning:

```bash
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic smartretail.events \
  --from-beginning
```

---

## View consumer group lag

```bash
docker compose exec kafka kafka-consumer-groups \
  --bootstrap-server kafka:9092 \
  --describe \
  --group smartretail-analytics
```

Important columns include:

```text
CURRENT-OFFSET
LOG-END-OFFSET
LAG
```

`LAG = 0` means the consumer has caught up with the available messages.

---

## View Kafka consumer logs

```bash
docker compose logs consumer --tail=100
```

---

## Trace one correlation ID

Example:

```bash
CID="<correlation-id>"

docker compose logs temporal-worker 2>&1 | grep "$CID"
docker compose logs celery-worker 2>&1 | grep "$CID"
docker compose logs consumer 2>&1 | grep "$CID"
```

This demonstrates end-to-end correlation across background components.

---

# 27. Summary

The complete SmartRetail event path is:

```text
Business operation
      |
      v
enqueue()
      |
      v
outbox_events
      |
      | every 5 seconds
      v
Celery outbox publisher
      |
      v
Kafka producer
      |
      v
smartretail.events
      |
      v
Kafka consumer
      |
      v
event handler
      |
      v
processed_events duplicate protection
      |
      v
analytics_daily / analytics_product
```

The key responsibilities are:

```text
enqueue()
= safely RECORD the event

outbox
= make event publication durable

producer
= SEND event to Kafka

Kafka
= transport/store event stream

consumer
= RECEIVE event from Kafka

handler
= REACT to the event

processed_events
= prevent duplicate application

analytics_daily
= daily business aggregates

analytics_product
= per-product business aggregates
```

This design gives SmartRetail asynchronous event processing, reliable
event publication, duplicate-safe analytics, and end-to-end traceability.