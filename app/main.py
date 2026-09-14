import os

from fastapi import FastAPI, HTTPException

from app.ai_reviewer import AIReviewService, AIReviewerError
from app.github_service import GitHubService, GitHubServiceError

app = FastAPI(
    title="AI PR Reviewer",
    description="AI-assisted GitHub pull-request review service.",
    version="0.3.0",
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
def review_pull_request(owner: str, repo: str, pr_number: int) -> dict:
    if pr_number < 1:
        raise HTTPException(status_code=422, detail="Pull request number must be positive")

    repository = validate_repository(owner, repo)
    github = GitHubService()
    ai = None
    try:
        review_input = github.get_pull_request_review_input(repository, pr_number)
        ai = AIReviewService()
        review = ai.review_pull_request(review_input)
        return {
            "repository": repository,
            "pull_request": review_input["pull_request"],
            "review": review.model_dump(),
        }
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except AIReviewerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        github.close()
        if ai is not None:
            ai.close()
