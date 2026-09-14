# AI PR Reviewer Application

An AI-assisted pull-request review application that connects GitHub, OpenAI, and Microsoft Outlook.

## Goal

When a GitHub pull request is opened or updated, the application will be able to:

- retrieve the pull-request metadata and code changes;
- analyse the changes with an AI reviewer;
- identify risks, bugs, and missing tests;
- produce a structured review and merge recommendation; and
- create an Outlook draft containing the review summary for human approval.

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

This endpoint retrieves the pull request from GitHub and sends the metadata and diff to the OpenAI Responses API. The response contains a structured review with summary, risk, concrete issues, missing tests, and a recommendation of `approve`, `changes_requested`, or `manual_review`.

Set `OPENAI_API_KEY` in the environment. `OPENAI_MODEL` optionally overrides the default model.

Because this endpoint can trigger paid OpenAI API calls, it is protected by a service API key. Set `REVIEW_API_KEY` to a long random secret and include it as `X-API-Key` on every AI review request. Missing or incorrect keys are rejected before GitHub is queried or OpenAI is called.

### Generate an AI review and save an Outlook draft

`POST /reviews/{owner}/{repo}/{pr_number}/outlook-draft`

This endpoint performs the same GitHub and OpenAI review flow, formats the structured result as a plain-text email, and creates an Outlook draft through Microsoft Graph. It does not send the message.

The Outlook integration uses renewable app-only Microsoft authentication through MSAL. Configure:

- `MICROSOFT_TENANT_ID` with the Microsoft Entra tenant ID;
- `MICROSOFT_CLIENT_ID` with the registered application client ID;
- `MICROSOFT_CLIENT_SECRET` with the application secret;
- `OUTLOOK_MAILBOX` with the mailbox in which the draft should be created; and
- `OUTLOOK_REVIEW_RECIPIENT` with the address placed in the draft's To field.

The Entra application must have Microsoft Graph `Mail.ReadWrite` **application** permission with administrator consent. The service acquires tokens using the client-credentials flow and MSAL automatically reuses its application token cache or obtains a fresh token when required. A short-lived Graph access token is therefore not stored in `.env`.

With app-only authentication, drafts are created via `/users/{mailbox}/messages`. The response is accepted only when Microsoft Graph returns a message ID and explicitly reports `isDraft: true`.

For public repositories, GitHub access can work without authentication subject to API rate limits. For private repositories or higher rate limits, set `GITHUB_TOKEN` in the environment.

For security, the API is deny-by-default: only repositories listed in `ALLOWED_GITHUB_REPOSITORIES` can be fetched. Large pull-request diffs are rejected before the AI-review stage. Pull-request content is treated as untrusted data in the AI-review prompt.

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
