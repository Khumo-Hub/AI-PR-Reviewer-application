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
