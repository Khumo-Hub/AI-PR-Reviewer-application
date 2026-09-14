from __future__ import annotations

import os
from typing import Any

import msal


class MicrosoftAuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class MicrosoftAuthService:
    GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        application: Any | None = None,
    ) -> None:
        if application is not None:
            self.application = application
            return

        resolved_tenant_id = tenant_id or os.getenv("MICROSOFT_TENANT_ID")
        resolved_client_id = client_id or os.getenv("MICROSOFT_CLIENT_ID")
        resolved_client_secret = client_secret or os.getenv("MICROSOFT_CLIENT_SECRET")

        if not resolved_tenant_id:
            raise MicrosoftAuthError(503, "Microsoft tenant ID is not configured")
        if not resolved_client_id:
            raise MicrosoftAuthError(503, "Microsoft client ID is not configured")
        if not resolved_client_secret:
            raise MicrosoftAuthError(503, "Microsoft client secret is not configured")

        authority = f"https://login.microsoftonline.com/{resolved_tenant_id}"
        self.application = msal.ConfidentialClientApplication(
            resolved_client_id,
            authority=authority,
            client_credential=resolved_client_secret,
        )

    def get_access_token(self) -> str:
        try:
            result = self.application.acquire_token_for_client(scopes=self.GRAPH_SCOPE)
        except Exception as exc:
            raise MicrosoftAuthError(
                502,
                "Unable to acquire a Microsoft Graph access token",
            ) from exc

        if not isinstance(result, dict):
            raise MicrosoftAuthError(503, "Microsoft authentication failed")

        access_token = result.get("access_token")
        if not access_token:
            raise MicrosoftAuthError(503, "Microsoft authentication failed")

        return access_token
