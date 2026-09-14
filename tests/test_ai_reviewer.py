from types import SimpleNamespace

import pytest

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

    result = service.review_pull_request(
        {
            "repository": "Khumo-Hub/AI-PR-Reviewer-application",
            "pull_request": {"number": 3, "title": "Example"},
            "diff": "diff --git a/app/main.py b/app/main.py",
        }
    )

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
