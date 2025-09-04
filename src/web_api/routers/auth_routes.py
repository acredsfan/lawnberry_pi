"""
Authentication Router
Provides login, logout, and user info endpoints to obtain JWTs for authenticated routes.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from ..auth import AuthManager, get_auth_manager, get_current_user
from ..auth import LoginRequest, LoginResponse

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, auth_mgr: AuthManager = Depends(get_auth_manager)):
    user = auth_mgr.authenticate_user(data.username, data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = auth_mgr.create_access_token({"sub": user["username"], "role": user["role"]})
    # expires_in mirrors config hours in seconds
    return LoginResponse(access_token=token, user=user, expires_in=auth_mgr.config.jwt_expiration_hours * 3600)


@router.post("/logout")
async def logout(current_user: Dict[str, Any] = Depends(get_current_user), auth_mgr: AuthManager = Depends(get_auth_manager)):
    # Best-effort; client should discard token; server revocation list maintained for active tokens
    return {"success": True}


@router.get("/me")
async def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return current_user
