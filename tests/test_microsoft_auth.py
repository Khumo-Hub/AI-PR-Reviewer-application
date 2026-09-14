import pytest

from app.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService


class FakeApplication:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.scopes = None

    def acquire_token_for_client(self, scopes):
        self.scopes = scopes
        if self.error:
            raise self.error
        return self.result


def test_acquires_graph_token_with_default_scope() -> None:
    application = FakeApplication({"access_token": "token-123"})
    auth = MicrosoftAuthService(application=application)

    token = auth.get_access_token()

    assert token == "token-123"
    assert application.scopes == ["https://graph.microsoft.com/.default"]


@pytest.mark.parametrize(
    ("environment_name", "detail"),
    [
        ("MICROSOFT_TENANT_ID", "Microsoft tenant ID is not configured"),
        ("MICROSOFT_CLIENT_ID", "Microsoft client ID is not configured"),
        ("MICROSOFT_CLIENT_SECRET", "Microsoft client secret is not configured"),
    ],
)
def test_missing_microsoft_credentials(monkeypatch, environment_name: str, detail: str) -> None:
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "tenant")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "client")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "secret")
    monkeypatch.delenv(environment_name, raising=False)

    with pytest.raises(MicrosoftAuthError) as exc_info:
        MicrosoftAuthService()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == detail


def test_authentication_error_response_is_rejected() -> None:
    application = FakeApplication({"error": "invalid_client", "error_description": "bad secret"})
    auth = MicrosoftAuthService(application=application)

    with pytest.raises(MicrosoftAuthError) as exc_info:
        auth.get_access_token()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Microsoft authentication failed"


def test_authentication_transport_failure_is_mapped() -> None:
    application = FakeApplication(error=RuntimeError("identity provider unavailable"))
    auth = MicrosoftAuthService(application=application)

    with pytest.raises(MicrosoftAuthError) as exc_info:
        auth.get_access_token()

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Unable to acquire a Microsoft Graph access token"
