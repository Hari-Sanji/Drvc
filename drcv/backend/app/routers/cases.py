import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Case, CaseAssignment, Conflict, Entity, Event, Record, Relationship, User, utcnow
from ..pipeline.analysis import CASE_STAGES, recompute_statuses, run_case_job
from ..security import accessible_case_ids, audit, get_case_or_404, has, require
from ..ser import case_counts, case_out, ilike_any, iso, record_brief
from ..storage import storage

router = APIRouter(prefix="/api/cases", tags=["Cases"])
VALID_STATUS = {"active", "processing", "requires_review", "completed"}


class CaseIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="General", max_length=80)


class CasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=80)
    status: str | None = None


class AssignIn(BaseModel):
    user_ids: list[int]


def next_code(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"CASE-{year}-"
    n = 0
    for (code,) in db.query(Case.code).filter(Case.code.like(prefix + "%")):
        try:
            n = max(n, int(code.rsplit("-", 1)[1]))
        except ValueError:
            pass
    return f"{prefix}{n + 1:04d}"


@router.get("")
def list_cases(status: str | None = None, q: str | None = None, include_archived: bool = False,
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               user: User = Depends(require("case:view")), db: Session = Depends(get_db)):
    query = db.query(Case)
    allowed = accessible_case_ids(db, user)
    if allowed is not None:
        query = query.filter(Case.id.in_(allowed or [-1]))
    if status == "archived":
        query = query.filter(Case.archived.is_(True))
    else:
        if not include_archived:
            query = query.filter(Case.archived.is_(False))
        if status in VALID_STATUS:
            query = query.filter(Case.status == status)
    if q:
        query = query.filter(ilike_any([Case.name, Case.code, Case.description, Case.category], q.strip()))
    total = query.count()
    rows = query.order_by(Case.updated_at.desc(), Case.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    counts = case_counts(db, [c.id for c in rows])
    return {"items": [case_out(db, c, counts[c.id]) for c in rows], "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
def create_case(body: CaseIn, user: User = Depends(require("case:create")), db: Session = Depends(get_db)):
    c = Case(code=next_code(db), name=body.name.strip(), description=body.description.strip(),
             category=body.category.strip() or "General", owner_id=user.id, status="active")
    db.add(c)
    db.commit()
    audit(db, user, "Created case", category="case", target_type="case", target_id=c.id, target_label=c.code,
          case_id=c.id, details=c.name)
    return case_out(db, c)


@router.get("/{case_id}")
def get_case(case_id: int, user: User = Depends(require("case:view")), db: Session = Depends(get_db)):
    return case_out(db, get_case_or_404(db, user, case_id))


@router.patch("/{case_id}")
def update_case(case_id: int, body: CasePatch, user: User = Depends(require("case:update")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    changes = []
    for f in ("name", "description", "category"):
        v = getattr(body, f)
        if v is not None and v.strip() != getattr(c, f):
            setattr(c, f, v.strip())
            changes.append(f)
    if body.status is not None:
        if body.status == "auto":
            c.status_locked = False
            changes.append("status → automatic")
        elif body.status in VALID_STATUS:
            c.status = body.status
            c.status_locked = True
            changes.append(f"status → {body.status}")
        else:
            raise HTTPException(422, "Invalid status.")
    c.updated_at = utcnow()
    db.commit()
    if body.status == "auto":
        recompute_statuses(db, c.id)
    audit(db, user, "Updated case", category="case", target_type="case", target_id=c.id, target_label=c.code,
          case_id=c.id, details=", ".join(changes) or "No changes")
    return case_out(db, c)


@router.post("/{case_id}/archive")
def archive_case(case_id: int, user: User = Depends(require("case:archive")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    c.archived = True
    c.updated_at = utcnow()
    db.commit()
    audit(db, user, "Archived case", category="case", target_type="case", target_id=c.id, target_label=c.code, case_id=c.id)
    return case_out(db, c)


@router.post("/{case_id}/unarchive")
def unarchive_case(case_id: int, user: User = Depends(require("case:archive")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    c.archived = False
    c.updated_at = utcnow()
    db.commit()
    audit(db, user, "Restored archived case", category="case", target_type="case", target_id=c.id, target_label=c.code, case_id=c.id)
    return case_out(db, c)


@router.delete("/{case_id}")
def delete_case(case_id: int, user: User = Depends(require("case:delete")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    keys = [r.storage_key for r in db.query(Record).filter(Record.case_id == c.id)]
    code, name = c.code, c.name
    for model in (Conflict, Relationship, Event, Entity):
        db.query(model).filter(model.case_id == c.id).delete()
    db.query(Record).filter(Record.case_id == c.id).delete()
    db.query(CaseAssignment).filter(CaseAssignment.case_id == c.id).delete()
    db.delete(c)
    db.commit()
    for k in keys:
        try:
            storage.delete(k)
        except Exception:
            pass
    audit(db, user, "Deleted case", category="case", target_type="case", target_id=case_id, target_label=code,
          details=f"{name}; {len(keys)} records removed from storage")
    return {"ok": True}


@router.put("/{case_id}/assignments")
def set_assignments(case_id: int, body: AssignIn, user: User = Depends(require("case:assign")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    valid = {u.id: u for u in db.query(User).filter(User.id.in_(body.user_ids or [-1]), User.role == "reviewer")}
    db.query(CaseAssignment).filter(CaseAssignment.case_id == c.id).delete()
    for uid in valid:
        db.add(CaseAssignment(case_id=c.id, user_id=uid))
    db.commit()
    audit(db, user, "Updated reviewer assignments", category="case", target_type="case", target_id=c.id,
          target_label=c.code, case_id=c.id, details=", ".join(u.name for u in valid.values()) or "None")
    return case_out(db, c)


@router.get("/{case_id}/overview")
def overview(case_id: int, user: User = Depends(require("case:view")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    recs = db.query(Record).filter(Record.case_id == c.id).order_by(Record.id).all()
    ent_counts = {}
    for e in db.query(Entity).filter(Entity.case_id == c.id):
        ent_counts[e.type] = ent_counts.get(e.type, 0) + 1
    rels = db.query(Relationship).filter(Relationship.case_id == c.id).all()
    related = {r.source_record_id for r in rels} | {r.target_record_id for r in rels}
    confl = db.query(Conflict).filter(Conflict.case_id == c.id).all()
    by_type = {}
    for x in confl:
        by_type[x.type] = by_type.get(x.type, 0) + 1
    events = db.query(Event).filter(Event.case_id == c.id).order_by(Event.date).all()
    return {
        "case": case_out(db, c),
        "records": [record_brief(r, c) for r in recs],
        "stats": {
            "records": len(recs), "hashed": sum(1 for r in recs if r.sha256), "related": len(related),
            "relationships": len(rels), "entities": sum(ent_counts.values()), "events": len(events),
            "conflicts": len(confl), "unresolved": sum(1 for x in confl if x.status in ("requires_review", "escalated")),
            "ocr_records": sum(1 for r in recs if r.text_method.startswith("OCR")),
        },
        "entity_counts": ent_counts, "conflict_types": by_type,
        "date_span": [events[0].date, events[-1].date] if events else None,
    }


@router.post("/{case_id}/analyze")
def analyze(case_id: int, user: User = Depends(require("analysis:run")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    if (c.analysis_state or {}).get("running"):
        return {"started": False, "message": "Analysis is already running.", "state": c.analysis_state}
    if db.query(Record).filter(Record.case_id == c.id, Record.sha256.isnot(None)).count() == 0:
        raise HTTPException(400, "No records uploaded. Add records to begin contextual analysis.")
    c.analysis_state = {"running": True, "stage": "queued", "stages": [], "started_at": iso(utcnow())}
    db.commit()
    audit(db, user, "Started case analysis", category="analysis", target_type="case", target_id=c.id,
          target_label=c.code, case_id=c.id)
    threading.Thread(target=run_case_job, args=(c.id, user.id), daemon=True).start()
    return {"started": True, "stages": [{"key": k, "label": l} for k, l in CASE_STAGES]}


@router.get("/{case_id}/analysis-status")
def analysis_status(case_id: int, user: User = Depends(require("case:view")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    return {"state": c.analysis_state or {}, "stages": [{"key": k, "label": l} for k, l in CASE_STAGES]}
