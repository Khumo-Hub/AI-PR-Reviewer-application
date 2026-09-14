from types import SimpleNamespace

import pytest
from openai import APIConnectionError, APIStatusError

from app.ai_reviewer import AIReviewResult, AIReviewService, AIReviewerError


class FakeResponses:
    def __init__(self, parsed_review: AIReviewResult) -> None:
        self.parsed_review = parsed_review
        self.last_kwargs = None

    def parse(self, **kwargs):
        self.last_kwargs = kwargs
        content = SimpleNamespace(type="output_text", parsed=self.parsed_review)
        message = SimpleNamespace(type="message", content=[content])
        return SimpleNamespace(output=[message])


class FakeOpenAIClient:
    def __init__(self, parsed_review: AIReviewResult) -> None:
        self.responses = FakeResponses(parsed_review)


class RaisingResponses:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def parse(self, **kwargs):
        raise self.error


class RaisingOpenAIClient:
    def __init__(self, error: Exception) -> None:
        self.responses = RaisingResponses(error)


def sample_input() -> dict:
    return {
        "repository": "Khumo-Hub/AI-PR-Reviewer-application",
        "pull_request": {"number": 3, "title": "Example"},
        "diff": "diff --git a/app/main.py b/app/main.py",
    }


def test_structured_ai_review() -> None:
    parsed_review = AIReviewResult(
        summary="Adds a secure endpoint.",
        risk="low",
        issues=[],
        tests_missing=[],
        recommendation="approve",
    )
    client = FakeOpenAIClient(parsed_review)
    service = AIReviewService(client=client, model="test-model")

    result = service.review_pull_request(sample_input())

    assert result.recommendation == "approve"
    assert result.risk == "low"
    assert client.responses.last_kwargs["model"] == "test-model"
    assert client.responses.last_kwargs["text_format"] is AIReviewResult
    assert "BEGIN UNTRUSTED PR DIFF" in client.responses.last_kwargs["input"]


def test_missing_openai_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(AIReviewerError) as exc_info:
        AIReviewService()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "OpenAI API key is not configured"


def test_openai_connection_failure_maps_to_bad_gateway() -> None:
    client = RaisingOpenAIClient(APIConnectionError(request=None))
    service = AIReviewService(client=client, model="test-model")

    with pytest.raises(AIReviewerError) as exc_info:
        service.review_pull_request(sample_input())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to reach the OpenAI API"


@pytest.mark.parametrize(
    ("status_code", "expected_status", "expected_detail"),
    [
        (401, 503, "OpenAI API authentication or permissions failed"),
        (403, 503, "OpenAI API authentication or permissions failed"),
        (429, 503, "OpenAI API rate limit exceeded"),
        (500, 502, "OpenAI API request failed"),
    ],
)
def test_openai_status_errors_are_mapped(
    status_code: int,
    expected_status: int,
    expected_detail: str,
) -> None:
    response = SimpleNamespace(status_code=status_code, request=None)
    error = APIStatusError(
        message="failure",
        response=response,
        body=None,
    )
    client = RaisingOpenAIClient(error)
    service = AIReviewService(client=client, model="test-model")

    with pytest.raises(AIReviewerError) as exc_info:
        service.review_pull_request(sample_input())

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == expected_detail


def test_missing_structured_output_is_rejected() -> None:
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(output=[])
        )
    )
    service = AIReviewService(client=client, model="test-model")

    with pytest.raises(AIReviewerError) as exc_info:
        service.review_pull_request(sample_input())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "OpenAI API returned no structured review"
