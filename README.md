# AI PR Reviewer Application

An AI-assisted pull-request review application that connects GitHub, OpenAI, and Microsoft Outlook.

## Goal

When a GitHub pull request is opened or updated, the application can retrieve the pull-request metadata and code changes, analyse them with an AI reviewer, identify risks and missing tests, produce a structured recommendation, and save the review as an Outlook draft for human approval.

## Stack

- Python / FastAPI
- GitHub API and webhooks
- OpenAI API
- Microsoft Graph / Outlook
- Pytest
- GitHub Actions
- Render

## Current API

### Health check

`GET /health`

### Retrieve a GitHub pull request

`GET /github/pull-requests/{owner}/{repo}/{pr_number}`

### Generate an AI pull-request review

`POST /reviews/{owner}/{repo}/{pr_number}`

This endpoint is protected by `REVIEW_API_KEY`, supplied through the `X-API-Key` header.

### Connect a Microsoft mailbox

`POST /microsoft/connect`

This protected endpoint starts the delegated Microsoft OAuth authorization-code flow and returns an `authorization_url`. Open that URL in a browser, sign in to the Microsoft account whose mailbox should be used, and consent to delegated `Mail.ReadWrite` access.

Microsoft redirects back to:

`GET /microsoft/callback`

The callback validates the OAuth state, completes the authorization-code flow, and writes the MSAL token cache. Later Graph calls use `acquire_token_silent`, allowing MSAL to reuse or renew the delegated access token without storing a raw access token in configuration.

`GET /microsoft/status` is also protected by `X-API-Key` and reports whether a mailbox account is currently connected.

The Microsoft app registration should support **Accounts in any organizational directory and personal Microsoft accounts**. Configure these environment values:

- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_AUTHORITY=https://login.microsoftonline.com/common`
- `MICROSOFT_REDIRECT_URI=https://<your-render-service>.onrender.com/microsoft/callback`
- `MICROSOFT_TOKEN_CACHE_PATH=.data/msal_token_cache.json`
- `OUTLOOK_REVIEW_RECIPIENT`

The old tenant-specific `MICROSOFT_TENANT_ID` and `OUTLOOK_MAILBOX` settings are no longer required.

### Generate an AI review and save an Outlook draft

`POST /reviews/{owner}/{repo}/{pr_number}/outlook-draft`

This endpoint runs the GitHub and OpenAI review flow and creates a draft through Microsoft Graph using delegated authorization. Draft creation uses:

`POST /me/messages`

The response is accepted only when Microsoft Graph returns a message ID and explicitly reports `isDraft: true`.

### Receive GitHub pull-request webhooks

`POST /webhooks/github`

GitHub calls this endpoint for pull-request events. The service validates `X-Hub-Signature-256` with `GITHUB_WEBHOOK_SECRET`, enforces the repository allowlist, filters supported PR actions, acknowledges quickly with HTTP 202, and runs GitHub → OpenAI → Outlook processing in a background task.

Automation runs for non-draft pull requests on `opened`, `reopened`, `synchronize`, and `ready_for_review`.

## Microsoft token-cache reliability

The delegated design uses an MSAL token cache so access tokens can be renewed without repeatedly asking the user to sign in. The default cache is stored at `.data/msal_token_cache.json`, which is excluded from Git.

On Render's free web-service filesystem, this cache is **not durable across instance replacement or redeployment**. If the cache disappears, `/microsoft/status` will show that no account is connected and `/microsoft/connect` must be used again. Before production use, move the serialized MSAL cache to durable encrypted storage.

## Continuous integration

GitHub Actions runs the complete Pytest suite for every pull request and every push to `main` using Python 3.11. The workflow uses read-only repository permissions, pip dependency caching, a 10-minute timeout, and a stable `tests` job name.

## Deployment on Render

A Render Blueprint is provided in `render.yaml`. It creates a Python web service in Frankfurt, installs `requirements.txt`, starts FastAPI with Uvicorn, and uses `/health` for health checks.

Required deployment values include:

- `OPENAI_API_KEY`
- `REVIEW_API_KEY`
- `GITHUB_WEBHOOK_SECRET`
- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_REDIRECT_URI`
- `OUTLOOK_REVIEW_RECIPIENT`

After deployment, verify `GET /health` returns `{"status":"ok"}`. Then complete `/microsoft/connect` once and register the GitHub repository webhook at:

`https://<your-render-service>.onrender.com/webhooks/github`

Use `application/json`, the same `GITHUB_WEBHOOK_SECRET`, SSL verification, and pull-request events.

The Blueprint uses Render's free plan for initial testing. Move to an always-on service and durable token-cache storage before relying on the integration for production automation.

## Development workflow

The application is developed through feature branches and pull requests rather than committing directly to `main`.

### Roadmap

1. FastAPI application foundation
2. GitHub PR integration
3. AI PR review service
4. Outlook draft integration
5. GitHub Actions CI
6. GitHub webhook automation
7. Public deployment and GitHub webhook registration
8. Optional review dashboard
