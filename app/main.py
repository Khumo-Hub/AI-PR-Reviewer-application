import hmac
import os

from fastapi import FastAPI, Header, HTTPException

from app.ai_reviewer import AIReviewService, AIReviewerError
from app.github_service import GitHubService, GitHubServiceError
from app.outlook_service import OutlookService, OutlookServiceError

app = FastAPI(
    title="AI PR Reviewer",
    description="AI-assisted GitHub pull-request review service.",
    version="0.4.0",
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
        raise HTTPException(
            status_code=403,
            detail="Repository is not allowed for review",
        )
    return repository


def validate_review_api_key(api_key: str | None) -> None:
    configured_api_key = os.getenv("REVIEW_API_KEY")
    if not configured_api_key:
        raise HTTPException(
            status_code=503,
            detail="Review API key is not configured",
        )

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
        return {
            **review_payload,
            "outlook_draft": draft,
        }
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
