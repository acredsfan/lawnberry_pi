"""Unit tests for backend.src.core.tls_status.

Covers:
- PermissionError-handling paths in cert detection helpers (defensive guards
  that log warnings rather than silently failing).
- Direct file-based path: the primary production path now that pi has setfacl
  read ACLs on /etc/letsencrypt/.
- _probe_cert_via_tls() as a standalone utility (it is NOT called from
  get_tls_status(); kept here for manual diagnostics coverage).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.src.core.tls_status import (
    _detect_le_cert_path,
    _detect_nginx_cert_path,
    _probe_cert_via_tls,
    get_tls_status,
)


# ---------------------------------------------------------------------------
# _detect_le_cert_path – PermissionError must not propagate
# ---------------------------------------------------------------------------

class TestDetectLeCertPathPermissionError:
    """PermissionError must not propagate — a warning must be logged instead."""

    def test_domain_hint_permission_error_returns_none(self, tmp_path, caplog):
        """When candidate.exists() raises PermissionError, returns (None, None)
        and logs a warning so operators know to re-apply ACLs."""
        # The letsencrypt live dir exists but is not traversable
        live_dir = tmp_path / "live"
        live_dir.mkdir()

        with patch("backend.src.core.tls_status.LE_LIVE_DIR", live_dir):
            # Patch Path.exists to raise PermissionError
            original_exists = Path.exists

            def mock_exists(self):
                if "fullchain.pem" in str(self):
                    raise PermissionError("Permission denied")
                return original_exists(self)

            with caplog.at_level(logging.WARNING, logger="backend.src.core.tls_status"):
                with patch.object(Path, "exists", mock_exists):
                    result = _detect_le_cert_path("somedomain.example.com")

        assert result == (None, None)
        assert any("PermissionError" in r.message for r in caplog.records)

    def test_iterdir_permission_error_returns_none(self, tmp_path, caplog):
        """When LE_LIVE_DIR.iterdir() raises PermissionError, returns (None, None)
        and logs a warning."""
        live_dir = tmp_path / "live"
        live_dir.mkdir()

        with patch("backend.src.core.tls_status.LE_LIVE_DIR", live_dir):
            with caplog.at_level(logging.WARNING, logger="backend.src.core.tls_status"):
                with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
                    result = _detect_le_cert_path(None)

        assert result == (None, None)
        assert any("PermissionError" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _detect_nginx_cert_path – PermissionError on cp.exists() → returns path anyway
# ---------------------------------------------------------------------------

class TestDetectNginxCertPath:
    def test_returns_path_on_permission_error(self, tmp_path, caplog):
        """If the cert file can't be stat'd (PermissionError), the nginx-configured
        path is still returned (nginx is serving it, so it must be valid), AND a
        warning is logged so the operator knows to re-apply ACLs."""
        conf_file = tmp_path / "nginx.conf"
        cert_path = tmp_path / "fullchain.pem"
        conf_file.write_text(f"ssl_certificate {cert_path};\n")

        original_exists = Path.exists

        def mock_exists(self):
            if str(self) == str(cert_path):
                raise PermissionError("Permission denied")
            return original_exists(self)

        with patch("backend.src.core.tls_status.NGINX_CONF_PATHS", [conf_file]):
            with caplog.at_level(logging.WARNING, logger="backend.src.core.tls_status"):
                with patch.object(Path, "exists", mock_exists):
                    result = _detect_nginx_cert_path()

        assert result == cert_path
        assert any("PermissionError" in r.message for r in caplog.records)

    def test_returns_path_when_exists_true(self, tmp_path):
        """Normal case: cert file exists and is readable."""
        conf_file = tmp_path / "nginx.conf"
        cert_path = tmp_path / "fullchain.pem"
        cert_path.write_text("FAKE CERT")
        conf_file.write_text(f"ssl_certificate {cert_path};\n")

        with patch("backend.src.core.tls_status.NGINX_CONF_PATHS", [conf_file]):
            result = _detect_nginx_cert_path()

        assert result == cert_path


# ---------------------------------------------------------------------------
# _probe_cert_via_tls – subprocess failure → (None, None, None)
# ---------------------------------------------------------------------------

class TestProbeCertViaTls:
    def test_subprocess_failure_returns_none_triple(self):
        with patch("backend.src.core.tls_status.subprocess.run", side_effect=Exception("connection refused")):
            result = _probe_cert_via_tls()
        assert result == (None, None, None)

    def test_parses_valid_s_client_output(self):
        # Simulate openssl s_client piped to openssl x509 output
        future = datetime.now(UTC) + timedelta(days=65)
        enddate_str = future.strftime("%b %d %H:%M:%S %Y GMT")
        x509_output = (
            f"notAfter={enddate_str}\n"
            "subject=CN = example.lawnberry.com\n"
        ).encode()

        mock_proc_sc = MagicMock()
        mock_proc_sc.stdout = b"--- fake s_client PEM output ---"
        mock_proc_x509 = MagicMock()
        mock_proc_x509.stdout = x509_output

        with patch("backend.src.core.tls_status.subprocess.run", side_effect=[mock_proc_sc, mock_proc_x509]):
            not_after, days_left, cn = _probe_cert_via_tls()

        assert not_after is not None
        assert days_left is not None
        assert 64 < days_left < 66
        assert cn == "example.lawnberry.com"


# ---------------------------------------------------------------------------
# get_tls_status integration – direct file access is the primary path
# ---------------------------------------------------------------------------

class TestGetTlsStatusDirectFileAccess:
    """End-to-end: get_tls_status reads cert expiry directly from the file.
    This is the production path now that pi has setfacl read ACLs on
    /etc/letsencrypt/.  No openssl s_client fallback is involved."""

    def _make_nginx_conf(self, tmp_path: Path, cert_path: Path) -> Path:
        conf = tmp_path / "lawnberry-https"
        conf.write_text(f"ssl_certificate {cert_path};\n")
        return conf

    def test_healthy_when_cert_readable_and_valid(self, tmp_path):
        """Normal production case: cert file is readable, openssl parses expiry."""
        cert_path = tmp_path / "fullchain.pem"
        cert_path.write_text("FAKE CERT")
        conf_file = self._make_nginx_conf(tmp_path, cert_path)

        future = datetime.now(UTC) + timedelta(days=65)
        enddate_str = future.strftime("%b %d %H:%M:%S %Y GMT")

        with (
            patch("backend.src.core.tls_status.NGINX_CONF_PATHS", [conf_file]),
            patch(
                "backend.src.core.tls_status._run_openssl",
                side_effect=[
                    f"notAfter={enddate_str}",   # _parse_not_after call
                    "subject=CN = lawnberry.link-smart-home.com",  # _subject_cn call
                ],
            ),
        ):
            result = get_tls_status()

        assert result["status"] == "healthy"
        assert result["detail"] == "Certificate valid"
        assert result["days_until_expiry"] is not None
        assert result["valid_now"] is True

    def test_returns_unknown_when_cert_unreadable_no_subprocess_fallback(
        self, tmp_path, caplog
    ):
        """When the cert file is unreadable (PermissionError), get_tls_status
        returns 'unknown' and logs a warning.  No subprocess/s_client call is
        made — the openssl s_client fallback has been removed from the hot path."""
        cert_path = tmp_path / "fullchain.pem"
        conf_file = self._make_nginx_conf(tmp_path, cert_path)

        original_exists = Path.exists

        def mock_exists(self):
            if str(self) == str(cert_path):
                raise PermissionError("Permission denied: /etc/letsencrypt/live/...")
            return original_exists(self)

        with (
            patch("backend.src.core.tls_status.NGINX_CONF_PATHS", [conf_file]),
            patch("backend.src.core.tls_status.LE_LIVE_DIR", tmp_path / "nonexistent"),
            patch.object(Path, "exists", mock_exists),
            # openssl file-based calls fail (cert unreadable)
            patch("backend.src.core.tls_status._run_openssl", return_value=None),
            # subprocess.run must NOT be called — assert below confirms this
            patch("backend.src.core.tls_status.subprocess.run") as mock_run,
            caplog.at_level(logging.WARNING, logger="backend.src.core.tls_status"),
        ):
            result = get_tls_status()

        assert result["status"] == "unknown"
        assert "Unable to parse" in result["detail"]
        assert result["valid_now"] is False
        # Confirm the s_client probe was NOT triggered by get_tls_status
        mock_run.assert_not_called()
        # Confirm the PermissionError warning was logged
        assert any("PermissionError" in r.message for r in caplog.records)

    def test_returns_unknown_when_cert_not_found_at_all(self, tmp_path):
        """If no cert path can be found (no nginx config, no LE dir, no self-signed),
        get_tls_status returns 'unknown' without raising."""
        with (
            patch("backend.src.core.tls_status.NGINX_CONF_PATHS", []),
            patch("backend.src.core.tls_status.LE_LIVE_DIR", tmp_path / "nonexistent"),
            patch("backend.src.core.tls_status.SELF_SIGNED_FULLCHAIN", tmp_path / "nope.pem"),
        ):
            result = get_tls_status()

        assert result["status"] == "unknown"
        assert result["detail"] == "No certificate found"
