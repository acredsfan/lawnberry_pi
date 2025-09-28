import io
import logging
from backend.src.core.logging import create_test_logger


def test_privacy_filter_redacts_tokens_in_message():
    stream = io.StringIO()
    logger = create_test_logger(stream)
    logger.info("Authorization: Bearer abcd1234")
    out = stream.getvalue()
    assert "[REDACTED]" in out
    assert "abcd1234" not in out


def test_privacy_filter_redacts_extra_fields():
    stream = io.StringIO()
    logger = create_test_logger(stream)
    logger.info("login attempt", extra={"token": "xyz", "password": "pw"})
    out = stream.getvalue()
    assert "[REDACTED]" in out
    assert "xyz" not in out
    assert "pw" not in out
