from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from typing import Optional
import secrets

from app.auth import auth_service, demo_login

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
async def register(request: RegisterRequest, response: Response):
    """Register new user with password validation"""
    result, error = auth_service.register(
        username=request.username,
        email=request.email,
        password=request.password
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    # Set session cookie
    response.set_cookie(
        key="session_id",
        value=result["session"]["session_id"],
        httponly=True,
        samesite="lax",
        max_age=86400,
        secure=True  # In production, set to True with HTTPS
    )
    
    return LoginResponse(
        user=result["user"],
        session_id=result["session"]["session_id"]
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response, demo_mode: bool = True):
    """Login endpoint"""
    if demo_mode:
        # Demo mode - allow any username, no password required
        result, error = demo_login(request.username)
    else:
        # Production mode - require password
        result, error = auth_service.authenticate(request.username, request.password)
    
    if error:
        raise HTTPException(status_code=401, detail=error)
    
    # Set session cookie
    response.set_cookie(
        key="session_id",
        value=result["session"]["session_id"],
        httponly=True,
        samesite="lax",
        max_age=86400,
        secure=True
    )
    
    return LoginResponse(
        user=result["user"],
        session_id=result["session"]["session_id"]
    )


@router.post("/logout")
async def logout(response: Response):
    """Logout endpoint"""
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