

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    environment: str = "development"

        # --- Temporal ---
    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "smartretail-task-queue"

    redis_url: str = "redis://redis:6379/0"

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_events_topic: str = "smartretail.events" 

    kafka_consumer_group: str = "smartretail-analytics"

    # --- Week 4: AI embeddings ---
    embedding_provider: str = "fake"

    embedding_model: str = (
        "text-embedding-3-small"
    )

    vector_dimensions: int = 1536

    openai_api_key: str = ""

    embedding_batch_size: int = 32


        # --- Week 4: semantic search ---

    search_default_top_k: int = 5

    # Initial threshold for FakeEmbeddings.
    # Tune this later using the retrieval evaluation set.
    search_similarity_threshold: float = 0.20


# Instantiated once at import time and reused everywhere (a singleton).
# Creating Settings() is cheap but re-parsing env vars on every request
# would be wasteful and could theoretically see a value change mid-request.
settings = Settings()
