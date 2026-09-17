import hmac
import logging
import os
import threading
import time

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from app.ai_reviewer import AIReviewService, AIReviewerError
from app.github_service import GitHubService, GitHubServiceError
from app.microsoft_auth import MicrosoftAuthError, MicrosoftAuthService
from app.outlook_service import OutlookService, OutlookServiceError
from app.ui_v2 import portfolio_page
from app.webhook_service import (
    SUPPORTED_PULL_REQUEST_ACTIONS,
    parse_webhook_payload,
    review_tracker,
    tracker,
    verify_github_signature,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI PR Reviewer",
    description="AI-assisted GitHub pull-request review service.",
    version="0.8.0",
)

_microsoft_flow_lock = threading.Lock()
_microsoft_flows: dict[str, tuple[dict, float]] = {}
_MICROSOFT_FLOW_TTL_SECONDS = 600


def allowed_github_repositories() -> set[str]:
    configured = os.getenv("ALLOWED_GITHUB_REPOSITORIES", "")
    return {
        repository.strip().lower()
        for repository in configured.split(",")
        if repository.strip()
    }


def validate_repository(owner: str, repo: str) -> str:
    repository = f"{owner}/{repo}"
    if repository.lower() not in allowed_github_repositories():
        raise HTTPException(status_code=403, detail="Repository is not allowed for review")
    return repository


def validate_repository_name(repository: str) -> str:
    if repository.lower() not in allowed_github_repositories():
        raise HTTPException(status_code=403, detail="Repository is not allowed for review")
    return repository


