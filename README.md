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

The response contains structured pull-request metadata plus the unified diff that will later be passed to the AI review service.

For public repositories, GitHub access can work without authentication subject to API rate limits. For private repositories or higher rate limits, set `GITHUB_TOKEN` in the environment.

For security, the API is deny-by-default: only repositories listed in `ALLOWED_GITHUB_REPOSITORIES` can be fetched. Use a comma-separated list such as `Khumo-Hub/AI-PR-Reviewer-application,owner/another-repo`. Requests for repositories outside the allowlist return HTTP 403 before any GitHub API call is made.

Large pull-request diffs are rejected before the AI-review stage. `MAX_PR_DIFF_BYTES` defaults to 500000 bytes and can be adjusted through the environment.

Copy `.env.example` as a starting point and never commit a real token.

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
