import asyncio

import pytest

from app.ai.llm import (
    FakeLLM,
    LLMResult,
    get_llm_provider,
)


def test_fake_llm_returns_configured_response():
    provider = FakeLLM(
        response_text="Recommended product."
    )

    result = asyncio.run(
        provider.generate(
            system_prompt=(
                "You are a shopping assistant."
            ),
            user_prompt="Recommend a phone.",
        )
    )

    assert isinstance(
        result,
        LLMResult,
    )

    assert (
        result.text
        == "Recommended product."
    )

    assert result.model == "fake-llm"


def test_fake_llm_is_deterministic():
    provider = FakeLLM(
        response_text="Same answer."
    )

    first = asyncio.run(
        provider.generate(
            system_prompt="System",
            user_prompt="Question",
        )
    )

    second = asyncio.run(
        provider.generate(
            system_prompt="System",
            user_prompt="Question",
        )
    )

    assert first.text == second.text

    assert (
        first.input_tokens
        == second.input_tokens
    )

    assert (
        first.output_tokens
        == second.output_tokens
    )


def test_fake_llm_records_prompts():
    provider = FakeLLM()

    asyncio.run(
        provider.generate(
            system_prompt="SYSTEM RULES",
            user_prompt="CUSTOMER QUESTION",
        )
    )

    assert len(provider.calls) == 1

    assert (
        provider.calls[0]["system_prompt"]
        == "SYSTEM RULES"
    )

    assert (
        provider.calls[0]["user_prompt"]
        == "CUSTOMER QUESTION"
    )


def test_fake_llm_streams_complete_text():
    provider = FakeLLM(
        response_text="ABCDEFGHIJ",
        stream_chunk_size=4,
    )

    async def collect_events():
        events = []

        async for event in provider.stream(
            system_prompt="System",
            user_prompt="Question",
        ):
            events.append(event)

        return events

    events = asyncio.run(
        collect_events()
    )

    text = "".join(
        event.text
        for event in events
        if not event.done
    )

    assert text == "ABCDEFGHIJ"

    assert events[-1].done is True


def test_factory_returns_fake_llm(
    monkeypatch,
):
    from app.ai import llm

    monkeypatch.setattr(
        llm.settings,
        "llm_provider",
        "fake",
    )

    provider = get_llm_provider()

    assert isinstance(
        provider,
        FakeLLM,
    )


def test_factory_rejects_unknown_provider(
    monkeypatch,
):
    from app.ai import llm

    monkeypatch.setattr(
        llm.settings,
        "llm_provider",
        "unknown-provider",
    )

    with pytest.raises(
        ValueError,
        match="Unknown LLM provider",
    ):
        get_llm_provider()


def test_fake_llm_rejects_invalid_chunk_size():
    with pytest.raises(
        ValueError,
        match="stream_chunk_size",
    ):
        FakeLLM(
            stream_chunk_size=0,
        )
        