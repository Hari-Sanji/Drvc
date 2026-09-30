import csv
import io
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..models import AuditLog, Case, Conflict, Entity, Event, Record, Relationship, ReviewAction, User, utcnow
from ..pipeline.analysis import run_case_job
from ..pipeline.extract import ocr_engine_name
from ..pipeline.nlp import fmt_date
from ..security import accessible_case_ids, audit, get_current_user, has, require, verify_chain
from ..ser import UNRESOLVED, ilike_any, iso, record_brief
from ..settings_store import DEFAULTS, get_settings, set_setting

router = APIRouter(prefix="/api", tags=["Platform"])


def _case_scope(db, user):
    q = db.query(Case.id).filter(Case.archived.is_(False))
    allowed = accessible_case_ids(db, user)
    if allowed is not None:
        q = q.filter(Case.id.in_(allowed or [-1]))
    return [cid for (cid,) in q]


# ------------------------------------------------------------------ dashboard
CONFLICT_BUCKETS = {"Date Mismatch": "Date mismatch", "Identity Mismatch": "Identity mismatch",
                    "Location Mismatch": "Location mismatch", "Identifier Mismatch": "Identifier mismatch"}


@router.get("/dashboard")
def dashboard(user: User = Depends(require("dashboard:view")), db: Session = Depends(get_db)):
    ids = _case_scope(db, user) or [-1]
    recs = db.query(Record).filter(Record.case_id.in_(ids)).all()
    rels = db.query(Relationship).filter(Relationship.case_id.in_(ids)).all()
    related = {r.source_record_id for r in rels} | {r.target_record_id for r in rels}
    confs = db.query(Conflict).filter(Conflict.case_id.in_(ids)).all()
    cases = db.query(Case).filter(Case.id.in_(ids)).all()

    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    proc = {d: 0 for d in days}
    for r in recs:
        if r.processed_at:
            d = r.processed_at.date() if r.processed_at.tzinfo is None else r.processed_at.astimezone(timezone.utc).date()
            if d in proc:
                proc[d] += 1
    rev = {d: 0 for d in days}
    since = datetime.combine(days[0], datetime.min.time()).replace(tzinfo=timezone.utc)
    for (ts,) in db.query(ReviewAction.created_at).filter(ReviewAction.case_id.in_(ids), ReviewAction.created_at >= since):
        d = ts.date() if ts.tzinfo is None else ts.astimezone(timezone.utc).date()
        if d in rev:
            rev[d] += 1

    status = {"active": 0, "processing": 0, "requires_review": 0, "completed": 0}
    for c in cases:
        status[c.status] = status.get(c.status, 0) + 1
    dist = {v: 0 for v in CONFLICT_BUCKETS.values()} | {"Other": 0}
    for c in confs:
        dist[CONFLICT_BUCKETS.get(c.type, "Other")] += 1

    feed_q = db.query(AuditLog).filter(AuditLog.category.in_(["upload", "pipeline", "conflict", "review", "report", "case", "analysis", "integrity"]))
    if accessible_case_ids(db, user) is not None:
        feed_q = feed_q.filter(AuditLog.case_id.in_(ids))
    feed = feed_q.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(14).all()
    return {
        "stats": {
            "total_records": len(recs), "integrity_verified": sum(1 for r in recs if r.sha256),
            "related_records": len(related), "potential_conflicts": len(confs),
            "requires_review": sum(1 for c in confs if c.status in UNRESOLVED),
            "cases": len(cases), "entities": db.query(Entity).filter(Entity.case_id.in_(ids)).count(),
            "events": db.query(Event).filter(Event.case_id.in_(ids)).count(), "relationships": len(rels),
            "resolved": sum(1 for c in confs if c.status not in UNRESOLVED),
        },
        "activity": [{"date": d.isoformat(), "processed": proc[d], "reviews": rev[d]} for d in days],
        "case_status": status,
        "conflict_distribution": dist,
        "recent": [{"id": a.id, "ts": iso(a.ts), "user": a.user_name, "role": a.role, "action": a.action,
                    "category": a.category, "target": a.target_label, "case_id": a.case_id, "record_id": a.record_id,
                    "result": a.result} for a in feed],
        "cases": [{"id": c.id, "code": c.code, "name": c.name, "status": c.status, "is_demo": c.is_demo} for c in cases],
    }


