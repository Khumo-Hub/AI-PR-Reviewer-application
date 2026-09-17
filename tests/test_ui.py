from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_portfolio_app_loads() -> None:
    response = client.get("/app")

    assert response.status_code == 200
    assert "AI PR Reviewer" in response.text
    assert "Review a pull request" in response.text
    assert "Create Outlook Draft" in response.text
