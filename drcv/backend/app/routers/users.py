import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import ROLE_LABELS, audit, hash_password, password_policy_error, require
from ..ser import user_out

router = APIRouter(prefix="/api/users", tags=["Users"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserIn(BaseModel):
    email: str = Field(max_length=255)
    name: str = Field(min_length=2, max_length=120)
    role: str
    password: str = Field(max_length=200)


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: str | None = None
    is_active: bool | None = None


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)


@router.get("")
def list_users(user: User = Depends(require("user:manage")), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.id)]


@router.get("/reviewers")
def list_reviewers(user: User = Depends(require("case:assign")), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).filter(User.role == "reviewer", User.is_active.is_(True))]


@router.post("", status_code=201)
def create_user(body: UserIn, user: User = Depends(require("user:manage")), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Please enter a valid email address.")
    if body.role not in ROLE_LABELS:
        raise HTTPException(422, "Unknown role.")
    if err := password_policy_error(body.password):
        raise HTTPException(422, err)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "A user with this email already exists.")
    u = User(email=email, name=body.name.strip(), role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    audit(db, user, f"Created user {u.email}", category="users", target_type="user", target_id=u.id,
          target_label=u.email, details=f"Role: {ROLE_LABELS[u.role]}")
    return user_out(u)


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserPatch, user: User = Depends(require("user:manage")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    changes = []
    if body.name is not None and body.name.strip() != u.name:
        changes.append(f"name → {body.name.strip()}")
        u.name = body.name.strip()
    if body.role is not None and body.role != u.role:
        if body.role not in ROLE_LABELS:
            raise HTTPException(422, "Unknown role.")
        if u.id == user.id:
            raise HTTPException(400, "You cannot change your own role.")
        changes.append(f"role {ROLE_LABELS[u.role]} → {ROLE_LABELS[body.role]}")
        u.role = body.role
    if body.is_active is not None and body.is_active != u.is_active:
        if u.id == user.id:
            raise HTTPException(400, "You cannot disable your own account.")
        changes.append("enabled" if body.is_active else "disabled")
        u.is_active = body.is_active
    db.commit()
    if changes:
        audit(db, user, f"Updated user {u.email}", category="users", target_type="user", target_id=u.id,
              target_label=u.email, details="; ".join(changes))
    return user_out(u)


@router.post("/{user_id}/password")
def reset_password(user_id: int, body: PasswordIn, user: User = Depends(require("user:manage")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    if err := password_policy_error(body.password):
        raise HTTPException(422, err)
    u.password_hash = hash_password(body.password)
    u.token_version = (u.token_version or 0) + 1
    db.commit()
    audit(db, user, f"Reset password for {u.email}", category="users", target_type="user", target_id=u.id,
          target_label=u.email)
    return {"ok": True}


@router.post("/{user_id}/reset-2fa")
def reset_2fa(user_id: int, user: User = Depends(require("user:manage")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    u.totp_enabled, u.totp_secret = False, None
    u.token_version = (u.token_version or 0) + 1
    db.commit()
    audit(db, user, f"Reset two-factor authentication for {u.email}", category="users", target_type="user",
          target_id=u.id, target_label=u.email)
    return user_out(u)