# ------------------------------------------------------------------ audit
@router.get("/audit")
def audit_logs(case_id: int | None = None, record_id: int | None = None, category: str | None = None,
               result: str | None = None, q: str | None = None, page: int = Query(1, ge=1),
               page_size: int = Query(50, ge=1, le=200), user: User = Depends(require("audit:view")),
               db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    if not has(user, "user:manage"):
        allowed = accessible_case_ids(db, user)
        if allowed is not None:
            query = query.filter(AuditLog.case_id.in_(allowed or [-1]))
        # non-admins do not see security/user-management entries of other users
        query = query.filter(or_(AuditLog.category.notin_(["security", "users", "auth", "settings"]), AuditLog.user_id == user.id))
    if case_id:
        query = query.filter(AuditLog.case_id == case_id)
    if record_id:
        query = query.filter(AuditLog.record_id == record_id)
    if category:
        query = query.filter(AuditLog.category == category)
    if result:
        query = query.filter(AuditLog.result == result)
    if q:
        query = query.filter(ilike_any([AuditLog.action, AuditLog.user_name, AuditLog.target_label, AuditLog.details], q.strip()))
    total = query.count()
    rows = query.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [{"id": a.id, "ts": iso(a.ts), "user": a.user_name, "role": a.role, "action": a.action,
                       "category": a.category, "target_type": a.target_type, "target_id": a.target_id,
                       "target": a.target_label, "case_id": a.case_id, "record_id": a.record_id, "result": a.result,
                       "details": a.details, "hash": a.entry_hash} for a in rows], "total": total, "page": page, "page_size": page_size,
            "read_only": True}


@router.get("/audit/verify")
def audit_verify(user: User = Depends(require("audit:view")), db: Session = Depends(get_db)):
    """Recomputes the SHA-256 hash chain over the whole audit log."""
    res = verify_chain(db)
    audit(db, user, "Verified audit log integrity", category="audit", result="success" if res["ok"] else "failed",
          details=res["message"])
    return res


@router.get("/audit/export")
def audit_export(user: User = Depends(require("audit:export")), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "timestamp_utc", "user", "role", "action", "category", "target_type", "target", "case_id",
                "record_id", "result", "details", "prev_hash", "entry_hash"])
    for a in db.query(AuditLog).order_by(AuditLog.id):
        w.writerow([a.id, iso(a.ts), a.user_name, a.role, a.action, a.category, a.target_type, a.target_label,
                    a.case_id, a.record_id, a.result, a.details, a.prev_hash, a.entry_hash])
    audit(db, user, "Exported audit log", category="audit")
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="drcv-audit-log.csv"'})


