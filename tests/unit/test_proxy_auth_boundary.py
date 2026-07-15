from pathlib import Path


def test_production_proxy_replaces_untrusted_forwarding_identity() -> None:
    frontend_server = Path("frontend/server.mjs").read_text(encoding="utf-8")
    backend_unit = Path("systemd/lawnberry-backend.service").read_text(encoding="utf-8")

    assert "delete req.headers['x-forwarded-for']" in frontend_server
    assert "delete req.headers['forwarded']" in frontend_server
    assert "delete req.headers['x-lawnberry-client-ip']" in frontend_server
    assert "isLoopback(peerIp) && trustedUpstreamIp" in frontend_server
    assert "req.headers['x-lawnberry-client-ip'] = clientIp" in frontend_server
    assert "--no-proxy-headers" in backend_unit


def test_dotenv_load_precedes_auth_router_import() -> None:
    main_source = Path("backend/src/main.py").read_text(encoding="utf-8")

    assert main_source.index("load_dotenv(") < main_source.index(
        "from .api.routers import auth as auth_router"
    )
