from fastapi import FastAPI

app = FastAPI(
    title="AI PR Reviewer",
    description="AI-assisted GitHub pull-request review service.",
    version="0.1.0",
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI PR Reviewer is running"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