# ------------------------------------------------------------------ search
@router.get("/search")
def search(q: str = Query("", max_length=120), case_id: int | None = None, kind: str | None = None,
           status: str | None = None, date_from: str | None = None, date_to: str | None = None,
           conflict: str | None = None, review: str | None = None, limit: int = Query(8, ge=1, le=50),
           user: User = Depends(require("case:view")), db: Session = Depends(get_db)):
    q = q.strip()
    scope = _case_scope(db, user)
    if case_id:
        scope = [c for c in scope if c == case_id]
    scope = scope or [-1]
    out = {"cases": [], "records": [], "entities": [], "events": [], "conflicts": []}
    if len(q) < 2 and not any([kind, status, date_from, date_to, conflict, review]):
        return out
    cq = db.query(Case).filter(Case.id.in_(scope))
    if q:
        cq = cq.filter(ilike_any([Case.name, Case.code, Case.description, Case.category], q))
    if status in ("active", "processing", "requires_review", "completed"):
        cq = cq.filter(Case.status == status)
    out["cases"] = [{"id": c.id, "code": c.code, "name": c.name, "status": c.status} for c in cq.limit(limit)]

    conflict_rec_ids = {i for c in db.query(Conflict).filter(Conflict.case_id.in_(scope)) for i in (c.record_a_id, c.record_b_id)}
    rq = db.query(Record).filter(Record.case_id.in_(scope))
    if q:
        rq = rq.filter(ilike_any([Record.filename, Record.doc_type, Record.sha256, Record.text], q))
    if kind:
        rq = rq.filter(or_(Record.kind == kind, Record.ext == "." + kind.lower()))
    if status in ("Completed", "Requires Review", "Failed"):
        rq = rq.filter(Record.status == status)
    if conflict == "yes":
        rq = rq.filter(Record.id.in_(conflict_rec_ids or {-1}))
    elif conflict == "no":
        rq = rq.filter(Record.id.notin_(conflict_rec_ids or {-1}))
    if date_from:
        rq = rq.filter(Record.uploaded_at >= date_from)
    if date_to:
        rq = rq.filter(Record.uploaded_at <= date_to + "T23:59:59")
    for r in rq.limit(limit):
        b = record_brief(r)
        idx = (r.text or "").lower().find(q.lower()) if q else -1
        b["snippet"] = (r.text[max(0, idx - 50): idx + 80].replace("\n", " ") if idx >= 0 else "")
        out["records"].append(b)

    if q:
        groups = {}
        for e in db.query(Entity).filter(Entity.case_id.in_(scope), ilike_any([Entity.value], q)).limit(200):
            g = groups.setdefault((e.type, e.norm), {"type": e.type, "value": e.value, "case_id": e.case_id, "record_ids": []})
            if e.record_id not in g["record_ids"]:
                g["record_ids"].append(e.record_id)
        out["entities"] = list(groups.values())[:limit * 2]
    eq = db.query(Event).filter(Event.case_id.in_(scope))
    if q:
        eq = eq.filter(ilike_any([Event.label, Event.snippet, Event.date], q))
    if date_from:
        eq = eq.filter(Event.date >= date_from)
    if date_to:
        eq = eq.filter(Event.date <= date_to)
    if q or date_from or date_to:
        out["events"] = [{"id": e.id, "date": e.date, "date_label": fmt_date(e.date), "label": e.label,
                          "record_id": e.record_id, "case_id": e.case_id} for e in eq.order_by(Event.date).limit(limit)]
    xq = db.query(Conflict).filter(Conflict.case_id.in_(scope))
    if q:
        xq = xq.filter(ilike_any([Conflict.type, Conflict.field, Conflict.value_a, Conflict.value_b], q))
    if review == "open":
        xq = xq.filter(Conflict.status.in_(UNRESOLVED))
    elif review == "done":
        xq = xq.filter(Conflict.status.notin_(UNRESOLVED))
    if q or review:
        out["conflicts"] = [{"id": c.id, "type": c.type, "field": c.field, "status": c.status, "case_id": c.case_id}
                            for c in xq.limit(limit)]
    return out


# ------------------------------------------------------------------ notifications
NOTIFY_CATEGORIES = ["conflict", "review", "report", "analysis", "case"]


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(AuditLog).filter(or_(AuditLog.category.in_(NOTIFY_CATEGORIES), AuditLog.result == "failed"))
    allowed = accessible_case_ids(db, user)
    if allowed is not None:
        q = q.filter(AuditLog.case_id.in_(allowed or [-1]))
    items = q.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(20).all()
    seen = user.notif_seen_at
    def unread(a):
        if not seen:
            return True
        ts, s = a.ts, seen
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if s.tzinfo is None:
            s = s.replace(tzinfo=timezone.utc)
        return ts > s
    return {"items": [{"id": a.id, "ts": iso(a.ts), "action": a.action, "user": a.user_name, "target": a.target_label,
                       "category": a.category, "case_id": a.case_id, "record_id": a.record_id, "result": a.result,
                       "unread": unread(a)} for a in items],
            "unread": sum(1 for a in items if unread(a))}


