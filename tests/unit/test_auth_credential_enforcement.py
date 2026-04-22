"""Tests for BUG-009: LAWN_BERRY_OPERATOR_CREDENTIAL must be required at startup."""
import os
import pytest


def test_auth_service_raises_if_credential_unset(monkeypatch):
    """AuthService must raise RuntimeError if LAWN_BERRY_OPERATOR_CREDENTIAL is unset."""
    monkeypatch.delenv("LAWN_BERRY_OPERATOR_CREDENTIAL", raising=False)
    monkeypatch.setenv("SIM_MODE", "0")

    from backend.src.services.auth_service import AuthService

    with pytest.raises(RuntimeError, match="LAWN_BERRY_OPERATOR_CREDENTIAL"):
        AuthService()


def test_auth_service_succeeds_in_sim_mode(monkeypatch):
    """AuthService must NOT raise in SIM_MODE even without credential."""
    monkeypatch.delenv("LAWN_BERRY_OPERATOR_CREDENTIAL", raising=False)
    monkeypatch.setenv("SIM_MODE", "1")

    from backend.src.services.auth_service import AuthService

    svc = AuthService()  # must not raise
    assert svc is not None
