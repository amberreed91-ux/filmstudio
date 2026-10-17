from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from typing import Optional
import secrets

from app.auth import auth_service, demo_login
from app.config import settings

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str = ""


class LoginResponse(BaseModel):
    user: dict
    session_id: str


@router.post("/register", response_model=LoginResponse)
async def register(request: RegisterRequest, response: Response, http_request: Request):
    """Register new user with password validation"""
    result, error = auth_service.register(
        username=request.username,
        email=request.email,
        password=request.password
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    result, error = auth_service.authenticate(request.username, request.password)
    if error:
        raise HTTPException(status_code=401, detail=error)
    # Set session cookie
    # Secure only over HTTPS: a Secure flag on plain-http loopback hosts
    # (notably 127.0.0.1 in strict browsers) makes the browser silently drop
    # the cookie, which reads as a permanent "Authentication required" loop.
    response.set_cookie(
        key="session_id",
        value=result["session"]["session_id"],
        httponly=True,
        samesite="lax",
        max_age=86400,
        secure=http_request.url.scheme == "https",
    )

    return LoginResponse(
        user=result["user"],
        session_id=result["session"]["session_id"]
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response, http_request: Request):
    """Login endpoint"""
    if settings.demo_mode and bool(getattr(http_request.state, "local_access", False)):
        # Demo mode - allow any username, no password required
        result, error = demo_login(request.username)
    else:
        # Production mode - require password
        result, error = auth_service.authenticate(request.username, request.password)
    
    if error:
        raise HTTPException(status_code=401, detail=error)
    
    # Set session cookie (Secure only over HTTPS — see register above).
    response.set_cookie(
        key="session_id",
        value=result["session"]["session_id"],
        httponly=True,
        samesite="lax",
        max_age=86400,
        secure=http_request.url.scheme == "https",
    )
    
    return LoginResponse(
        user=result["user"],
        session_id=result["session"]["session_id"]
    )


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Logout endpoint"""
    token = request.cookies.get("session_id") or request.headers.get("X-Session-Token")
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    if token:
        auth_service.delete_session(token)
    response.delete_cookie("session_id")
    return {"status": "logged_out"}


@router.get("/session")
async def get_session(request: Request):
    """Get current session info"""
    session_id = request.cookies.get("session_id") or request.headers.get("X-Session-Token")
    
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = auth_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    
    user = auth_service.get_user(session["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return {"user": user, "session": session}


@router.delete("/session")
async def delete_session(request: Request, response: Response):
    """Delete a specific session"""
    session_id = request.cookies.get("session_id") or request.headers.get("X-Session-Token")
    
    if session_id:
        auth_service.delete_session(session_id)
    
    response.delete_cookie("session_id")
    return {"status": "session_deleted"}

@router.get("/access-mode")
async def access_mode(request: Request):
    return {"local_access": bool(getattr(request.state, "local_access", False))}
