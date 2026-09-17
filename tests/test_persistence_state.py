from app.webhook_service import ReviewTracker


class MemoryStateStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


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
    first.mark_completed("owner/repo", 12, "abc123")
    first.discard("owner/repo", 12, "abc123")

    second = ReviewTracker(state_store=store)
    assert second.register("owner/repo", 12, "abc123") is True
