"""TLS/HTTPS certificate status probe for LawnBerry Pi.

This module inspects the currently configured TLS certificate(s) and returns a
concise status payload suitable for health and metrics endpoints. It avoids
third-party dependencies and shells out to `openssl` with tight timeouts.

Notes:
- Prefers the nginx-active certificate if one is referenced in nginx configs.
- Falls back to Let's Encrypt directory (based on LB_DOMAIN/.env or first live dir).
- Otherwise considers the self-signed baseline.
"""
# ruff: noqa: I001
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


NGINX_CONF_PATHS = [
    Path("/etc/nginx/nginx.conf"),
    *list(Path("/etc/nginx/sites-enabled").glob("*")),
]
LE_LIVE_DIR = Path("/etc/letsencrypt/live")
SELF_SIGNED_FULLCHAIN = Path("/etc/lawnberry/certs/selfsigned/fullchain.pem")


@dataclass
class CertInfo:
    path: Path | None
    mode: str  # "letsencrypt", "self-signed", or "unknown"
    domain: str | None


def _read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _detect_nginx_cert_path() -> Path | None:
    cert_re = re.compile(r"^\s*ssl_certificate\s+([^;]+);", re.IGNORECASE)
    for p in NGINX_CONF_PATHS:
        try:
            if not p.exists() or not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = cert_re.match(line)
                if m:
                    cp = Path(m.group(1).strip())
                    try:
                        if cp.exists():
                            return cp
                    except PermissionError:
                        # Can't traverse the cert directory (e.g. /etc/letsencrypt/live
                        # is root-only), but nginx has it configured so it must be valid.
                        return cp
        except Exception:
            continue
    return None


def _detect_le_cert_path(domain_hint: str | None) -> tuple[Path | None, str | None]:
    if domain_hint:
        candidate = LE_LIVE_DIR / domain_hint / "fullchain.pem"
        try:
            if candidate.exists():
                return candidate, domain_hint
        except (PermissionError, OSError):
            # The letsencrypt live dir may not be traversable by the current user;
            # skip file-existence checks and let the caller fall back to s_client.
            pass
    # fallback: first directory in live
    try:
        for d in sorted(LE_LIVE_DIR.iterdir()):
            if not d.is_dir():
                continue
            pem = d / "fullchain.pem"
            try:
                if pem.exists():
                    return pem, d.name
            except (PermissionError, OSError):
                pass
    except Exception:
        pass
    return None, None


