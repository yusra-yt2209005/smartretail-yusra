import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.ai.llm import FakeLLM
from app.core.exceptions import (
    AIOutputValidationError,
)
from app.services import (
    content_generation_service,
)


def _fake_product():
    variant = SimpleNamespace(
        sku="PHONE-256-BLK",
        price="1499.99",
        stock=10,
        is_active=True,
        attributes={
            "storage": "256GB",
            "color": "Black",
        },
    )

    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Demo Phone",
        description=(
            "A demo smartphone."
        ),
        category_id=uuid.uuid4(),
        status=SimpleNamespace(
            value="published"
        ),
        variants=[
            variant
        ],
    )


async def _collect(
    iterator,
):
    events = []

    async for event in iterator:
        events.append(
            event
        )

    return events


def test_build_product_context_uses_real_product_data():
    product = _fake_product()

    context = (
        content_generation_service
        .build_product_context(
            product
        )
    )

    assert "Demo Phone" in context
    assert "A demo smartphone." in context
    assert "PHONE-256-BLK" in context
    assert "256GB" in context
    assert "1499.99" in context


def test_description_streams_from_provider():
    product = _fake_product()

    llm = FakeLLM(
        response_text=(
            "A useful product description."
        ),
        stream_chunk_size=5,
    )

    events = asyncio.run(
        _collect(
            content_generation_service
            .stream_description(
                product=product,
                llm=llm,
            )
        )
    )

    text = "".join(
        event["text"]
        for event in events
        if event["type"] == "text"
    )

    assert text == (
        "A useful product description."
    )

    assert (
        events[-2]["type"]
        == "metadata"
    )

    assert (
        events[-1]["type"]
        == "done"
    )


def test_seo_stream_validates_json():
    product = _fake_product()

    llm = FakeLLM(
        response_text=(
            '{"title":"Demo Phone",'
            '"meta_description":'
            '"A demo smartphone."}'
        ),
        stream_chunk_size=10,
    )

    events = asyncio.run(
        _collect(
            content_generation_service
            .stream_seo(
                product=product,
                llm=llm,
            )
        )
    )

    seo_events = [
        event
        for event in events
        if event["type"] == "seo"
    ]

    assert len(seo_events) == 1

    assert (
        seo_events[0]["seo"]["title"]
        == "Demo Phone"
    )

    assert (
        seo_events[0]["seo"][
            "meta_description"
        ]
        == "A demo smartphone."
    )

    assert (
        events[-2]["type"]
        == "metadata"
    )

    assert (
        events[-1]["type"]
        == "done"
    )

    assert (
        events[-1]["status"]
        == "completed"
    )

def test_seo_invalid_json_fails_cleanly():
    product = _fake_product()

    llm = FakeLLM(
        response_text=(
            "this is not JSON"
        )
    )

    events = asyncio.run(
        _collect(
            content_generation_service
            .stream_seo(
                product=product,
                llm=llm,
            )
        )
    )

    error_events = [
        event
        for event in events
        if event["type"] == "error"
    ]

    assert len(
        error_events
    ) == 1

    assert (
        error_events[0]["code"]
        == "ai_output_invalid"
    )

    assert (
        events[-1]["type"]
        == "done"
    )

    assert (
        events[-1]["status"]
        == "failed"
    )


def test_faq_valid_first_attempt():
    product = _fake_product()

    llm = FakeLLM(
        response_text=(
            '{"faqs":['
            '{"question":"What storage does it have?",'
            '"answer":"It has 256GB storage."},'
            '{"question":"What color is it?",'
            '"answer":"It is black."}'
            ']}'
        )
    )

    faq, model, _, _ = asyncio.run(
        content_generation_service
        .generate_faq_with_repair(
            product=product,
            count=2,
            llm=llm,
        )
    )

    assert len(faq.faqs) == 2
    assert model == "fake-llm"

    # No repair was required.
    assert len(llm.calls) == 1


def test_faq_repairs_invalid_json_once():
    product = _fake_product()

    class RepairingFakeLLM(FakeLLM):
        def __init__(self):
            super().__init__()
            self.attempt = 0

        async def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
        ):
            self.attempt += 1

            if self.attempt == 1:
                self.response_text = (
                    "invalid JSON"
                )
            else:
                self.response_text = (
                    '{"faqs":['
                    '{"question":"What storage?",'
                    '"answer":"256GB."}'
                    ']}'
                )

            return await super().generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

    llm = RepairingFakeLLM()

    faq, _, _, _ = asyncio.run(
        content_generation_service
        .generate_faq_with_repair(
            product=product,
            count=1,
            llm=llm,
        )
    )

    assert len(faq.faqs) == 1

    # Initial generation + exactly one repair.
    assert llm.attempt == 2


def test_faq_fails_after_one_repair_attempt():
    product = _fake_product()

    class BrokenFakeLLM(FakeLLM):
        def __init__(self):
            super().__init__(
                response_text=(
                    "still invalid"
                )
            )

    llm = BrokenFakeLLM()

    with pytest.raises(
        AIOutputValidationError
    ):
        asyncio.run(
            content_generation_service
            .generate_faq_with_repair(
                product=product,
                count=2,
                llm=llm,
            )
        )

    # First attempt + exactly one repair.
    assert len(llm.calls) == 2


