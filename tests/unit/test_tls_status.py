"""Unit tests for backend.src.core.tls_status.

Covers the critical PermissionError-handling paths that were missing before the
fix for the "TLS probe failed" health regression on Raspberry Pi deployments
where /etc/letsencrypt/live is root-only (mode 700).
"""
from __future__ import annotations

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
    """candidate.exists() raises PermissionError on restricted systems."""

    def test_domain_hint_permission_error_returns_none(self, tmp_path):
        """When candidate.exists() raises PermissionError, returns (None, None)."""
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

            with patch.object(Path, "exists", mock_exists):
                result = _detect_le_cert_path("somedomain.example.com")

        assert result == (None, None)

    def test_iterdir_permission_error_returns_none(self, tmp_path):
        """When LE_LIVE_DIR.iterdir() raises PermissionError, returns (None, None)."""
        live_dir = tmp_path / "live"
        live_dir.mkdir()

        with patch("backend.src.core.tls_status.LE_LIVE_DIR", live_dir):
            with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
                result = _detect_le_cert_path(None)

        assert result == (None, None)


# ---------------------------------------------------------------------------
# _detect_nginx_cert_path – PermissionError on cp.exists() → returns path anyway
# ---------------------------------------------------------------------------

class TestDetectNginxCertPath:
    def test_returns_path_on_permission_error(self, tmp_path):
        """If the cert file can't be stat'd (PermissionError), the nginx-configured
        path is still returned (nginx is serving it, so it must be valid)."""
        conf_file = tmp_path / "nginx.conf"
        cert_path = tmp_path / "fullchain.pem"
        conf_file.write_text(f"ssl_certificate {cert_path};\n")

        original_exists = Path.exists

        def mock_exists(self):
            if str(self) == str(cert_path):
                raise PermissionError("Permission denied")
            return original_exists(self)

        with patch("backend.src.core.tls_status.NGINX_CONF_PATHS", [conf_file]):
            with patch.object(Path, "exists", mock_exists):
                result = _detect_nginx_cert_path()

        assert result == cert_path

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
# get_tls_status integration – permission-denied cert falls back to s_client
# ---------------------------------------------------------------------------

class TestGetTlsStatusFallback:
    """End-to-end: when the cert file is root-only, get_tls_status must use
    the TLS endpoint probe and return a proper status instead of raising."""

    def _make_nginx_conf(self, tmp_path: Path, cert_path: Path) -> Path:
        conf = tmp_path / "lawnberry-https"
        conf.write_text(f"ssl_certificate {cert_path};\n")
        return conf

    def test_no_exception_when_cert_unreadable_with_working_tls(self, tmp_path):
        """Simulates the production Pi scenario: cert file stat raises PermissionError,
        but the TLS probe endpoint returns valid cert info."""
        cert_path = tmp_path / "fullchain.pem"
        conf_file = self._make_nginx_conf(tmp_path, cert_path)

        future = datetime.now(UTC) + timedelta(days=65)
        enddate_str = future.strftime("%b %d %H:%M:%S %Y GMT")
        x509_output = (
            f"notAfter={enddate_str}\n"
            "subject=CN = lawnberry.link-smart-home.com\n"
        ).encode()

        original_exists = Path.exists

        def mock_exists(self):
            if str(self) == str(cert_path):
                raise PermissionError("Permission denied: /etc/letsencrypt/live/...")
            return original_exists(self)

        mock_proc_sc = MagicMock()
        mock_proc_sc.stdout = b"--- PEM data ---"
        mock_proc_x509 = MagicMock()
        mock_proc_x509.stdout = x509_output

        with (
            patch("backend.src.core.tls_status.NGINX_CONF_PATHS", [conf_file]),
            patch("backend.src.core.tls_status.LE_LIVE_DIR", tmp_path / "nonexistent"),
            patch.object(Path, "exists", mock_exists),
            patch("backend.src.core.tls_status.subprocess.run", side_effect=[mock_proc_sc, mock_proc_x509]),
            # _run_openssl (file-based) won't be able to read the cert either
            patch("backend.src.core.tls_status._run_openssl", return_value=None),
        ):
            result = get_tls_status()

        assert result["status"] == "healthy"
        assert result["detail"] == "Certificate valid"
        assert result["days_until_expiry"] is not None
        assert result["valid_now"] is True
        assert result["domain"] == "lawnberry.link-smart-home.com"

    def test_returns_unknown_when_both_file_and_tls_probe_fail(self, tmp_path):
        """If the cert file is unreadable AND the TLS probe also fails,
        status must be 'unknown' (not raise an exception)."""
        cert_path = tmp_path / "fullchain.pem"
        conf_file = self._make_nginx_conf(tmp_path, cert_path)

        original_exists = Path.exists

        def mock_exists(self):
            if str(self) == str(cert_path):
                raise PermissionError("denied")
            return original_exists(self)

        with (
            patch("backend.src.core.tls_status.NGINX_CONF_PATHS", [conf_file]),
            patch("backend.src.core.tls_status.LE_LIVE_DIR", tmp_path / "nonexistent"),
            patch.object(Path, "exists", mock_exists),
            patch("backend.src.core.tls_status.subprocess.run", side_effect=Exception("connection refused")),
            patch("backend.src.core.tls_status._run_openssl", return_value=None),
        ):
            result = get_tls_status()

        assert result["status"] == "unknown"
        assert "Unable to parse" in result["detail"]
        assert result["valid_now"] is False
