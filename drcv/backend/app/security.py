"""Password hashing, JWT tokens, role permissions and FastAPI auth dependencies."""
import base64
import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import AuditLog, Case, CaseAssignment, User

# ---------------------------------------------------------------- passwords
_ITER = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def password_policy_error(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isupper() for c in password) or not any(c.islower() for c in password):
        return "Password must contain upper and lower case letters."
    if not any(c.isdigit() for c in password):
        return "Password must contain a number."
    return None


# ---------------------------------------------------------------- roles
ROLE_LABELS = {"admin": "Admin", "investigator": "Investigator", "reviewer": "Reviewer", "viewer": "Viewer"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "dashboard:view", "case:view", "case:create", "case:update", "case:archive", "case:delete", "case:assign",
        "record:view", "record:upload", "record:delete", "analysis:run", "analysis:view",
        "conflict:review", "review:note", "report:generate", "report:view",
        "audit:view", "audit:export", "user:manage", "settings:manage", "case:view_all",
    },
    "investigator": {
        "dashboard:view", "case:view", "case:create", "case:update", "record:view", "record:upload",
        "analysis:run", "analysis:view", "review:note", "report:generate", "report:view", "audit:view",
        "case:view_all",
    },
    "reviewer": {
        "dashboard:view", "case:view", "record:view", "analysis:view", "conflict:review", "review:note",
        "report:generate", "report:view", "audit:view",
    },
    "viewer": {
        "dashboard:view", "case:view", "record:view", "analysis:view", "report:view", "case:view_all",
    },
}

PERMISSION_LABELS = {
    "dashboard:view": "View dashboard", "case:view": "View cases", "case:create": "Create cases",
    "case:update": "Edit cases", "case:archive": "Archive cases", "case:delete": "Delete cases",
    "case:assign": "Assign reviewers", "record:view": "View records", "record:upload": "Upload records",
    "record:delete": "Delete records", "analysis:run": "Run analysis", "analysis:view": "View analysis",
    "conflict:review": "Resolve / accept / escalate conflicts", "review:note": "Add review notes",
    "report:generate": "Generate reports", "report:view": "View & download reports",
    "audit:view": "View audit logs (read-only)", "audit:export": "Export audit logs",
    "user:manage": "Manage users", "settings:manage": "Manage system settings",
    "case:view_all": "See all cases (reviewers only see assigned cases)",
}


def permissions_for(role: str) -> set[str]:
    return ROLE_PERMISSIONS.get(role, set())


# ---------------------------------------------------------------- tokens
def create_token(user: User, remember: bool = False) -> str:
    hours = config.REMEMBER_TTL_HOURS if remember else config.TOKEN_TTL_HOURS
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "role": user.role, "tv": user.token_version or 0, "iat": now,
               "exp": now + timedelta(hours=hours)}
    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid authentication token.")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    if not token:
        raise HTTPException(401, "Authentication required.")
    data = _decode(token)
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "Account not found or disabled.")
    if int(data.get("tv", 0)) != (user.token_version or 0):
        raise HTTPException(401, "Your session ended because the account's password or security settings changed. Please sign in again.")
    return user


# ---------------------------------------------------------------- TOTP two-factor authentication (RFC 6238)
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    code = (int.from_bytes(digest[off:off + 4], "big") & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str | None, code: str | None, window: int = 1) -> bool:
    if not secret or not code:
        return False
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6:
        return False
    counter = int(datetime.now(timezone.utc).timestamp()) // 30
    return any(hmac.compare_digest(totp_at(secret, counter + d), code) for d in range(-window, window + 1))


# ---------------------------------------------------------------- audit (hash-chained, tamper-evident)
_audit_lock = threading.Lock()


def _ts_str(ts) -> str:
    if ts is None:
        return ""
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts.isoformat(timespec="microseconds")


