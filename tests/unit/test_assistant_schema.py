import pytest
from pydantic import ValidationError

from app.schemas.assistant import (
    AssistantRequest,
)


def test_question_is_trimmed():
    request = AssistantRequest(
        question="  Samsung phone  "
    )

    assert request.question == "Samsung phone"


def test_whitespace_only_question_is_rejected():
    with pytest.raises(
        ValidationError
    ):
        AssistantRequest(
            question="     "
        )


def test_question_with_null_character_is_rejected():
    with pytest.raises(
        ValidationError
    ):
        AssistantRequest(
            question="Samsung\x00phone"
        )


def test_question_over_max_length_is_rejected():
    with pytest.raises(
        ValidationError
    ):
        AssistantRequest(
            question="a" * 501
        )

