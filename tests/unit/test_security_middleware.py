import pytest
from fastapi import FastAPI

from backend.src.middleware.security import SecurityMiddleware


class FakeTime:
    def __init__(self, start: float = 1_000.0) -> None:
        self.value = start

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def time(self) -> float:
        return self.value


@pytest.mark.asyncio
async def test_successful_requests_do_not_consume_attempt_quota(monkeypatch):
    app = FastAPI()
    middleware = SecurityMiddleware(
        app,
        rate_limit_window_seconds=60,
        rate_limit_max_attempts=3,
        lockout_failures=3,
        lockout_seconds=60,
    )
    fake_time = FakeTime()
    monkeypatch.setattr("backend.src.middleware.security.time.time", fake_time.time)

    client_key = "client-a"

    # First attempt succeeds
    assert await middleware._preprocess_rate_limit(client_key) is None
    await middleware._postprocess_rate_limit(client_key, 200)

    # Attempts deque should be cleared for successful logins
    assert client_key not in middleware._attempts

    # A subsequent request within the window should still be allowed
    fake_time.advance(10)
    assert await middleware._preprocess_rate_limit(client_key) is None


@pytest.mark.asyncio
async def test_failed_attempts_trigger_rate_limit(monkeypatch):
    app = FastAPI()
    middleware = SecurityMiddleware(
        app,
        rate_limit_window_seconds=30,
        rate_limit_max_attempts=3,
        lockout_failures=99,
        lockout_seconds=60,
    )
    fake_time = FakeTime()
    monkeypatch.setattr("backend.src.middleware.security.time.time", fake_time.time)

    client_key = "client-b"

    for _ in range(3):
        assert await middleware._preprocess_rate_limit(client_key) is None
        await middleware._postprocess_rate_limit(client_key, 401)
        fake_time.advance(1)

    response = await middleware._preprocess_rate_limit(client_key)
    assert response is not None
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0

    fake_time.advance(35)
    assert await middleware._preprocess_rate_limit(client_key) is None


@pytest.mark.asyncio
async def test_successful_auth_resets_failure_state(monkeypatch):
    app = FastAPI()
    middleware = SecurityMiddleware(
        app,
        rate_limit_window_seconds=45,
        rate_limit_max_attempts=3,
        lockout_failures=99,
        lockout_seconds=60,
    )
    fake_time = FakeTime()
    monkeypatch.setattr("backend.src.middleware.security.time.time", fake_time.time)

    client_key = "client-c"

    # Two failed attempts should be counted
    for _ in range(2):
        assert await middleware._preprocess_rate_limit(client_key) is None
        await middleware._postprocess_rate_limit(client_key, 401)
        fake_time.advance(1)

    # Successful attempt clears counters
    assert await middleware._preprocess_rate_limit(client_key) is None
    await middleware._postprocess_rate_limit(client_key, 200)

    assert client_key not in middleware._attempts
    assert client_key not in middleware._failures
    assert client_key not in middleware._lockout_until

    fake_time.advance(5)
    assert await middleware._preprocess_rate_limit(client_key) is None
