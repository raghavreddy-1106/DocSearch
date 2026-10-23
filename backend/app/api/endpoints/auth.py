"""
Authentication & User Management API Endpoint
----------------------------------------------
Provides registration, login, token issuance, and user session management.
Ensures every user account is distinct and search activities are tied to individual users.
"""
import os
import time
import json
import hashlib
import secrets
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr

router = APIRouter()

AUTH_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "users.json"


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ── Built-in Initial Default User ────────────────────────────────────────────
DEFAULT_USERS: Dict[str, Dict[str, Any]] = {
    "user@docsearch.io": {
        "id": "usr_default_01",
        "name": "DocSearch User",
        "email": "user@docsearch.io",
        "password_hash": _hash_password("user123"),
        "role": "User",
        "title": "Document Researcher",
        "avatar_color": "#3B82F6",
        "created_at": "2026-01-01T00:00:00Z"
    }
}


class UserStore:
    def __init__(self):
        self.users: Dict[str, Dict[str, Any]] = {}
        self.sessions: Dict[str, str] = {}  # token -> email
        self._load()

    def _load(self):
        if AUTH_DATA_FILE.exists():
            try:
                with open(AUTH_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.users = data.get("users", {})
                    self.sessions = data.get("sessions", {})
                    if not self.users:
                        self.users = dict(DEFAULT_USERS)
            except Exception as e:
                print(f"[UserStore] Load error: {e}")
                self.users = dict(DEFAULT_USERS)
        else:
            self.users = dict(DEFAULT_USERS)
            self._save()

    def _save(self):
        try:
            AUTH_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(AUTH_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "users": self.users,
                    "sessions": self.sessions
                }, f, indent=2)
        except Exception as e:
            print(f"[UserStore] Save error: {e}")

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.users.get(email.lower().strip())

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        for user in self.users.values():
            if user.get("id") == user_id:
                return user
        return None

    def create_user(self, name: str, email: str, password: str, role: str = "User", title: str = "") -> Dict[str, Any]:
        email_clean = email.lower().strip()
        if email_clean in self.users:
            raise HTTPException(status_code=400, detail="An account with this email already exists.")

        user_id = f"usr_{secrets.token_hex(6)}"
        colors = ["#3B82F6", "#10B981", "#8B5CF6", "#F59E0B", "#EC4899", "#06B6D4"]
        avatar_color = colors[len(self.users) % len(colors)]

        user = {
            "id": user_id,
            "name": name.strip(),
            "email": email_clean,
            "password_hash": _hash_password(password),
            "role": role or "User",
            "title": title or "Document Researcher",
            "avatar_color": avatar_color,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        self.users[email_clean] = user
        self._save()
        return user

    def create_session(self, email: str) -> str:
        token = f"dstok_{secrets.token_urlsafe(32)}"
        self.sessions[token] = email.lower().strip()
        self._save()
        return token

    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        email = self.sessions.get(token)
        if not email:
            return None
        return self.get_by_email(email)


user_store = UserStore()


def get_current_user_from_request(
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
) -> Optional[Dict[str, Any]]:
    """Extract authenticated user from token or headers."""
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        user = user_store.get_user_by_token(token)
        if user:
            return user
    if x_user_email:
        user = user_store.get_by_email(x_user_email)
        if user:
            return user
    if x_user_id:
        user = user_store.get_by_id(x_user_id)
        if user:
            return user
    return None


# ── Schemas ──────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    title: Optional[str] = ""


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    role: str
    title: str
    avatar_color: str
    token: Optional[str] = None


class AuthResponse(BaseModel):
    success: bool
    message: str
    user: Optional[UserProfile] = None
    token: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Authenticate user with email and password."""
    user = user_store.get_by_email(req.email)
    if not user or user.get("password_hash") != _hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = user_store.create_session(user["email"])
    profile = UserProfile(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        role=user.get("role", "User"),
        title=user.get("title", "Document Researcher"),
        avatar_color=user.get("avatar_color", "#3B82F6"),
        token=token
    )
    return AuthResponse(
        success=True,
        message=f"Welcome back, {user['name']}!",
        user=profile,
        token=token
    )


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    """Register a new user account."""
    if len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters long.")

    user = user_store.create_user(
        name=req.name,
        email=req.email,
        password=req.password,
        role="User",
        title=req.title or "Document Researcher"
    )
    token = user_store.create_session(user["email"])
    profile = UserProfile(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        role=user.get("role", "User"),
        title=user.get("title", "Document Researcher"),
        avatar_color=user.get("avatar_color", "#3B82F6"),
        token=token
    )
    return AuthResponse(
        success=True,
        message="Account created successfully!",
        user=profile,
        token=token
    )


@router.get("/me", response_model=AuthResponse)
def get_current_user(
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
):
    """Retrieve current logged in user from Authorization token header."""
    user = get_current_user_from_request(authorization=authorization, x_user_email=x_user_email)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    token = authorization.replace("Bearer ", "").strip() if authorization else None
    profile = UserProfile(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        role=user.get("role", "User"),
        title=user.get("title", "Document Researcher"),
        avatar_color=user.get("avatar_color", "#3B82F6"),
        token=token
    )
    return AuthResponse(success=True, message="Authenticated", user=profile, token=token)


@router.post("/logout")
def logout(
    authorization: Optional[str] = Header(None)
):
    """Invalidate current session token."""
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        if token in user_store.sessions:
            del user_store.sessions[token]
            user_store._save()
    return {"success": True, "message": "Logged out successfully"}
