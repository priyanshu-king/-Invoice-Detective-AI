from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserPreferences, Workspace, WorkspacePreferences
from app.schemas import WorkspaceSettingsUpdate
from app.security import AuthenticatedPrincipal, get_current_principal


router = APIRouter(prefix="/settings", tags=["settings"])


def _serialize_settings(
    workspace: Workspace,
    preferences: WorkspacePreferences | None,
    user_preferences: UserPreferences | None,
    principal: AuthenticatedPrincipal,
) -> dict:
    return {
        "workspace_name": workspace.name,
        "business_name": preferences.business_name if preferences else "",
        "default_currency": preferences.default_currency if preferences else "INR",
        "date_format": preferences.date_format if preferences else "YYYY-MM-DD",
        "time_zone": preferences.time_zone if preferences else "Asia/Kolkata",
        "language": preferences.language if preferences else "en",
        "default_tax_rate": preferences.default_tax_rate if preferences else None,
        "invoice_number_prefix": preferences.invoice_number_prefix if preferences else "",
        "default_review_status": preferences.default_review_status if preferences else "needs_review",
        "notifications": {
            "audit_completion": preferences.notify_audit_completion if preferences else True,
            "duplicate_detection": preferences.notify_duplicate_detection if preferences else True,
            "failed_upload": preferences.notify_failed_upload if preferences else True,
            "review_reminders": preferences.notify_review_reminders if preferences else False,
        },
        "profile": {
            "display_name": user_preferences.display_name if user_preferences else "",
            "email": principal.email,
        },
        "appearance": user_preferences.appearance if user_preferences else "light",
        "authentication": {
            "status": "local password account",
            "session_information": "Local sessions expire after 12 hours; this page does not display the active session expiry.",
            "password_management": "Password changes and recovery are not available in this local build.",
        },
    }


@router.get("")
def get_settings(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    workspace = db.query(Workspace).filter(Workspace.id == principal.workspace_id).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    preferences = db.query(WorkspacePreferences).filter(
        WorkspacePreferences.workspace_id == principal.workspace_id
    ).first()
    user_preferences = db.query(UserPreferences).filter(
        UserPreferences.user_id == principal.user_id
    ).first()
    return _serialize_settings(workspace, preferences, user_preferences, principal)


@router.put("")
def update_settings(
    payload: WorkspaceSettingsUpdate,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    if principal.role != "owner":
        raise HTTPException(status_code=403, detail="Only a workspace owner can update workspace settings.")

    workspace = db.query(Workspace).filter(Workspace.id == principal.workspace_id).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    workspace_preferences = db.query(WorkspacePreferences).filter(
        WorkspacePreferences.workspace_id == principal.workspace_id
    ).first()
    if workspace_preferences is None:
        workspace_preferences = WorkspacePreferences(workspace_id=principal.workspace_id)
        db.add(workspace_preferences)

    user_preferences = db.query(UserPreferences).filter(
        UserPreferences.user_id == principal.user_id
    ).first()
    if user_preferences is None:
        user_preferences = UserPreferences(user_id=principal.user_id)
        db.add(user_preferences)

    values = payload.model_dump()
    workspace.name = values.pop("workspace_name")
    user_preferences.display_name = values.pop("profile_display_name")
    user_preferences.appearance = values.pop("appearance")
    values.pop("notify_audit_completion")
    values.pop("notify_duplicate_detection")
    values.pop("notify_failed_upload")
    values.pop("notify_review_reminders")
    for field, value in values.items():
        setattr(workspace_preferences, field, value)
    workspace_preferences.notify_audit_completion = payload.notify_audit_completion
    workspace_preferences.notify_duplicate_detection = payload.notify_duplicate_detection
    workspace_preferences.notify_failed_upload = payload.notify_failed_upload
    workspace_preferences.notify_review_reminders = payload.notify_review_reminders

    db.commit()
    db.refresh(workspace)
    db.refresh(workspace_preferences)
    db.refresh(user_preferences)
    return _serialize_settings(workspace, workspace_preferences, user_preferences, principal)
