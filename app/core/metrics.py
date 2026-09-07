from prometheus_client import Counter, Histogram


HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    [
        "method",
        "endpoint",
        "status",
    ],
)


HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    [
        "method",
        "endpoint",
    ],
)


ORDERS_PLACED_TOTAL = Counter(
    "orders_placed_total",
    "Total number of orders successfully placed",
)


INVENTORY_OVERSELL_PREVENTED_TOTAL = Counter(
    "inventory_oversell_prevented_total",
    (
        "Number of inventory reservation attempts "
        "rejected because there was insufficient stock"
    ),
)


EVENTS_CONSUMED_TOTAL = Counter(
    "events_consumed_total",
    "Total number of Kafka events processed",
    ["event_type"],
)


EVENTS_FAILED_TOTAL = Counter(
    "events_failed_total",
    "Total number of Kafka events that failed processing",
    ["event_type"],
)

# ---------------------------------------------------------------------
# Week 5: AI metrics
# ---------------------------------------------------------------------

AI_REQUESTS_TOTAL = Counter(
    "ai_requests_total",
    "Total number of AI requests",
    [
        "intent",
        "refused",
    ],
)


AI_FAILURES_TOTAL = Counter(
    "ai_failures_total",
    "Total number of failed AI requests",
    [
        "intent",
    ],
)


AI_REQUEST_LATENCY_SECONDS = Histogram(
    "ai_request_latency_seconds",
    "AI request latency in seconds",
    [
        "intent",
    ],
)


AI_TOKENS_TOTAL = Counter(
    "ai_tokens_total",
    "Total number of AI tokens used",
    [
        "type",
    ],
)