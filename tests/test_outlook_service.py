import httpx
import pytest

from app.microsoft_auth import MicrosoftAuthError
from app.outlook_service import OutlookService, OutlookServiceError, format_review_email


class FakeAuthService:
    def __init__(self, token: str = "test-token", error: MicrosoftAuthError | None = None) -> None:
        self.token = token
        self.error = error
        self.calls = 0

    def get_access_token(self) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        return self.token


def review_payload() -> dict:
    return {
        "repository": "Khumo-Hub/AI-PR-Reviewer-application",
        "pull_request": {
            "number": 4,
            "title": "Outlook integration",
            "url": "https://github.com/Khumo-Hub/AI-PR-Reviewer-application/pull/4",
        },
        "review": {
            "summary": "Adds Outlook draft creation.",
            "risk": "low",
            "issues": [{
                "severity": "medium",
                "title": "Example issue",
                "detail": "Something to review.",
                "recommendation": "Check it.",
                "file": "app/main.py",
            }],
            "tests_missing": ["Add an integration test."],
            "recommendation": "manual_review",
        },
    }


def test_format_review_email() -> None:
    subject, body = format_review_email(review_payload())
    assert "#4" in subject
    assert "manual_review" in subject
    assert "Adds Outlook draft creation." in body
    assert "Example issue" in body
    assert "Add an integration test." in body
    assert "saved as a draft" in body


def test_create_review_draft_uses_me_endpoint_and_delegated_token() -> None:
    auth = FakeAuthService()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.0/me/messages"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(201, json={
            "id": "draft-123",
            "subject": "PR Review",
            "isDraft": True,
            "webLink": "https://outlook.office.com/draft-123",
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        outlook = OutlookService(
            recipient="reviewer@example.com",
            auth_service=auth,
            client=client,
            base_url="https://graph.microsoft.test/v1.0",
        )
        result = outlook.create_review_draft(review_payload())

    assert auth.calls == 1
    assert result["id"] == "draft-123"
    assert result["is_draft"] is True
    assert result["recipient"] == "reviewer@example.com"


def test_missing_recipient(monkeypatch) -> None:
    monkeypatch.delenv("OUTLOOK_REVIEW_RECIPIENT", raising=False)
    with pytest.raises(OutlookServiceError) as exc_info:
        OutlookService(auth_service=FakeAuthService())
    assert exc_info.value.detail == "Outlook review recipient is not configured"


def test_auth_failure_is_mapped() -> None:
    auth = FakeAuthService(error=MicrosoftAuthError(503, "Microsoft mailbox authorization is required"))
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        outlook = OutlookService(
            recipient="reviewer@example.com",
            auth_service=auth,
            client=client,
        )
        with pytest.raises(OutlookServiceError) as exc_info:
            outlook.create_review_draft(review_payload())
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Microsoft mailbox authorization is required"


@pytest.mark.parametrize(
    ("status_code", "expected_detail"),
    [
        (401, "Microsoft Graph authentication failed"),
        (403, "Microsoft Graph Mail.ReadWrite delegated permission is required"),
        (429, "Microsoft Graph rate limit exceeded"),
        (500, "Microsoft Graph draft creation failed"),
    ],
)
def test_graph_error_responses(status_code: int, expected_detail: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        outlook = OutlookService(
            recipient="reviewer@example.com",
            auth_service=FakeAuthService(),
            client=client,
            base_url="https://graph.microsoft.test/v1.0",
        )
        with pytest.raises(OutlookServiceError) as exc_info:
            outlook.create_review_draft(review_payload())
    assert exc_info.value.detail == expected_detail


def test_graph_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        outlook = OutlookService(
            recipient="reviewer@example.com",
            auth_service=FakeAuthService(),
            client=client,
        )
        with pytest.raises(OutlookServiceError) as exc_info:
            outlook.create_review_draft(review_payload())
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to reach Microsoft Graph"


@pytest.mark.parametrize(
    "response_json",
    [
        {},
        {"id": "draft-123"},
        {"id": "draft-123", "isDraft": False},
        {"id": "", "isDraft": True},
    ],
)
def test_invalid_draft_response_is_rejected(response_json: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=response_json)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        outlook = OutlookService(
            recipient="reviewer@example.com",
            auth_service=FakeAuthService(),
            client=client,
        )
        with pytest.raises(OutlookServiceError) as exc_info:
            outlook.create_review_draft(review_payload())
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Microsoft Graph returned an invalid draft response"
