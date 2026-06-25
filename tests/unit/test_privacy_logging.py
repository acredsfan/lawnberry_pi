import io

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


def test_privacy_filter_redacts_nested_victron_secret_fields():
    stream = io.StringIO()
    logger = create_test_logger(stream)
    logger.info(
        "config loaded",
        extra={
            "hardware": {
                "victron": {
                    "encryption_key": "unit-test-secret",
                    "device_key": "device-secret",
                }
            }
        },
    )
    out = stream.getvalue()
    assert "[REDACTED]" in out
    assert "unit-test-secret" not in out
    assert "device-secret" not in out


def test_privacy_filter_redacts_victron_secret_fields_in_message():
    stream = io.StringIO()
    logger = create_test_logger(stream)
    logger.info("encryption_key=unit-test-secret device_key=device-secret")
    out = stream.getvalue()
    assert "unit-test-secret" not in out
    assert "device-secret" not in out


def test_privacy_filter_supports_custom_sensitive_keys():
    stream = io.StringIO()
    logger = create_test_logger(
        stream,
        include_defaults=False,
        sensitive_keys=["session_token"],
    )
    logger.info("login attempt", extra={"session_token": "abc123"})
    out = stream.getvalue()
    assert "[REDACTED]" in out
    assert "abc123" not in out


def test_privacy_filter_supports_custom_patterns():
    stream = io.StringIO()
    logger = create_test_logger(
        stream,
        include_defaults=False,
        sensitive_patterns=[r"(?i)(sessionid=)[^\s,;]+"],
    )
    logger.info("sessionid=abc123")
    out = stream.getvalue()
    assert "[REDACTED]" in out
    assert "abc123" not in out