def entry_hash(prev: str | None, e: AuditLog) -> str:
    payload = json.dumps([prev or "", _ts_str(e.ts), e.user_id, e.user_name, e.role, e.action, e.category,
                          e.target_type, e.target_id, e.target_label, e.case_id, e.record_id, e.result, e.details or ""],
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def audit(db: Session, user: User | None, action: str, *, category: str = "general", target_type=None,
          target_id=None, target_label=None, case_id=None, record_id=None, result="success", details="",
          ts=None, commit=True):
    """Appends an audit entry whose hash covers the previous entry's hash (a hash chain).
    Written in its own session under a lock so the chain order is strict."""
    from .db import SessionLocal
    with _audit_lock:
        s = SessionLocal()
        try:
            last = s.query(AuditLog.entry_hash).order_by(AuditLog.id.desc()).first()
            prev = last[0] if last else None
            e = AuditLog(
                user_id=user.id if user else None,
                user_name=user.name if user else "System",
                role=ROLE_LABELS.get(user.role, user.role) if user else "System",
                action=action[:200], category=category, target_type=target_type, target_id=target_id,
                target_label=(target_label or None) and str(target_label)[:255], case_id=case_id, record_id=record_id,
                result=result, details=details or "",
                ts=(ts or datetime.now(timezone.utc)),
            )
            # normalise to what the database will hand back, so verification is exact
            e.ts = e.ts.astimezone(timezone.utc) if e.ts.tzinfo else e.ts.replace(tzinfo=timezone.utc)
            e.ts = e.ts.replace(microsecond=e.ts.microsecond)
            e.prev_hash = prev
            e.entry_hash = entry_hash(prev, e)
            s.add(e)
            s.commit()
            return e
        finally:
            s.close()


def rechain_from(first_id: int | None = None) -> int:
    """Recomputes the chain from first_id onward (used after seeding synthetic history, and to
    backfill databases created before the chain existed). Returns entries rewritten."""
    from .db import SessionLocal
    with _audit_lock:
        s = SessionLocal()
        try:
            q = s.query(AuditLog).order_by(AuditLog.id)
            prev = None
            if first_id:
                before = s.query(AuditLog.entry_hash).filter(AuditLog.id < first_id).order_by(AuditLog.id.desc()).first()
                prev = before[0] if before else None
                q = q.filter(AuditLog.id >= first_id)
            n = 0
            for e in q:
                e.prev_hash = prev
                e.entry_hash = entry_hash(prev, e)
                prev = e.entry_hash
                n += 1
            s.commit()
            return n
        finally:
            s.close()


def verify_chain(db: Session) -> dict:
    prev, n = None, 0
    for e in db.query(AuditLog).order_by(AuditLog.id).yield_per(500):
        if e.prev_hash != prev or e.entry_hash != entry_hash(prev, e):
            return {"ok": False, "checked": n, "broken_at": e.id, "broken_ts": _ts_str(e.ts),
                    "message": f"Audit entry #{e.id} does not match the chain — it or an earlier entry was altered or removed."}
        prev = e.entry_hash
        n += 1
    return {"ok": True, "checked": n, "broken_at": None, "head": prev,
            "message": f"All {n} audit entries are intact and correctly chained."}


def require(permission: str):
    """Dependency factory: enforces a permission on the backend and audits denials."""
    def dep(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if permission not in permissions_for(user.role):
            audit(db, user, f"Access denied: {PERMISSION_LABELS.get(permission, permission)}",
                  category="security", result="denied",
                  details=f"{request.method} {request.url.path} requires '{permission}'")
            raise HTTPException(403, f"Your role ({ROLE_LABELS.get(user.role)}) is not permitted to "
                                     f"{PERMISSION_LABELS.get(permission, permission).lower()}.")
        return user
    return dep


def has(user: User, permission: str) -> bool:
    return permission in permissions_for(user.role)


def accessible_case_ids(db: Session, user: User) -> list[int] | None:
    """None means all cases. Reviewers only see cases assigned to them."""
    if has(user, "case:view_all"):
        return None
    return [a.case_id for a in db.query(CaseAssignment).filter(CaseAssignment.user_id == user.id)]


def get_case_or_404(db: Session, user: User, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found.")
    allowed = accessible_case_ids(db, user)
    if allowed is not None and case.id not in allowed:
        audit(db, user, "Access denied: case not assigned", category="security", result="denied",
              target_type="case", target_id=case.id, target_label=case.code, case_id=case.id)
        raise HTTPException(403, "This case has not been assigned to you.")
    return case