def validate_review_api_key(api_key: str | None) -> None:
    configured_api_key = os.getenv("REVIEW_API_KEY")
    if not configured_api_key:
        raise HTTPException(status_code=503, detail="Review API key is not configured")

    if api_key is None or not hmac.compare_digest(api_key, configured_api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing review API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def build_review_payload(repository: str, review_input: dict, review) -> dict:
    return {
        "repository": repository,
        "pull_request": review_input["pull_request"],
        "review": review.model_dump(),
    }


def _store_microsoft_flow(flow: dict) -> None:
    state = flow["state"]
    expires_at = time.monotonic() + _MICROSOFT_FLOW_TTL_SECONDS
    with _microsoft_flow_lock:
        now = time.monotonic()
        expired = [key for key, (_, expiry) in _microsoft_flows.items() if expiry <= now]
        for key in expired:
            _microsoft_flows.pop(key, None)
        _microsoft_flows[state] = (flow, expires_at)


def _pop_microsoft_flow(state: str | None) -> dict:
    if not state:
        raise HTTPException(status_code=400, detail="Missing Microsoft OAuth state")
    with _microsoft_flow_lock:
        entry = _microsoft_flows.pop(state, None)
    if entry is None:
        raise HTTPException(status_code=400, detail="Invalid or expired Microsoft OAuth state")
    flow, expires_at = entry
    if expires_at <= time.monotonic():
        raise HTTPException(status_code=400, detail="Invalid or expired Microsoft OAuth state")
    return flow


def run_review_and_create_draft(
    repository: str,
    pr_number: int,
    expected_head_sha: str,
) -> None:
    github = None
    ai = None
    outlook = None
    completed = False
    try:
        github = GitHubService()
        review_input = github.get_pull_request_review_input(repository, pr_number)
        current_head_sha = review_input.get("pull_request", {}).get("head_sha")
        if current_head_sha != expected_head_sha:
            logger.info(
                "Skipping stale webhook review for %s PR #%s: expected head %s, current head %s",
                repository,
                pr_number,
                expected_head_sha,
                current_head_sha,
            )
            return

        ai = AIReviewService()
        review = ai.review_pull_request(review_input)
        review_payload = build_review_payload(repository, review_input, review)
        outlook = OutlookService()
        outlook.create_review_draft(review_payload)
        review_tracker.mark_completed(repository, pr_number, expected_head_sha)
        completed = True
        logger.info(
            "Webhook review completed for %s PR #%s at head %s",
            repository,
            pr_number,
            expected_head_sha,
        )
    except (GitHubServiceError, AIReviewerError, OutlookServiceError) as exc:
        logger.error(
            "Webhook review failed for %s PR #%s at head %s: %s",
            repository,
            pr_number,
            expected_head_sha,
            exc,
        )
    except Exception:
        logger.exception(
            "Unexpected webhook review failure for %s PR #%s at head %s",
            repository,
            pr_number,
            expected_head_sha,
        )
    finally:
        if not completed:
            review_tracker.discard(repository, pr_number, expected_head_sha)
        if github is not None:
            github.close()
        if ai is not None:
            ai.close()
        if outlook is not None:
            outlook.close()


@app.get("/", include_in_schema=False)
def root():
    return portfolio_page()


@app.get("/app", include_in_schema=False)
def portfolio_app():
    return portfolio_page()


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/microsoft/connect")
def connect_microsoft_mailbox(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, str]:
    validate_review_api_key(x_api_key)
    try:
        auth = MicrosoftAuthService()
        flow = auth.begin_authorization()
        _store_microsoft_flow(flow)
        return {"authorization_url": flow["auth_uri"]}
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/microsoft/callback")
def microsoft_oauth_callback(request: Request) -> dict:
    state = request.query_params.get("state")
    flow = _pop_microsoft_flow(state)
    try:
        auth = MicrosoftAuthService()
        result = auth.complete_authorization(flow, dict(request.query_params))
        return {
            **result,
            "message": "Microsoft mailbox connected. You can return to the AI PR Reviewer application.",
        }
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/microsoft/status")
def microsoft_connection_status(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    validate_review_api_key(x_api_key)
    try:
        auth = MicrosoftAuthService()
        return auth.connection_status()
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/github/pull-requests/{owner}/{repo}/{pr_number}")
def get_pull_request(owner: str, repo: str, pr_number: int) -> dict:
    if pr_number < 1:
        raise HTTPException(status_code=422, detail="Pull request number must be positive")

    repository = validate_repository(owner, repo)
    github = None
    try:
        github = GitHubService()
        return github.get_pull_request_review_input(repository, pr_number)
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        if github is not None:
            github.close()


@app.post("/reviews/{owner}/{repo}/{pr_number}")
def review_pull_request(
    owner: str,
    repo: str,
    pr_number: int,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    validate_review_api_key(x_api_key)

    if pr_number < 1:
        raise HTTPException(status_code=422, detail="Pull request number must be positive")

    repository = validate_repository(owner, repo)
    github = None
    ai = None
    try:
        github = GitHubService()
        review_input = github.get_pull_request_review_input(repository, pr_number)
        ai = AIReviewService()
        review = ai.review_pull_request(review_input)
        return build_review_payload(repository, review_input, review)
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except AIReviewerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        if github is not None:
            github.close()
        if ai is not None:
            ai.close()


@app.post("/reviews/{owner}/{repo}/{pr_number}/outlook-draft")
def create_outlook_review_draft(
    owner: str,
    repo: str,
    pr_number: int,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    validate_review_api_key(x_api_key)

    if pr_number < 1:
        raise HTTPException(status_code=422, detail="Pull request number must be positive")

    repository = validate_repository(owner, repo)
    github = None
    ai = None
    outlook = None
    try:
        github = GitHubService()
        review_input = github.get_pull_request_review_input(repository, pr_number)
        ai = AIReviewService()
        review = ai.review_pull_request(review_input)
        review_payload = build_review_payload(repository, review_input, review)

        outlook = OutlookService()
        draft = outlook.create_review_draft(review_payload)
        return {**review_payload, "outlook_draft": draft}
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except AIReviewerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except OutlookServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        if github is not None:
            github.close()
        if ai is not None:
            ai.close()
        if outlook is not None:
            outlook.close()


@app.post("/webhooks/github", status_code=202)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
) -> dict[str, str]:
    body = await request.body()
    verify_github_signature(body, x_hub_signature_256)

    if not x_github_delivery:
        raise HTTPException(status_code=400, detail="Missing GitHub delivery ID")

    if not tracker.register(x_github_delivery):
        return {"status": "duplicate_ignored"}

    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event != "pull_request":
        return {"status": "event_ignored"}

    payload = parse_webhook_payload(body)
    action = payload.get("action")
    if action not in SUPPORTED_PULL_REQUEST_ACTIONS:
        return {"status": "action_ignored"}

    repository = payload.get("repository", {}).get("full_name")
    pull_request = payload.get("pull_request", {})
    pr_number = pull_request.get("number")
    head_sha = pull_request.get("head", {}).get("sha")
    is_draft = pull_request.get("draft", False)

    if (
        not isinstance(repository, str)
        or not isinstance(pr_number, int)
        or pr_number < 1
        or not isinstance(head_sha, str)
        or not head_sha
    ):
        raise HTTPException(status_code=400, detail="Invalid pull request webhook payload")

    validate_repository_name(repository)

    if is_draft:
        return {"status": "draft_ignored"}

    if not review_tracker.register(repository, pr_number, head_sha):
        return {"status": "review_already_scheduled"}

    background_tasks.add_task(
        run_review_and_create_draft,
        repository,
        pr_number,
        head_sha,
    )
    return {"status": "review_scheduled"}
