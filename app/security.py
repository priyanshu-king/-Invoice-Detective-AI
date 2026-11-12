"""Authentication helpers and workspace-scoped request dependencies."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import ipaddress
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import AuthSession, User, Workspace, WorkspaceMembership


bearer_scheme = HTTPBearer(auto_error=False)
_PASSWORD_SCRYPT_N = 2 ** 14
_PASSWORD_SCRYPT_R = 8
_PASSWORD_SCRYPT_P = 1


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: int
    email: str
    workspace_id: int
    workspace_name: str
    role: str
    session_id: int


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_PASSWORD_SCRYPT_N,
        r=_PASSWORD_SCRYPT_R,
        p=_PASSWORD_SCRYPT_P,
        dklen=64,
    )
    return f"scrypt${_PASSWORD_SCRYPT_N}${_PASSWORD_SCRYPT_R}${_PASSWORD_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded_hash.split("$", 5)
        if (
            algorithm != "scrypt"
            or int(n) != _PASSWORD_SCRYPT_N
            or int(r) != _PASSWORD_SCRYPT_R
            or int(p) != _PASSWORD_SCRYPT_P
        ):
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=_PASSWORD_SCRYPT_N,
            r=_PASSWORD_SCRYPT_R,
            p=_PASSWORD_SCRYPT_P,
            dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(derived, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def require_loopback_auth_request(request: Request) -> None:
    if request.client is None:
        raise HTTPException(status_code=403, detail="Authentication is limited to this machine.")
    try:
        client_is_loopback = ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        client_is_loopback = False
    try:
        server_is_loopback = ipaddress.ip_address(settings.HOST).is_loopback
    except ValueError:
        server_is_loopback = settings.HOST == "localhost"
    if not client_is_loopback or not server_is_loopback:
        raise HTTPException(status_code=403, detail="Authentication is limited to this machine.")


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == hash_session_token(credentials.credentials))
        .first()
    )
    now = datetime.utcnow()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(
            status_code=401,
            detail="Session is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == session.user_id, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Session is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    membership = (
        db.query(WorkspaceMembership, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .filter(WorkspaceMembership.user_id == user.id)
        .order_by(WorkspaceMembership.id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="No workspace is assigned to this account.")

    workspace_membership, workspace = membership
    return AuthenticatedPrincipal(
        user_id=user.id,
        email=user.email,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        role=workspace_membership.role,
        session_id=session.id,
    )


def get_current_workspace_id(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> int:
    return principal.workspace_id
