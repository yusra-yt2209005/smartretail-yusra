import asyncio
import uuid
from decimal import Decimal

from app.services import (
    assistant_service,
)
from app.ai.llm import (
    FakeLLM,
    LLMStreamEvent,
)


def _fake_product(
    title: str = "Demo Samsung Phone",
):
    return {
        "product_id": uuid.uuid4(),
        "variant_id": uuid.uuid4(),
        "title": title,
        "category_id": uuid.uuid4(),
        "price": Decimal("999.99"),
        "similarity": 0.91,
        "context_text": (
            f"Title: {title}\n"
            "Category: Phones\n"
            "Description: Demo smartphone."
        ),
    }


async def _collect_stream(
    **kwargs,
):
    events = []

    async for event in (
        assistant_service.stream_assistant(
            **kwargs
        )
    ):
        events.append(
            event
        )

    return events


def test_stream_text_then_citations_then_done(
    monkeypatch,
):
    product = _fake_product()

    monkeypatch.setattr(
        assistant_service,
        "search_products",
        lambda *args, **kwargs: [
            product
        ],
    )

    persisted = []

    monkeypatch.setattr(
        assistant_service,
        "_persist_interaction",
        lambda *args, **kwargs: (
            persisted.append(kwargs)
        ),
    )

    llm = FakeLLM(
        response_text=(
            "This is a streamed answer."
        ),
        stream_chunk_size=5,
    )

    events = asyncio.run(
        _collect_stream(
            db=None,
            question="Samsung phone",
            llm=llm,
        )
    )

    event_types = [
        event["type"]
        for event in events
    ]

    assert event_types[-2:] == [
        "citations",
        "done",
    ]

    text_events = [
        event
        for event in events
        if event["type"] == "text"
    ]

    assert len(text_events) > 1

    generated_text = "".join(
        event["text"]
        for event in text_events
    )

    assert generated_text == (
        "This is a streamed answer."
    )

    assert (
        events[-1]["status"]
        == "completed"
    )

    assert len(persisted) == 1

    assert (
        persisted[0]["status"]
        == "completed"
    )


def test_stream_uses_provider_stream_not_generate(
    monkeypatch,
):
    product = _fake_product()

    monkeypatch.setattr(
        assistant_service,
        "search_products",
        lambda *args, **kwargs: [
            product
        ],
    )

    monkeypatch.setattr(
        assistant_service,
        "_persist_interaction",
        lambda *args, **kwargs: None,
    )

    llm = FakeLLM(
        response_text="Streaming works.",
        stream_chunk_size=4,
    )

    async def forbidden_generate(
        **kwargs,
    ):
        raise AssertionError(
            "generate() must not be used "
            "for SSE streaming"
        )

    llm.generate = forbidden_generate

    events = asyncio.run(
        _collect_stream(
            db=None,
            question="Samsung phone",
            llm=llm,
        )
    )

    assert (
        events[-1]["type"]
        == "done"
    )


def test_stream_refuses_without_llm(
    monkeypatch,
):
    monkeypatch.setattr(
        assistant_service,
        "search_products",
        lambda *args, **kwargs: [],
    )

    persisted = []

    monkeypatch.setattr(
        assistant_service,
        "_persist_interaction",
        lambda *args, **kwargs: (
            persisted.append(kwargs)
        ),
    )

    llm = FakeLLM(
        response_text=(
            "This must not be used."
        )
    )

    events = asyncio.run(
        _collect_stream(
            db=None,
            question="Impossible product",
            llm=llm,
        )
    )

    assert len(llm.calls) == 0

    assert (
        events[-1]["type"]
        == "done"
    )

    assert (
        events[-1]["status"]
        == "refused"
    )

    assert (
        persisted[0]["status"]
        == "refused"
    )


def test_stream_comparison_resolves_exact_products(
    monkeypatch,
):
    first = _fake_product(
        "M2 Samsung Galaxy A56"
    )

    second = _fake_product(
        "M2 Samsung Galaxy S25"
    )

    def fake_find(
        db,
        *,
        name,
    ):
        if name == "Samsung Galaxy A56":
            return first

        if name == "Samsung Galaxy S25":
            return second

        return None

    monkeypatch.setattr(
        assistant_service,
        "find_buyable_product_by_name",
        fake_find,
    )

    monkeypatch.setattr(
        assistant_service,
        "_persist_interaction",
        lambda *args, **kwargs: None,
    )

    llm = FakeLLM(
        response_text="Comparison."
    )

    events = asyncio.run(
        _collect_stream(
            db=None,
            question=(
                "Compare Samsung Galaxy A56 "
                "and Samsung Galaxy S25"
            ),
            llm=llm,
        )
    )

    citations_event = (
        events[-2]
    )

    assert (
        citations_event["type"]
        == "citations"
    )

    assert (
        len(
            citations_event[
                "citations"
            ]
        )
        == 2
    )


def test_stream_missing_comparison_product_refuses(
    monkeypatch,
):
    real_product = _fake_product(
        "M2 Samsung Galaxy S25"
    )

    def fake_find(
        db,
        *,
        name,
    ):
        if name == "Samsung Galaxy S25":
            return real_product

        return None

    monkeypatch.setattr(
        assistant_service,
        "find_buyable_product_by_name",
        fake_find,
    )

    monkeypatch.setattr(
        assistant_service,
        "_persist_interaction",
        lambda *args, **kwargs: None,
    )

    llm = FakeLLM(
        response_text=(
            "Must not be generated."
        )
    )

    events = asyncio.run(
        _collect_stream(
            db=None,
            question=(
                "Compare Samsung Galaxy S25 "
                "and FakePhone Ultra 9000"
            ),
            llm=llm,
        )
    )

    assert len(llm.calls) == 0

    assert (
        events[-1]["status"]
        == "refused"
    )

def test_stream_persists_partial_answer_on_disconnect(
    monkeypatch,
):
    product = _fake_product()

    monkeypatch.setattr(
        assistant_service,
        "search_products",
        lambda *args, **kwargs: [
            product
        ],
    )

    persisted = []

    monkeypatch.setattr(
        assistant_service,
        "_persist_interaction",
        lambda *args, **kwargs: (
            persisted.append(kwargs)
        ),
    )

    class DisconnectingLLM(FakeLLM):
        async def stream(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
        ):
            self._record_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            yield LLMStreamEvent(
                text="Partial answer"
            )

            raise asyncio.CancelledError

    llm = DisconnectingLLM()

    async def consume():
        async for _ in (
            assistant_service.stream_assistant(
                db=None,
                question="Samsung phone",
                llm=llm,
            )
        ):
            pass

    try:
        asyncio.run(
            consume()
        )
    except asyncio.CancelledError:
        pass

    assert len(persisted) == 1

    assert (
        persisted[0]["status"]
        == "truncated"
    )

    assert (
        persisted[0]["response"].answer
        == "Partial answer"
    )