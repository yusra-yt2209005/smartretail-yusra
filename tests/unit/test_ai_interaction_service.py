from app.services.ai_interaction_service import (
    record_ai_interaction,
)


class FakeSession:
    def __init__(self):
        self.added = None
        self.committed = False
        self.refreshed = None

    def add(self, value):
        self.added = value

    def commit(self):
        self.committed = True

    def refresh(self, value):
        self.refreshed = value


def test_record_ai_interaction_persists_fields(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.ai_interaction_service.get_correlation_id",
        lambda: "test-correlation-id",
    )

    db = FakeSession()

    interaction = record_ai_interaction(
        db,
        question="Which Samsung phone should I buy?",
        intent="guidance",
        answer="Fake LLM response.",
        refused=False,
        status="completed",
        prompt_version="guidance-v1",
        model="fake-llm",
        product_ids=[
            "product-1",
            "product-2",
        ],
        variant_ids=[
            "variant-1",
            "variant-2",
        ],
        input_tokens=12,
        output_tokens=6,
        latency_ms=25.5,
    )

    assert (
        interaction.correlation_id
        == "test-correlation-id"
    )

    assert interaction.intent == "guidance"

    assert interaction.refused is False

    assert (
        interaction.status
        == "completed"
    )

    assert interaction.input_tokens == 12
    assert interaction.output_tokens == 6

    assert interaction.product_ids == [
        "product-1",
        "product-2",
    ]

    assert db.added is interaction
    assert db.committed is True
    assert db.refreshed is interaction