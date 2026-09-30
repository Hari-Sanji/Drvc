import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, utcnow
from ..security import (PERMISSION_LABELS, ROLE_LABELS, ROLE_PERMISSIONS, audit, create_token, get_current_user,
                        hash_password, new_totp_secret, password_policy_error, permissions_for, verify_password,
                        verify_totp)
from ..ser import user_out

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

_fail_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 120

DEMO_ACCOUNTS = [
    {"role": "admin", "email": "admin@demo.local", "password": "Admin@123",
     "summary": "Full access: cases, records, reviews, users, settings, audit"},
    {"role": "investigator", "email": "investigator@demo.local", "password": "Investigator@123",
     "summary": "Create cases, upload records, run analysis, generate reports"},
    {"role": "reviewer", "email": "reviewer@demo.local", "password": "Reviewer@123",
     "summary": "Review assigned cases, resolve / accept / escalate conflicts"},
    {"role": "viewer", "email": "viewer@demo.local", "password": "Viewer@123",
     "summary": "Read-only access to cases, records, timeline and reports"},
]


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False
    code: str | None = Field(default=None, max_length=12)


def me_payload(u: User):
    return {"user": user_out(u), "permissions": sorted(permissions_for(u.role))}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    now = time.time()
    with _fail_lock:
        recent = [t for t in _failures.get(email, []) if now - t < WINDOW]
        _failures[email] = recent
        if len(recent) >= MAX_FAILS:
            raise HTTPException(429, "Too many failed sign-in attempts. Please wait two minutes and try again.")
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        with _fail_lock:
            _failures.setdefault(email, []).append(now)
        audit(db, user, "Failed sign-in attempt", category="auth", result="denied",
              details=f"Email: {email}" if not user else "Incorrect password")
        raise HTTPException(401, "Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(403, "This account has been disabled. Contact an administrator.")
    if user.totp_enabled:
        if not body.code:
            return {"requires_2fa": True, "message": "Enter the 6-digit code from your authenticator app."}
        if not verify_totp(user.totp_secret, body.code):
            with _fail_lock:
                _failures.setdefault(email, []).append(now)
            audit(db, user, "Failed two-factor code", category="auth", result="denied")
            raise HTTPException(401, "The authentication code is incorrect or has expired.")
    with _fail_lock:
        _failures.pop(email, None)
    user.last_login = utcnow()
    db.commit()
    audit(db, user, "Signed in", category="auth")
    return {"token": create_token(user, body.remember), **me_payload(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return me_payload(user)


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit(db, user, "Signed out", category="auth")
    return {"ok": True}


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Public list of synthetic demo credentials (only those that still exist and are active)."""
    active = {u.email for u in db.query(User).filter(User.is_demo.is_(True), User.is_active.is_(True))}
    return [dict(a, role_label=ROLE_LABELS[a["role"]]) for a in DEMO_ACCOUNTS if a["email"] in active]


@router.get("/roles")
def roles(user: User = Depends(get_current_user)):
    return {"roles": [{"key": r, "label": ROLE_LABELS[r], "permissions": sorted(p)} for r, p in ROLE_PERMISSIONS.items()],
            "permission_labels": PERMISSION_LABELS}


# ---------------------------------------------------------------- self-service security
class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        audit(db, user, "Failed password change (wrong current password)", category="auth", result="denied")
        raise HTTPException(400, "Your current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(422, "The new password must be different from the current one.")
    if err := password_policy_error(body.new_password):
        raise HTTPException(422, err)
    user.password_hash = hash_password(body.new_password)
    user.token_version = (user.token_version or 0) + 1  # signs out every other session
    db.commit()
    audit(db, user, "Changed own password", category="auth", details="All other sessions were signed out")
    return {"token": create_token(user), **me_payload(user)}


class CodeIn(BaseModel):
    code: str = Field(max_length=12)


class DisableIn(BaseModel):
    password: str = Field(max_length=200)
    code: str | None = Field(default=None, max_length=12)


@router.post("/2fa/setup")
def totp_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(409, "Two-factor authentication is already enabled.")
    user.totp_secret = new_totp_secret()
    db.commit()
    from urllib.parse import quote
    uri = f"otpauth://totp/DRCV:{quote(user.email)}?secret={user.totp_secret}&issuer=DRCV&digits=6&period=30"
    svg = None
    try:
        import segno
        svg = segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#1a1512", light="#ffffff")
    except Exception:
        pass
    return {"secret": user.totp_secret, "otpauth_uri": uri, "qr_svg": svg}


@router.post("/2fa/enable")
def totp_enable(body: CodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(409, "Two-factor authentication is already enabled.")
    if not user.totp_secret:
        raise HTTPException(400, "Start the setup first.")
    if not verify_totp(user.totp_secret, body.code):
        raise HTTPException(400, "That code did not match. Check your phone's time and try the newest code.")
    user.totp_enabled = True
    db.commit()
    audit(db, user, "Enabled two-factor authentication", category="auth")
    return me_payload(user)


@router.post("/2fa/disable")
def totp_disable(body: DisableIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "Your password is incorrect.")
    if user.totp_enabled and not verify_totp(user.totp_secret, body.code):
        raise HTTPException(400, "The authentication code is incorrect.")
    user.totp_enabled, user.totp_secret = False, None
    db.commit()
    audit(db, user, "Disabled two-factor authentication", category="auth")
    return me_payload(user)
