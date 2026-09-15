import pytest

from app.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService


class FakeApplication:
    def __init__(self) -> None:
        self.accounts = [{"username": "reviewer@example.com"}]
        self.silent_result = {"access_token": "token-123"}
        self.flow = {
            "auth_uri": "https://login.microsoftonline.com/authorize",
            "state": "state-123",
        }
        self.complete_result = {
            "access_token": "token-456",
            "id_token_claims": {"preferred_username": "reviewer@example.com"},
        }
        self.scopes = None
        self.account = None
        self.auth_response = None

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        self.scopes = scopes
        self.account = account
        return self.silent_result

    def initiate_auth_code_flow(self, scopes, redirect_uri, prompt):
        self.scopes = scopes
        assert redirect_uri == "https://example.test/microsoft/callback"
        assert prompt == "select_account"
        return self.flow

    def acquire_token_by_auth_code_flow(self, flow, auth_response):
        assert flow == self.flow
        self.auth_response = auth_response
        return self.complete_result


def test_silent_token_uses_delegated_mail_scope() -> None:
    application = FakeApplication()
    auth = MicrosoftAuthService(application=application)

    token = auth.get_access_token()

    assert token == "token-123"
    assert application.scopes == ["Mail.ReadWrite"]
    assert application.account == {"username": "reviewer@example.com"}


def test_missing_connected_account_requires_authorization() -> None:
    application = FakeApplication()
    application.accounts = []
    auth = MicrosoftAuthService(application=application)

    with pytest.raises(MicrosoftAuthError) as exc_info:
        auth.get_access_token()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Microsoft mailbox is not connected"


def test_begin_authorization_requires_redirect_uri() -> None:
    auth = MicrosoftAuthService(application=FakeApplication())

    with pytest.raises(MicrosoftAuthError) as exc_info:
        auth.begin_authorization()

    assert exc_info.value.detail == "Microsoft redirect URI is not configured"


def test_begin_and_complete_authorization() -> None:
    application = FakeApplication()
    auth = MicrosoftAuthService(
        application=application,
        redirect_uri="https://example.test/microsoft/callback",
    )

    flow = auth.begin_authorization()
    result = auth.complete_authorization(flow, {"state": "state-123", "code": "code-123"})

    assert flow["state"] == "state-123"
    assert result == {"connected": True, "account": "reviewer@example.com"}
    assert application.auth_response["code"] == "code-123"


def test_silent_refresh_failure_requires_authorization() -> None:
    application = FakeApplication()
    application.silent_result = {"error": "interaction_required"}
    auth = MicrosoftAuthService(application=application)

    with pytest.raises(MicrosoftAuthError) as exc_info:
        auth.get_access_token()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Microsoft mailbox authorization is required"


def test_connection_status_reports_account() -> None:
    auth = MicrosoftAuthService(application=FakeApplication())

    assert auth.connection_status() == {
        "connected": True,
        "account": "reviewer@example.com",
    }
