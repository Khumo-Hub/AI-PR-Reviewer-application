import hmac
import logging
import os

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from app.ai_reviewer import AIReviewService, AIReviewerError
from app.github_service import GitHubService, GitHubServiceError
from app.outlook_service import OutlookService, OutlookServiceError
from app.webhook_service import (
    SUPPORTED_PULL_REQUEST_ACTIONS,
    parse_webhook_payload,
    tracker,
    verify_github_signature,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI PR Reviewer",
    description="AI-assisted GitHub pull-request review service.",
    version="0.6.0",
)


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


def run_review_and_create_draft(repository: str, pr_number: int) -> None:
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
        outlook.create_review_draft(review_payload)
    except (GitHubServiceError, AIReviewerError, OutlookServiceError) as exc:
        logger.error(
            "Webhook review failed for %s PR #%s: %s",
            repository,
            pr_number,
            exc,
        )
    except Exception:
        logger.exception("Unexpected webhook review failure for %s PR #%s", repository, pr_number)
    finally:
        if github is not None:
            github.close()
        if ai is not None:
            ai.close()
        if outlook is not None:
            outlook.close()


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI PR Reviewer is running"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/github/pull-requests/{owner}/{repo}/{pr_number}")
def get_pull_request(owner: str, repo: str, pr_number: int) -> dict:
    if pr_number < 1:
        raise HTTPException(status_code=422, detail="Pull request number must be positive")

    repository = validate_repository(owner, repo)
    github = GitHubService()
    try:
        return github.get_pull_request_review_input(repository, pr_number)
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
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
    github = GitHubService()
    ai = None
    try:
        review_input = github.get_pull_request_review_input(repository, pr_number)
        ai = AIReviewService()
        review = ai.review_pull_request(review_input)
        return build_review_payload(repository, review_input, review)
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except AIReviewerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
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
    github = GitHubService()
    ai = None
    outlook = None
    try:
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
    is_draft = pull_request.get("draft", False)

    if not isinstance(repository, str) or not isinstance(pr_number, int) or pr_number < 1:
        raise HTTPException(status_code=400, detail="Invalid pull request webhook payload")

    validate_repository_name(repository)

    if is_draft:
        return {"status": "draft_ignored"}

    background_tasks.add_task(run_review_and_create_draft, repository, pr_number)
    return {"status": "review_scheduled"}
