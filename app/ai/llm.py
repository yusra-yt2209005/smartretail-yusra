from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.config import settings

#  The use of AsyncOpenAI and await client.responses.create(...), including stream=True with 
#  asynchronous iteration, matches the current SDK's Responses API pattern.
# ---------------------------------------------------------------------
# Provider result types
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class LLMResult:
    """
    One completed LLM response.

    We keep the generated text together with model/token metadata
    because Week 5 will later persist this information in
    ai_interactions and use it for analytics.
    """

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    # 
    # This is the normalized result returned by any complete LLM call.


@dataclass(frozen=True)
class LLMStreamEvent:
    """
    One piece of a streamed LLM response.

    Normal events contain text.

    The final event has done=True and carries token usage when known.
    """

    text: str = ""
    done: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None

    #This represents one piece of streamed output. The HTTP SSE formatting will be added later in 5.8.”




# ---------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------


class LLMProvider(ABC):
    """
    Common interface for text-generation providers.

    Assistant and merchant-generation code will depend on this
    interface rather than directly depending on OpenAI.
    """

    model_name: str

    # This is the interface the rest of SmartRetail depends on. 
    # It prevents assistant code from being tied directly to OpenAI.

    @abstractmethod
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResult:
        """
        Generate and return one complete response.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[LLMStreamEvent]:
        """
        Generate a response progressively.

        Week 5's SSE endpoint will later consume these events.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------
# Real OpenAI implementation
# ---------------------------------------------------------------------


class OpenAILLMProvider(LLMProvider):
    """
    Real text-generation provider using OpenAI.

    AsyncOpenAI is used because later AI endpoints must not block
    FastAPI's asyncio event loop while waiting for the provider.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:

        # Lazy import:
        # FakeLLM can run without initializing a real OpenAI client.
        from openai import AsyncOpenAI

        self.model_name = (
            model
            or settings.llm_model
        )

        resolved_api_key = (
            api_key
            or settings.openai_api_key
        )

        if not resolved_api_key.strip():
            raise ValueError(
                "OPENAI_API_KEY must be configured "
                "when LLM_PROVIDER=openai"
            )

        self._client = AsyncOpenAI(
            api_key=resolved_api_key,
            timeout=(
                timeout_seconds
                or settings.llm_timeout_seconds
            ),
        )

    async def generate( #his is where the actual real non-streaming provider call happens.
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResult:
        """
        Make one complete OpenAI Responses API request.
        """

        response = await self._client.responses.create(
            model=self.model_name,
            instructions=system_prompt,
            input=user_prompt,
            store=False,
        )

        usage = response.usage

        return LLMResult(
            text=response.output_text,
            model=self.model_name,
            input_tokens=(
                usage.input_tokens
                if usage is not None
                else 0
            ),
            output_tokens=(
                usage.output_tokens
                if usage is not None
                else 0
            ),
        )

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[LLMStreamEvent]:
        """
        Make a streaming OpenAI Responses API request.

        Text deltas are yielded as soon as they arrive.

        A final done event contains usage information.
        """

        stream = await self._client.responses.create(
            model=self.model_name,
            instructions=system_prompt,
            input=user_prompt,
            store=False,
            stream=True,
        )

        async for event in stream:

            if (
                event.type
                == "response.output_text.delta"
            ):
                yield LLMStreamEvent(
                    text=event.delta,
                )

            elif (
                event.type
                == "response.completed"
            ):
                usage = event.response.usage

                yield LLMStreamEvent(
                    done=True,
                    input_tokens=(
                        usage.input_tokens
                        if usage is not None
                        else 0
                    ),
                    output_tokens=(
                        usage.output_tokens
                        if usage is not None
                        else 0
                    ),
                )


# ---------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------

# __init__()  - Configures the fake answer:
# _record_call() - Stores: system_prompt and user_prompt
# _fake_usage() - Creates fake deterministic token counts. These are not real OpenAI token counts.
                    #They're just test data.
# generate() - Returns the canned response.
# stream() - Breaks the same canned response into pieces. No internet. No API key. No credits.

class FakeLLM(LLMProvider):
    """
    Deterministic offline LLM for tests and local development.

    No external network request is made.

    Tests can control exactly what answer is returned and inspect
    which prompts were passed into the provider.
    """

    model_name = "fake-llm"

    def __init__(
        self,
        response_text: str = "Fake LLM response.",
        *,
        stream_chunk_size: int = 12,
    ) -> None:

        if stream_chunk_size <= 0:
            raise ValueError(
                "stream_chunk_size must be greater than 0"
            )

        self.response_text = response_text
        self.stream_chunk_size = stream_chunk_size

        # Later grounding tests can inspect exactly what context and
        # question were sent to the LLM.
        self.calls: list[
            dict[str, str]
        ] = []

    def _record_call(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> None:
        """
        Keep a history of prompts received by the fake provider.
        """

        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )

    def _fake_usage(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[int, int]:
        """
        Produce deterministic fake token counts.

        These are word counts, not real tokenizer counts.
        They exist only so later usage/persistence code can be tested.
        """

        input_tokens = len(
            (
                system_prompt
                + " "
                + user_prompt
            ).split()
        )

        output_tokens = len(
            self.response_text.split()
        )

        return (
            input_tokens,
            output_tokens,
        )

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResult:
        """
        Return the configured fake response immediately.
        """

        self._record_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        input_tokens, output_tokens = (
            self._fake_usage(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        )

        return LLMResult(
            text=self.response_text,
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[LLMStreamEvent]:
        """
        Yield the configured fake response in small deterministic chunks.
        """

        self._record_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        for start in range(
            0,
            len(self.response_text),
            self.stream_chunk_size,
        ):
            yield LLMStreamEvent(
                text=self.response_text[
                    start:
                    start
                    + self.stream_chunk_size
                ]
            )

        input_tokens, output_tokens = (
            self._fake_usage(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        )

        yield LLMStreamEvent(
            done=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------
# This is where provider selection happens.

# settings.llm_provider
#        ↓
#     "fake"?
#        ↓
#     FakeLLM

# or:

# settings.llm_provider
#        ↓
#    "openai"?
#        ↓
# OpenAILLMProvider

def get_llm_provider() -> LLMProvider:
    """
    Return the LLM implementation configured for SmartRetail.

    Configuration comes from app/core/config.py, which loads values
    from the environment.

    FakeLLM is the safe default for development and tests.
    """

    provider_name = (
        settings.llm_provider
        .strip()
        .lower()
    )

    if provider_name == "fake":
        return FakeLLM()

    if provider_name == "openai":
        return OpenAILLMProvider()

    raise ValueError(
        "Unknown LLM provider: "
        f"{settings.llm_provider}"
    )