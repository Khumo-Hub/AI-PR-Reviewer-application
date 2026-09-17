from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import msal

from app.persistence import StateStore, StateStoreError, build_state_store


class MicrosoftAuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


_cache_lock = threading.Lock()
_MICROSOFT_CACHE_KEY = "microsoft_msal_token_cache"


class MicrosoftAuthService:
    GRAPH_SCOPES = ["Mail.ReadWrite"]

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        authority: str | None = None,
        redirect_uri: str | None = None,
        cache_path: str | None = None,
        application: Any | None = None,
        cache: Any | None = None,
        state_store: StateStore | None = None,
    ) -> None:
        self.redirect_uri = redirect_uri or os.getenv("MICROSOFT_REDIRECT_URI")
        self.cache_path = cache_path or os.getenv(
            "MICROSOFT_TOKEN_CACHE_PATH",
            ".data/msal_token_cache.json",
        )
        try:
            self.state_store = state_store if state_store is not None else build_state_store()
        except StateStoreError as exc:
            raise MicrosoftAuthError(503, "Unable to initialize Microsoft token persistence") from exc

        if application is not None:
            self.application = application
            self.cache = cache
            return

        resolved_client_id = client_id or os.getenv("MICROSOFT_CLIENT_ID")
        resolved_client_secret = client_secret or os.getenv("MICROSOFT_CLIENT_SECRET")
        resolved_authority = authority or os.getenv(
            "MICROSOFT_AUTHORITY",
            "https://login.microsoftonline.com/common",
        )

        if not resolved_client_id:
            raise MicrosoftAuthError(503, "Microsoft client ID is not configured")
        if not resolved_client_secret:
            raise MicrosoftAuthError(503, "Microsoft client secret is not configured")

        self.cache = cache or msal.SerializableTokenCache()
        self._load_cache()
        self.application = msal.ConfidentialClientApplication(
            resolved_client_id,
            authority=resolved_authority,
            client_credential=resolved_client_secret,
            token_cache=self.cache,
        )

    def _load_cache(self) -> None:
        if self.cache is None:
            return

        if self.state_store is not None:
            try:
                serialized = self.state_store.get(_MICROSOFT_CACHE_KEY)
            except StateStoreError as exc:
                raise MicrosoftAuthError(503, "Unable to load Microsoft token cache") from exc
            if serialized:
                try:
                    self.cache.deserialize(serialized)
                except ValueError as exc:
                    raise MicrosoftAuthError(503, "Unable to load Microsoft token cache") from exc
            return

        if not self.cache_path:
            return
        path = Path(self.cache_path)
        if not path.exists():
            return
        try:
            serialized = path.read_text(encoding="utf-8")
            if serialized:
                self.cache.deserialize(serialized)
        except (OSError, ValueError) as exc:
            raise MicrosoftAuthError(503, "Unable to load Microsoft token cache") from exc

    def _persist_cache(self) -> None:
        if self.cache is None or not hasattr(self.cache, "serialize"):
            return

        serialized = self.cache.serialize()
        if self.state_store is not None:
            try:
                with _cache_lock:
                    self.state_store.set(_MICROSOFT_CACHE_KEY, serialized)
            except StateStoreError as exc:
                raise MicrosoftAuthError(503, "Unable to persist Microsoft token cache") from exc
            return

        if not self.cache_path:
            return
        path = Path(self.cache_path)
        try:
            with _cache_lock:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    delete=False,
                ) as temporary:
                    temporary.write(serialized)
                    temp_name = temporary.name
                os.chmod(temp_name, 0o600)
                os.replace(temp_name, path)
        except OSError as exc:
            raise MicrosoftAuthError(503, "Unable to persist Microsoft token cache") from exc

    def begin_authorization(self) -> dict[str, Any]:
        if not self.redirect_uri:
            raise MicrosoftAuthError(503, "Microsoft redirect URI is not configured")
        try:
            flow = self.application.initiate_auth_code_flow(
                scopes=self.GRAPH_SCOPES,
                redirect_uri=self.redirect_uri,
                prompt="select_account",
            )
        except Exception as exc:
            raise MicrosoftAuthError(502, "Unable to start Microsoft authorization") from exc

        if not isinstance(flow, dict) or not flow.get("auth_uri") or not flow.get("state"):
            raise MicrosoftAuthError(502, "Microsoft authorization could not be started")
        return flow

    def complete_authorization(
        self,
        flow: dict[str, Any],
        auth_response: dict[str, str],
    ) -> dict[str, Any]:
        try:
            result = self.application.acquire_token_by_auth_code_flow(flow, auth_response)
        except ValueError as exc:
            raise MicrosoftAuthError(400, "Invalid Microsoft authorization response") from exc
        except Exception as exc:
            raise MicrosoftAuthError(502, "Unable to complete Microsoft authorization") from exc

        if not isinstance(result, dict) or not result.get("access_token"):
            raise MicrosoftAuthError(401, "Microsoft authorization was not completed")

        self._persist_cache()
        claims = result.get("id_token_claims") or {}
        username = claims.get("preferred_username") or claims.get("email")
        return {
            "connected": True,
            "account": username,
        }

    def connection_status(self) -> dict[str, Any]:
        try:
            accounts = self.application.get_accounts()
        except Exception as exc:
            raise MicrosoftAuthError(502, "Unable to read Microsoft account state") from exc

        account = accounts[0] if accounts else None
        username = account.get("username") if isinstance(account, dict) else None
        return {
            "connected": bool(account),
            "account": username,
        }

    def get_access_token(self) -> str:
        try:
            accounts = self.application.get_accounts()
        except Exception as exc:
            raise MicrosoftAuthError(502, "Unable to read Microsoft account state") from exc

        if not accounts:
            raise MicrosoftAuthError(503, "Microsoft mailbox is not connected")

        try:
            result = self.application.acquire_token_silent(
                scopes=self.GRAPH_SCOPES,
                account=accounts[0],
            )
        except Exception as exc:
            raise MicrosoftAuthError(
                502,
                "Unable to acquire a Microsoft Graph access token",
            ) from exc

        self._persist_cache()
        if not isinstance(result, dict) or not result.get("access_token"):
            raise MicrosoftAuthError(503, "Microsoft mailbox authorization is required")

        return result["access_token"]
