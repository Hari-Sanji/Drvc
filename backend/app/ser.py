"""Serializers shared across routers (never expose storage keys or filesystem paths)."""
from datetime import timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .models import Case, CaseAssignment, Conflict, Entity, Event, Record, Relationship, User
from .pipeline import nlp
from .security import ROLE_LABELS

UNRESOLVED = ("requires_review", "escalated")
CONFLICT_STATUS_LABELS = {"requires_review": "Requires Review", "reviewed": "Reviewed", "accepted": "Accepted",
                          "resolved": "Resolved", "escalated": "Escalated"}
CASE_STATUS_LABELS = {"active": "Active", "processing": "Processing", "requires_review": "Requires Review",
                      "completed": "Completed", "archived": "Archived"}


def iso(dt):
    """Always emit timezone-aware UTC ISO strings (SQLite returns naive datetimes)."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def user_out(u: User | None):
    if not u:
        return None
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "role_label": ROLE_LABELS.get(u.role, u.role),
            "is_active": u.is_active, "is_demo": u.is_demo, "created_at": iso(u.created_at),
            "totp_enabled": bool(u.totp_enabled),
            "last_login": iso(u.last_login)}


def case_counts(db: Session, case_ids: list[int]) -> dict:
    out = {cid: {"records": 0, "conflicts": 0, "unresolved": 0} for cid in case_ids}
    if not case_ids:
        return out
    for cid, n in db.query(Record.case_id, func.count(Record.id)).filter(Record.case_id.in_(case_ids)).group_by(Record.case_id):
        out[cid]["records"] = n
    for cid, st, n in db.query(Conflict.case_id, Conflict.status, func.count(Conflict.id)).filter(
            Conflict.case_id.in_(case_ids)).group_by(Conflict.case_id, Conflict.status):
        out[cid]["conflicts"] += n
        if st in UNRESOLVED:
            out[cid]["unresolved"] += n
    return out


def case_out(db: Session, c: Case, counts: dict | None = None):
    counts = counts or case_counts(db, [c.id])[c.id]
    assignees = [user_out(u) for u in db.query(User).join(CaseAssignment, CaseAssignment.user_id == User.id)
                 .filter(CaseAssignment.case_id == c.id)]
    status = "archived" if c.archived else c.status
    if counts["conflicts"] == 0:
        review = "No review items"
    elif counts["unresolved"]:
        review = f"{counts['unresolved']} pending review"
    else:
        review = "All items reviewed"
    return {
        "id": c.id, "code": c.code, "name": c.name, "description": c.description, "category": c.category,
        "status": status, "status_label": CASE_STATUS_LABELS.get(status, status), "status_locked": c.status_locked,
        "archived": c.archived, "is_demo": c.is_demo, "created_at": iso(c.created_at), "updated_at": iso(c.updated_at),
        "owner": user_out(c.owner), "record_count": counts["records"], "conflict_count": counts["conflicts"],
        "unresolved_count": counts["unresolved"], "review_status": review, "assignees": assignees,
        "analysis_state": c.analysis_state or {},
    }


def record_brief(r: Record, case: Case | None = None):
    return {
        "id": r.id, "case_id": r.case_id, "case_code": case.code if case else (r.case.code if r.case else None),
        "case_name": case.name if case else (r.case.name if r.case else None),
        "filename": r.filename, "ext": r.ext.lstrip(".").upper(), "mime": r.mime, "kind": r.kind, "size": r.size,
        "sha256": r.sha256, "status": r.status, "stage": r.stage, "doc_type": r.doc_type,
        "uploaded_at": iso(r.uploaded_at), "hashed_at": iso(r.hashed_at), "processed_at": iso(r.processed_at),
        "uploaded_by": r.uploader.name if r.uploader else None, "text_method": r.text_method,
        "ocr_confidence": r.ocr_confidence, "error": r.error, "is_demo": r.is_demo,
        "stage_log": r.stage_log or [],
    }


def conflict_out(c: Conflict, recs: dict):
    ra, rb = recs.get(c.record_a_id), recs.get(c.record_b_id)
    return {
        "id": c.id, "case_id": c.case_id, "type": c.type, "field": c.field, "severity": c.severity,
        "status": c.status, "status_label": CONFLICT_STATUS_LABELS.get(c.status, c.status),
        "explanation": c.explanation, "evidence": c.evidence, "detected_at": iso(c.detected_at), "updated_at": iso(c.updated_at),
        "record_a": {"id": c.record_a_id, "filename": ra.filename if ra else "Removed record",
                     "doc_type": ra.doc_type if ra else "", "value": c.value_a},
        "record_b": {"id": c.record_b_id, "filename": rb.filename if rb else "Removed record",
                     "doc_type": rb.doc_type if rb else "", "value": c.value_b},
    }


def records_map(db: Session, ids) -> dict:
    ids = list({i for i in ids if i})
    if not ids:
        return {}
    return {r.id: r for r in db.query(Record).filter(Record.id.in_(ids))}


def entity_out(e: Entity):
    return {"id": e.id, "record_id": e.record_id, "type": e.type, "value": e.value, "norm": e.norm, "label": e.label,
            "start": e.start, "end": e.end, "confidence": e.confidence}


def event_out(e: Event, rec: Record | None = None, flag: str = "normal"):
    return {"id": e.id, "record_id": e.record_id, "date": e.date, "date_label": nlp.fmt_date(e.date), "time": e.time,
            "label": e.label, "kind": e.kind, "snippet": e.snippet, "confidence": e.confidence,
            "source": {"id": rec.id, "filename": rec.filename, "doc_type": rec.doc_type} if rec else None,
            "flag": flag}


def relationship_out(r: Relationship, recs: dict):
    a, b = recs.get(r.source_record_id), recs.get(r.target_record_id)
    return {"id": r.id, "source": {"id": r.source_record_id, "filename": a.filename if a else "?", "doc_type": a.doc_type if a else ""},
            "target": {"id": r.target_record_id, "filename": b.filename if b else "?", "doc_type": b.doc_type if b else ""},
            "type": r.rel_type, "score": r.score, "label": r.label, "evidence": r.evidence}


def event_flags(db: Session, case_id: int, events: list[Event]) -> dict:
    """normal | review | conflict for each event."""
    conflicts = db.query(Conflict).filter(Conflict.case_id == case_id, Conflict.type == "Date Mismatch").all()
    flags = {}
    for e in events:
        f = "review" if e.confidence < 0.6 else "normal"
        label = nlp.fmt_date(e.date)
        for c in conflicts:
            if (e.record_id == c.record_a_id and label in c.value_a) or (e.record_id == c.record_b_id and label in c.value_b):
                f = "conflict" if c.status in UNRESOLVED else ("resolved" if f == "normal" else f)
                if c.status in UNRESOLVED:
                    break
        flags[e.id] = f
    return flags


def ilike_any(cols, q):
    like = f"%{q}%"
    return or_(*[c.ilike(like) for c in cols])


FLAG_RANK = {"conflict": 3, "review": 2, "resolved": 1, "normal": 0}


def merge_events(events: list, rmap: dict, flags: dict) -> list:
    """One timeline entry per (date, event label); every record that states it is listed as a source."""
    merged: dict = {}
    for e in events:
        key = (e.date, e.label)
        rec = rmap.get(e.record_id)
        src = {"id": e.record_id, "filename": rec.filename if rec else "?", "doc_type": rec.doc_type if rec else "",
               "snippet": e.snippet, "flag": flags.get(e.id, "normal")}
        if key not in merged:
            d = event_out(e, rec, flags.get(e.id, "normal"))
            d["sources"] = [src]
            merged[key] = d
        else:
            d = merged[key]
            if all(s["id"] != src["id"] for s in d["sources"]):
                d["sources"].append(src)
            d["confidence"] = max(d["confidence"], e.confidence)
            if FLAG_RANK.get(src["flag"], 0) > FLAG_RANK.get(d["flag"], 0):
                d["flag"] = src["flag"]
            if not d["time"] and e.time:
                d["time"] = e.time
    out = list(merged.values())
    for d in out:
        d["count"] = len(d["sources"])
    return out
