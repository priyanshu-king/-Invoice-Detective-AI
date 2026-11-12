from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuthSession, Invoice, User, Workspace, WorkspaceMembership
from app.schemas import (
    AuthResponse,
    AuthenticatedUserResponse,
    AuthenticatedWorkspaceResponse,
    LoginRequest,
    RegisterRequest,
)
from app.security import (
    AuthenticatedPrincipal,
    create_session_token,
    get_current_principal,
    hash_password,
    hash_session_token,
    require_loopback_auth_request,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_LIFETIME = timedelta(hours=12)


def _issue_session(db: Session, user: User, workspace: Workspace, role: str) -> AuthResponse:
    raw_token = create_session_token()
    expires_at = datetime.utcnow() + SESSION_LIFETIME
    db.add(AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        expires_at=expires_at,
    ))
    db.commit()
    return AuthResponse(
        access_token=raw_token,
        expires_at=expires_at,
        user=AuthenticatedUserResponse(id=user.id, email=user.email, role=role),
        workspace=AuthenticatedWorkspaceResponse(id=workspace.id, name=workspace.name),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    local_request: None = Depends(require_loopback_auth_request),
    db: Session = Depends(get_db),
) -> AuthResponse:

    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))

    if db.query(User.id).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    is_first_account = db.query(User.id).first() is None
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    workspace = Workspace(name=payload.workspace_name.strip())
    db.add_all([user, workspace])
    db.flush()
    membership = WorkspaceMembership(user_id=user.id, workspace_id=workspace.id, role="owner")
    db.add(membership)

    if is_first_account:
        db.query(Invoice).filter(Invoice.workspace_id.is_(None)).update(
            {Invoice.workspace_id: workspace.id},
            synchronize_session=False,
        )

    db.flush()
    response = _issue_session(db, user, workspace, membership.role)
    return response


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    local_request: None = Depends(require_loopback_auth_request),
    db: Session = Depends(get_db),
) -> AuthResponse:

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

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
    return _issue_session(db, user, workspace, workspace_membership.role)


@router.get("/me")
def get_me(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> dict:
    return {
        "user": {
            "id": principal.user_id,
            "email": principal.email,
            "role": principal.role,
        },
        "workspace": {
            "id": principal.workspace_id,
            "name": principal.workspace_name,
        },
    }


@router.post("/logout")
def logout(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    session = db.query(AuthSession).filter(AuthSession.id == principal.session_id).first()
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.utcnow()
        db.commit()
    return {"logged_out": True}
