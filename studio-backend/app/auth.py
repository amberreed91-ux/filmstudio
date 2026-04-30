import secrets
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from functools import wraps

# User database - in production, load from database
_users_db: Dict[str, dict] = {}
_sessions_db: Dict[str, dict] = {}
_session_ttl = 86400  # 24 hours

# Password requirements
MIN_PASSWORD_LENGTH = 8
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_DIGIT = True
PASSWORD_REQUIRE_SPECIAL = False

# Rate limiting
_rate_limits: Dict[str, List[float]] = {}
RATE_LIMIT_REQUESTS = 100  # per window
RATE_LIMIT_WINDOW = 60  # seconds


def _create_password_hash(password: str, salt: str = "") -> str:
    """Create secure password hash with salt"""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode(),
        salt.encode(),
        100000
    ).hex()


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength"""
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    
    if PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if PASSWORD_REQUIRE_DIGIT and not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    if PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, ""


def check_rate_limit(identifier: str) -> tuple[bool, str]:
    """Check if requester has exceeded rate limit"""
    now = datetime.now().timestamp()
    
    # Clean old entries
    if identifier in _rate_limits:
        _rate_limits[identifier] = [t for t in _rate_limits[identifier] if now - t < RATE_LIMIT_WINDOW]
    
    # Check limit
    if identifier not in _rate_limits:
        _rate_limits[identifier] = []
    
    if len(_rate_limits[identifier]) >= RATE_LIMIT_REQUESTS:
        return False, f"Rate limit exceeded. Max {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW}s"
    
    # Add current request
    _rate_limits[identifier].append(now)
    return True, ""


class AuthService:
    """Production-ready authentication service"""
    
    def __init__(self, storage=None):
        self.storage = storage
        self._load_users()
    
    def _load_users(self):
        """Load users from database"""
        # Placeholder - in production load from database
        pass
    
    def register(self, username: str, email: str, password: str) -> tuple[Optional[dict], str]:
        """Register new user"""
        # Validate username
        if not username or len(username) < 3:
            return None, "Username must be at least 3 characters"
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return None, "Username can only contain letters, numbers, and underscores"
        
        # Validate email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return None, "Invalid email format"
        
        # Validate password
        valid, error = validate_password(password)
        if not valid:
            return None, error
        
        # Check if user exists
        if username in _users_db:
            return None, "Username already exists"
        
        # Create user
        salt = secrets.token_hex(16)
        user_id = f"user-{secrets.token_hex(8)}"
        
        user = {
            "user_id": user_id,
            "username": username,
            "email": email,
            "password_hash": _create_password_hash(password, salt),
            "salt": salt,
            "role": "user",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "failed_attempts": 0,
            "locked_until": None,
        }
        
        _users_db[username] = user
        
        # Return user without sensitive data
        return {k: v for k, v in user.items() if k not in ('password_hash', 'salt')}, ""
    
    def authenticate(self, username: str, password: str) -> tuple[Optional[dict], str]:
        """Authenticate user with rate limiting"""
        # Check rate limit
        allowed, error = check_rate_limit(f"auth:{username}")
        if not allowed:
            return None, error
        
        user = _users_db.get(username)
        if not user:
            return None, "Invalid username or password"
        
        # Check if account is locked
        if user.get("locked_until"):
            locked_until = datetime.fromisoformat(user["locked_until"])
            if locked_until > datetime.now():
                return None, "Account is temporarily locked. Try again later."
        
        # Verify password
        password_hash = _create_password_hash(password, user.get("salt", ""))
        
        if password_hash != user.get("password_hash"):
            # Failed attempt
            user["failed_attempts"] = user.get("failed_attempts", 0) + 1
            
            # Lock after 5 failed attempts
            if user["failed_attempts"] >= 5:
                user["locked_until"] = (datetime.now() + timedelta(minutes=15)).isoformat()
                return None, "Too many failed attempts. Account locked for 15 minutes."
            
            return None, "Invalid username or password"
        
        # Reset failed attempts on successful login
        user["failed_attempts"] = 0
        user["locked_until"] = None
        user["last_login"] = datetime.now().isoformat()
        
        # Create session
        session = self._create_session(user["user_id"])
        
        return {
            "user": {k: v for k, v in user.items() if k not in ('password_hash', 'salt')},
            "session": session
        }, ""
    
    def _create_session(self, user_id: str) -> dict:
        """Create new session"""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now()
        
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=_session_ttl)).isoformat(),
            "last_active_at": now.isoformat(),
        }
        
        _sessions_db[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get valid session"""
        session = _sessions_db.get(session_id)
        if not session:
            return None
        
        # Check expiration
        if datetime.fromisoformat(session["expires_at"]) < datetime.now():
            del _sessions_db[session_id]
            return None
        
        # Refresh activity
        session["last_active_at"] = datetime.now().isoformat()
        return session
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        if session_id in _sessions_db:
            del _sessions_db[session_id]
            return True
        return False
    
    def get_user(self, user_id: str) -> Optional[dict]:
        """Get user by ID"""
        for user in _users_db.values():
            if user["user_id"] == user_id:
                return {k: v for k, v in user.items() if k not in ('password_hash', 'salt')}
        return None
    
    def require_role(self, required_role: str):
        """Decorator to require specific role"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                user = kwargs.get("current_user")
                if not user or user.get("role") != required_role:
                    return {"error": "Insufficient permissions"}, 403
                return await func(*args, **kwargs)
            return wrapper
        return decorator


# Global instance
auth_service = AuthService()


# Demo login - requires username but password can be empty for testing
def demo_login(username: str) -> tuple[Optional[dict], str]:
    """Demo mode login - creates user if doesn't exist"""
    if not username:
        return None, "Username required"
    
    # Sanitize username
    username = username.strip().lower()
    
    if username not in _users_db:
        # Create demo user
        user_id = f"user-{secrets.token_hex(8)}"
        _users_db[username] = {
            "user_id": user_id,
            "username": username,
            "email": f"{username}@demo.local",
            "password_hash": None,
            "salt": None,
            "role": "user",
            "created_at": datetime.now().isoformat(),
            "last_login": datetime.now().isoformat(),
            "failed_attempts": 0,
            "locked_until": None,
        }
    
    user = _users_db[username]
    user["last_login"] = datetime.now().isoformat()
    
    session = auth_service._create_session(user["user_id"])
    
    return {
        "user": {k: v for k, v in user.items() if k not in ('password_hash', 'salt')},
        "session": session
    }, ""