from app.webhook_service import ReviewTracker


class MemoryStateStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.claims: dict[str, tuple[str, str]] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def claim_review(self, key: str, claim_token: str, lease_seconds: int) -> bool:
        if key in self.claims:
            return False
        self.claims[key] = ("in_progress", claim_token)
        return True

    def renew_review(self, key: str, claim_token: str, lease_seconds: int) -> bool:
        return self.claims.get(key) == ("in_progress", claim_token)

    def complete_review(self, key: str, claim_token: str) -> bool:
        if self.claims.get(key) != ("in_progress", claim_token):
            return False
        self.claims[key] = ("completed", claim_token)
        return True

    def release_review(self, key: str, claim_token: str) -> bool:
        if self.claims.get(key) != ("in_progress", claim_token):
            return False
        del self.claims[key]
        return True

    def prune_completed_reviews(self, max_entries: int) -> None:
        completed = [key for key, (status, _) in self.claims.items() if status == "completed"]
        for key in completed[:-max_entries]:
            self.claims.pop(key, None)

    def clear_reviews(self) -> None:
        self.claims.clear()


def test_completed_review_survives_tracker_recreation_with_state_store() -> None:
    store = MemoryStateStore()
    first = ReviewTracker(state_store=store)
    assert first.register("Owner/Repo", 12, "ABC123") is True
    first.mark_completed("Owner/Repo", 12, "ABC123")

    second = ReviewTracker(state_store=store)
    assert second.register("owner/repo", 12, "abc123") is False


def test_database_backed_discard_allows_retry() -> None:
    store = MemoryStateStore()
    first = ReviewTracker(state_store=store)
    assert first.register("owner/repo", 12, "abc123") is True
    first.discard("owner/repo", 12, "abc123")

    second = ReviewTracker(state_store=store)
    assert second.register("owner/repo", 12, "abc123") is True