def test_stream_faq_returns_validated_items():
    product = _fake_product()

    llm = FakeLLM(
        response_text=(
            '{"faqs":['
            '{"question":"What storage?",'
            '"answer":"256GB."}'
            ']}'
        ),
        stream_chunk_size=10,
    )

    events = asyncio.run(
        _collect(
            content_generation_service
            .stream_faq(
                product=product,
                count=1,
                llm=llm,
            )
        )
    )

    progress_events = [
        event
        for event in events
        if event["type"]
        == "progress"
    ]

    faq_events = [
        event
        for event in events
        if event["type"]
        == "faq"
    ]

    assert len(
        progress_events
    ) > 1

    assert len(
        faq_events
    ) == 1

    assert (
        faq_events[0]["faq"]["answer"]
        == "256GB."
    )

    assert (
        events[-2]["type"]
        == "metadata"
    )

    assert (
        events[-1]["type"]
        == "done"
    )

    assert (
        events[-1]["status"]
        == "completed"
    )

def test_get_owned_product_checks_edit_permission(
    monkeypatch,
):
    product = _fake_product()
    user = SimpleNamespace()

    calls = {
        "get": 0,
        "edit": 0,
    }

    def fake_get_product(
        db,
        product_id,
    ):
        calls["get"] += 1
        return product

    def fake_assert_can_edit(
        found_product,
        found_user,
    ):
        calls["edit"] += 1

        assert found_product is product
        assert found_user is user

    monkeypatch.setattr(
        content_generation_service
        .product_service,
        "get_product",
        fake_get_product,
    )

    monkeypatch.setattr(
        content_generation_service
        .product_service,
        "assert_can_edit",
        fake_assert_can_edit,
    )

    result = (
        content_generation_service
        .get_owned_product(
            db=None,
            product_id=product.id,
            user=user,
        )
    )

    assert result is product
    assert calls["get"] == 1
    assert calls["edit"] == 1


def test_seo_uses_stream_not_generate():
    product = _fake_product()

    llm = FakeLLM(
        response_text=(
            '{"title":"Demo Phone",'
            '"meta_description":'
            '"A demo smartphone."}'
        ),
        stream_chunk_size=8,
    )

    async def forbidden_generate(
        **kwargs,
    ):
        raise AssertionError(
            "SEO endpoint must use stream(), "
            "not generate()."
        )

    llm.generate = forbidden_generate

    events = asyncio.run(
        _collect(
            content_generation_service
            .stream_seo(
                product=product,
                llm=llm,
            )
        )
    )

    assert (
        events[-1]["status"]
        == "completed"
    )

def test_description_persists_generated_content(
    monkeypatch,
):
    product = _fake_product()

    persisted = []

    generated_id = uuid.uuid4()

    def fake_persist(
        db,
        **kwargs,
    ):
        persisted.append(
            kwargs
        )

        return SimpleNamespace(
            id=generated_id
        )

    monkeypatch.setattr(
        content_generation_service,
        "persist_generated_content",
        fake_persist,
    )

    llm = FakeLLM(
        response_text=(
            "Generated description."
        )
    )

    events = asyncio.run(
        _collect(
            content_generation_service
            .stream_description(
                product=product,
                llm=llm,
                db=object(),
            )
        )
    )

    assert len(persisted) == 1

    assert (
        persisted[0]["content_type"]
        == content_generation_service
        .GeneratedContentType
        .DESCRIPTION
    )

    assert persisted[0]["content"] == {
        "text": "Generated description."
    }

    assert (
        events[-2][
            "generated_content_id"
        ]
        == str(generated_id)
    )

def test_seo_persists_validated_content(
    monkeypatch,
):
    product = _fake_product()

    persisted = []

    generated_id = uuid.uuid4()

    def fake_persist(
        db,
        **kwargs,
    ):
        persisted.append(
            kwargs
        )

        return SimpleNamespace(
            id=generated_id
        )

    monkeypatch.setattr(
        content_generation_service,
        "persist_generated_content",
        fake_persist,
    )

    llm = FakeLLM(
        response_text=(
            '{"title":"Demo Phone",'
            '"meta_description":'
            '"A demo smartphone."}'
        )
    )

    asyncio.run(
        _collect(
            content_generation_service
            .stream_seo(
                product=product,
                llm=llm,
                db=object(),
            )
        )
    )

    assert len(persisted) == 1

    assert (
        persisted[0]["content_type"]
        == content_generation_service
        .GeneratedContentType
        .SEO
    )

    assert persisted[0]["content"] == {
        "title": "Demo Phone",
        "meta_description": (
            "A demo smartphone."
        ),
    }

def test_faq_persists_validated_content(
    monkeypatch,
):
    product = _fake_product()

    persisted = []

    generated_id = uuid.uuid4()

    def fake_persist(
        db,
        **kwargs,
    ):
        persisted.append(
            kwargs
        )

        return SimpleNamespace(
            id=generated_id
        )

    monkeypatch.setattr(
        content_generation_service,
        "persist_generated_content",
        fake_persist,
    )

    llm = FakeLLM(
        response_text=(
            '{"faqs":['
            '{"question":"What storage?",'
            '"answer":"256GB."}'
            ']}'
        )
    )

    asyncio.run(
        _collect(
            content_generation_service
            .stream_faq(
                product=product,
                count=1,
                llm=llm,
                db=object(),
            )
        )
    )

    assert len(persisted) == 1

    assert (
        persisted[0]["content_type"]
        == content_generation_service
        .GeneratedContentType
        .FAQ
    )

    assert persisted[0]["content"] == {
        "faqs": [
            {
                "question": (
                    "What storage?"
                ),
                "answer": "256GB.",
            }
        ]
    }