@router.post("/notifications/seen")
def notifications_seen(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.notif_seen_at = utcnow()
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ settings
class SettingsIn(BaseModel):
    organization_name: str | None = None
    ocr_enabled: bool | None = None
    max_upload_mb: int | None = None
    similarity_threshold: float | None = None
    relationship_min_score: float | None = None
    name_variation_threshold: float | None = None
    low_ocr_confidence: int | None = None
    show_demo_guide: bool | None = None


@router.get("/settings")
def get_settings_api(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings(db)
    return {"settings": s, "editable": has(user, "settings:manage"),
            "system": {"ocr_engine": ocr_engine_name() or "Not installed",
                       "database": "PostgreSQL" if config.DATABASE_URL.startswith("postgresql") else "SQLite (local fallback)",
                       "storage": "Local secure storage (opaque keys)", "hash_algorithm": "SHA-256",
                       "nlp": "Deterministic (regex, date parsing, gazetteer, TF-IDF cosine, fuzzy matching)",
                       "allowed_types": sorted(e[1:].upper() for e in config.ALLOWED_EXTENSIONS),
                       "version": "1.0.0"}}


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(require("settings:manage")), db: Session = Depends(get_db)):
    ranges = {"max_upload_mb": (1, 100), "similarity_threshold": (0.01, 0.9), "relationship_min_score": (0.05, 0.9),
              "name_variation_threshold": (0.5, 0.99), "low_ocr_confidence": (10, 99)}
    changed = []
    for k, v in body.model_dump(exclude_none=True).items():
        if k in ranges and not (ranges[k][0] <= v <= ranges[k][1]):
            raise HTTPException(422, f"{k.replace('_', ' ').title()} must be between {ranges[k][0]} and {ranges[k][1]}.")
        if k == "organization_name":
            v = v.strip()[:120] or DEFAULTS[k]
        set_setting(db, k, v)
        changed.append(f"{k}={v}")
    db.commit()
    audit(db, user, "Updated system settings", category="settings", details=", ".join(changed))
    return get_settings_api(user, db)


@router.post("/settings/reset-demo")
def reset_demo(user: User = Depends(require("settings:manage")), db: Session = Depends(get_db)):
    from ..seed import reset_demo_cases
    n = reset_demo_cases(db, user)
    return {"ok": True, "cases": n}


# ------------------------------------------------------------------ demo
@router.post("/demo/launch")
def demo_launch(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.is_demo.is_(True), Case.category == "Academic Records").order_by(Case.id).first()
    if not case:
        raise HTTPException(404, "The demo case is not available. An administrator can restore it from Settings.")
    allowed = accessible_case_ids(db, user)
    if allowed is not None and case.id not in allowed:
        raise HTTPException(403, "The demo case has not been assigned to you.")
    if case.archived:
        case.archived = False
        db.commit()
    started = False
    if has(user, "analysis:run") and not (case.analysis_state or {}).get("running"):
        case.analysis_state = {"running": True, "stage": "queued", "stages": [], "started_at": iso(utcnow())}
        db.commit()
        threading.Thread(target=run_case_job, args=(case.id, user.id, 0.9), daemon=True).start()
        started = True
    audit(db, user, "Launched guided demo", category="analysis", target_type="case", target_id=case.id,
          target_label=case.code, case_id=case.id)
    return {"case_id": case.id, "started": started}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.query(func.count(User.id)).scalar()
    return {"status": "ok", "time": iso(utcnow())}
