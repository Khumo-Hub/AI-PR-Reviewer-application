# AI PR Reviewer Application

An AI-assisted pull-request review application that connects GitHub, OpenAI, and Microsoft Outlook.

## Goal

When a GitHub pull request is opened or updated, the application will be able to:

- retrieve the pull-request metadata and code changes;
- analyse the changes with an AI reviewer;
- identify risks, bugs, and missing tests;
- produce a structured review and merge recommendation; and
- send or draft an Outlook email containing the review summary.

## Planned stack

- Python
- FastAPI
- GitHub API and webhooks
- OpenAI API
- Microsoft Graph / Outlook
- Pytest
- GitHub Actions

## Current API

### Health check

`GET /health`

### Retrieve a GitHub pull request

`GET /github/pull-requests/{owner}/{repo}/{pr_number}`

The response contains structured pull-request metadata plus the unified diff.

### Generate an AI pull-request review

`POST /reviews/{owner}/{repo}/{pr_number}`

This endpoint retrieves the pull request from GitHub and sends the metadata and diff to the OpenAI Responses API. The response contains a structured review with:

- summary;
- risk level;
- concrete issues;
- missing tests; and
- a recommendation: `approve`, `changes_requested`, or `manual_review`.

Set `OPENAI_API_KEY` in the environment. `OPENAI_MODEL` optionally overrides the default model.

For public repositories, GitHub access can work without authentication subject to API rate limits. For private repositories or higher rate limits, set `GITHUB_TOKEN` in the environment.

For security, the API is deny-by-default: only repositories listed in `ALLOWED_GITHUB_REPOSITORIES` can be fetched. Use a comma-separated list such as `Khumo-Hub/AI-PR-Reviewer-application,owner/another-repo`. Requests for repositories outside the allowlist return HTTP 403 before any GitHub API call is made.

Large pull-request diffs are rejected before the AI-review stage. `MAX_PR_DIFF_BYTES` defaults to 500000 bytes and can be adjusted through the environment.

Pull-request content is treated as untrusted data in the AI-review prompt so instructions embedded in source code or comments are not treated as application instructions.

Copy `.env.example` as a starting point and never commit real credentials.

## Development workflow

The application is developed through feature branches and pull requests rather than committing features directly to `main`.

### Roadmap

1. FastAPI application foundation and health endpoint
2. GitHub pull-request integration
3. AI pull-request review service
4. Outlook email integration
5. GitHub Actions and automated tests
6. GitHub webhook automation
7. Optional review dashboard