def _run_openssl(args: list[str], timeout: float = 2.0) -> str | None:
    try:
        out = subprocess.check_output(
            ["openssl", *args], timeout=timeout, stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8", errors="ignore").strip()
    except Exception:
        return None


def _run_openssl_from_pem(args: list[str], pem_data: str, timeout: float = 3.0) -> str | None:
    """Run an ``openssl x509`` command with a PEM certificate provided on stdin."""
    try:
        proc = subprocess.run(
            ["openssl", *args],
            input=pem_data.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="ignore").strip()
    except Exception:
        return None


def _fetch_pem_from_endpoint(
    host: str = "127.0.0.1",
    port: int = 443,
    domain: str | None = None,
    timeout: float = 5.0,
) -> str | None:
    """Connect to a live TLS endpoint and return the leaf certificate as a PEM string.

    This is used as a fallback when the certificate file cannot be read directly
    (e.g. when the process lacks permission to access /etc/letsencrypt/live/).
    """
    cmd = ["openssl", "s_client", "-connect", f"{host}:{port}"]
    if domain:
        cmd += ["-servername", domain]
    try:
        proc = subprocess.run(
            cmd,
            input=b"",
            capture_output=True,
            timeout=timeout,
        )
        output = proc.stdout.decode("utf-8", errors="ignore")
        begin_marker = "-----BEGIN CERTIFICATE-----"
        end_marker = "-----END CERTIFICATE-----"
        start = output.find(begin_marker)
        stop = output.find(end_marker)
        if start == -1 or stop == -1:
            return None
        return output[start: stop + len(end_marker)]
    except Exception:
        return None


def _parse_not_after(pem_path: Path) -> tuple[datetime | None, float | None]:
    # `openssl x509 -noout -enddate -in <pem>` → "notAfter=Jul 13 12:00:00 2026 GMT"
    txt = _run_openssl(["x509", "-noout", "-enddate", "-in", str(pem_path)])
    if not txt or "notAfter=" not in txt:
        return None, None
    value = txt.split("=", 1)[1].strip()
    try:
        dt = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
        days = (dt - datetime.now(UTC)).total_seconds() / 86400.0
        return dt, days
    except Exception:
        return None, None


def _subject_cn(pem_path: Path) -> str | None:
    subj = _run_openssl(["x509", "-noout", "-subject", "-in", str(pem_path)])
    if not subj:
        return None
    # subject=CN = example.com or subject= /CN=example.com
    m = re.search(r"CN\s*=\s*([^/]+)$", subj)
    return m.group(1).strip() if m else None


def _probe_cert_via_tls(
    host: str = "127.0.0.1", port: int = 443, timeout: float = 4.0
) -> tuple[datetime | None, float | None, str | None]:
    """Get certificate expiry/CN by probing the live TLS endpoint.

    Used as a fallback when the cert file itself is not readable by the current
    user (e.g. /etc/letsencrypt/live is root-only on Raspberry Pi deployments).
    Runs ``openssl s_client`` and pipes the presented certificate into
    ``openssl x509``; no file access is required.

    Returns ``(not_after, days_left, cn)`` — any member may be ``None`` on
    failure.
    """
    try:
        proc_sc = subprocess.run(
            [
                "openssl", "s_client",
                "-connect", f"{host}:{port}",
                "-servername", "localhost",
            ],
            input=b"",
            capture_output=True,
            timeout=timeout,
        )
        proc_x509 = subprocess.run(
            ["openssl", "x509", "-noout", "-enddate", "-subject"],
            input=proc_sc.stdout,
            capture_output=True,
            timeout=timeout,
        )
        text = proc_x509.stdout.decode("utf-8", errors="ignore").strip()
        not_after: datetime | None = None
        days_left: float | None = None
        cn: str | None = None
        for line in text.splitlines():
            if line.startswith("notAfter="):
                value = line.split("=", 1)[1].strip()
                try:
                    dt = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
                    not_after = dt
                    days_left = (dt - datetime.now(UTC)).total_seconds() / 86400.0
                except Exception:
                    pass
            elif line.startswith("subject="):
                m = re.search(r"CN\s*=\s*([^,/\n]+)", line)
                if m:
                    cn = m.group(1).strip()
        return not_after, days_left, cn
    except Exception:
        return None, None, None


def _active_cert_info() -> CertInfo:
    # 1) Prefer nginx-referenced certificate if found
    active = _detect_nginx_cert_path()
    if active:
        mode = (
            "letsencrypt"
            if str(active).startswith(str(LE_LIVE_DIR))
            else (
                "self-signed"
                if str(active).startswith("/etc/lawnberry/certs/selfsigned")
                else "unknown"
            )
        )
        return CertInfo(path=active, mode=mode, domain=None)

    # 2) Try Let's Encrypt live directory
    env = {**os.environ}
    env.update(_read_env_file(Path("./.env")))
    domain_hint = env.get("LB_DOMAIN") or env.get("DOMAIN")
    le_path, domain = _detect_le_cert_path(domain_hint)
    if le_path:
        return CertInfo(path=le_path, mode="letsencrypt", domain=domain)

    # 3) Fall back to self-signed baseline
    if SELF_SIGNED_FULLCHAIN.exists():
        return CertInfo(path=SELF_SIGNED_FULLCHAIN, mode="self-signed", domain=None)

    return CertInfo(path=None, mode="unknown", domain=None)


def get_tls_status() -> dict[str, Any]:
    info = _active_cert_info()
    if info.path is None:
        return {
            "status": "unknown",
            "detail": "No certificate found",
            "mode": info.mode,
        }

    not_after, days_left = _parse_not_after(info.path)
    cn = _subject_cn(info.path)

    # When the cert file is inaccessible (e.g. root-only letsencrypt dir) the
    # file-based openssl calls return None.  Fall back to probing the live TLS
    # endpoint so we can still report accurate expiry information.
    if days_left is None:
        tls_not_after, tls_days, tls_cn = _probe_cert_via_tls()
        if tls_days is not None:
            not_after = tls_not_after
            days_left = tls_days
            if cn is None:
                cn = tls_cn

    # Health policy
    status: str
    detail: str
    valid_now = days_left is not None and days_left >= 0.0
    if days_left is None:
        status = "unknown"
        detail = "Unable to parse certificate expiry"
    elif days_left < 7:
        status = "critical"
        detail = f"Certificate expiring soon ({days_left:.1f} days)"
    elif days_left < 30:
        status = "degraded"
        detail = f"Certificate within renewal window ({days_left:.1f} days)"
    else:
        status = "healthy"
        detail = "Certificate valid"

    return {
        "status": status,
        "detail": detail,
        "mode": info.mode,
        "domain": info.domain or cn,
        "active_cert_path": str(info.path),
        "not_after": not_after.isoformat() if not_after else None,
        "days_until_expiry": None if days_left is None else round(days_left, 1),
        "valid_now": bool(valid_now),
    }
