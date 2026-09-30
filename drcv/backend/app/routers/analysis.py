from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case as sa_case
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Case, Conflict, Entity, Event, Record, Relationship, ReviewAction, User, utcnow
from ..pipeline.analysis import recompute_statuses
from ..security import ROLE_LABELS, accessible_case_ids, audit, get_case_or_404, has, require
from ..ser import (CONFLICT_STATUS_LABELS, UNRESOLVED, merge_events, conflict_out, entity_out, event_flags, event_out, iso,
                   records_map, relationship_out)

router = APIRouter(prefix="/api", tags=["Analysis"])


@router.get("/cases/{case_id}/timeline")
def timeline(case_id: int, include_mentions: bool = True, user: User = Depends(require("analysis:view")),
             db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    q = db.query(Event).filter(Event.case_id == c.id)
    if not include_mentions:
        q = q.filter(Event.kind != "mention")
    evs = q.order_by(Event.date, Event.time, Event.id).all()
    rmap = records_map(db, [e.record_id for e in evs])
    flags = event_flags(db, c.id, evs)
    merged = merge_events(evs, rmap, flags)
    return {"events": merged, "raw_count": len(evs),
            "counts": {k: sum(1 for m in merged if m["flag"] == k) for k in ("normal", "review", "conflict", "resolved")}}


@router.get("/cases/{case_id}/entities")
def entities(case_id: int, type: str | None = None, user: User = Depends(require("analysis:view")),
             db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    q = db.query(Entity).filter(Entity.case_id == c.id)
    if type:
        q = q.filter(Entity.type == type.upper())
    groups: dict = {}
    for e in q:
        g = groups.setdefault((e.type, e.norm), {"type": e.type, "value": e.value, "norm": e.norm, "records": []})
        if e.record_id not in g["records"]:
            g["records"].append(e.record_id)
    return sorted(groups.values(), key=lambda g: (-len(g["records"]), g["type"], g["value"]))


@router.get("/cases/{case_id}/events")
def events(case_id: int, user: User = Depends(require("analysis:view")), db: Session = Depends(get_db)):
    return timeline(case_id, True, user, db)


@router.get("/cases/{case_id}/relationships")
def relationships(case_id: int, user: User = Depends(require("analysis:view")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    rels = db.query(Relationship).filter(Relationship.case_id == c.id).order_by(Relationship.score.desc()).all()
    rmap = records_map(db, [r.source_record_id for r in rels] + [r.target_record_id for r in rels])
    return [relationship_out(r, rmap) for r in rels]


@router.get("/cases/{case_id}/graph")
def graph(case_id: int, user: User = Depends(require("analysis:view")), db: Session = Depends(get_db)):
    c = get_case_or_404(db, user, case_id)
    recs = db.query(Record).filter(Record.case_id == c.id, Record.sha256.isnot(None)).order_by(Record.id).all()
    conflicts = db.query(Conflict).filter(Conflict.case_id == c.id, Conflict.status.in_(UNRESOLVED)).all()
    flagged = {x.record_a_id for x in conflicts} | {x.record_b_id for x in conflicts}
    nodes, edges = [], []
    nodes.append({"id": f"case-{c.id}", "type": "case", "label": c.code, "sub": c.name})
    for r in recs:
        nodes.append({"id": f"rec-{r.id}", "type": "image" if r.kind == "image" else "document", "label": r.doc_type,
                      "sub": r.filename, "record_id": r.id, "flag": "conflict" if r.id in flagged else r.status})
        edges.append({"id": f"c-{r.id}", "source": f"case-{c.id}", "target": f"rec-{r.id}", "type": "contains",
                      "label": "Contains"})
    type_map = {"PERSON": "person", "ORG": "organization", "LOCATION": "location", "ID": "identifier",
                "DOC_REF": "identifier"}
    ent_nodes: dict = {}
    rec_ids = {r.id for r in recs}
    for e in db.query(Entity).filter(Entity.case_id == c.id, Entity.type.in_(list(type_map))):
        if e.record_id not in rec_ids:
            continue
        if e.type in ("ID", "DOC_REF") and e.confidence < 0.9:
            continue
        key = f"ent-{e.type}-{e.norm}"
        if key not in ent_nodes:
            ent_nodes[key] = {"id": key, "type": type_map[e.type], "label": e.value, "sub": e.label or e.type.title(),
                              "records": set()}
        ent_nodes[key]["records"].add(e.record_id)
    for key, n in ent_nodes.items():
        rs = n.pop("records")
        n["shared"] = len(rs)
        nodes.append(n)
        for rid in rs:
            edges.append({"id": f"{key}-{rid}", "source": f"rec-{rid}", "target": key, "type": "mentions",
                          "label": "Mentions"})
    ev_nodes: dict = {}
    for e in db.query(Event).filter(Event.case_id == c.id, Event.kind != "mention").order_by(Event.date):
        if e.record_id not in rec_ids:
            continue
        key = f"ev-{e.date}-{e.kind}"
        if key not in ev_nodes:
            ev_nodes[key] = {"id": key, "type": "event", "label": e.label, "sub": e.date, "records": set()}
        ev_nodes[key]["records"].add(e.record_id)
    for key, n in ev_nodes.items():
        rs = n.pop("records")
        n["shared"] = len(rs)
        nodes.append(n)
        for rid in rs:
            edges.append({"id": f"{key}-{rid}", "source": f"rec-{rid}", "target": key, "type": "event",
                          "label": "Associated Event"})
    for rel in db.query(Relationship).filter(Relationship.case_id == c.id):
        edges.append({"id": f"rel-{rel.id}", "source": f"rec-{rel.source_record_id}", "target": f"rec-{rel.target_record_id}",
                      "type": "relationship", "label": f"{rel.label} · {rel.rel_type}", "score": rel.score,
                      "rel_type": rel.rel_type, "evidence": rel.evidence})
    return {"nodes": nodes, "edges": edges}


# ------------------------------------------------------------------ conflicts
@router.get("/conflicts")
def list_conflicts(case_id: int | None = None, status: str | None = None, type: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                   user: User = Depends(require("analysis:view")), db: Session = Depends(get_db)):
    q = db.query(Conflict).join(Case, Case.id == Conflict.case_id).filter(Case.archived.is_(False))
    allowed = accessible_case_ids(db, user)
    if allowed is not None:
        q = q.filter(Conflict.case_id.in_(allowed or [-1]))
    if case_id:
        q = q.filter(Conflict.case_id == case_id)
    if status == "unresolved":
        q = q.filter(Conflict.status.in_(UNRESOLVED))
    elif status:
        q = q.filter(Conflict.status == status)
    if type:
        q = q.filter(Conflict.type == type)
    total = q.count()
    rows = q.order_by(sa_case((Conflict.status.in_(UNRESOLVED), 0), else_=1), Conflict.case_id.desc(), Conflict.id).offset((page - 1) * page_size).limit(page_size).all()
    rmap = records_map(db, [c.record_a_id for c in rows] + [c.record_b_id for c in rows])
    cases = {c.id: c for c in db.query(Case).filter(Case.id.in_({r.case_id for r in rows} or {-1}))}
    items = []
    for c in rows:
        d = conflict_out(c, rmap)
        d["case"] = {"id": c.case_id, "code": cases[c.case_id].code, "name": cases[c.case_id].name}
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/conflicts/{conflict_id}")
def get_conflict(conflict_id: int, user: User = Depends(require("analysis:view")), db: Session = Depends(get_db)):
    c = db.get(Conflict, conflict_id)
    if not c:
        raise HTTPException(404, "Conflict not found.")
    case = get_case_or_404(db, user, c.case_id)
    d = conflict_out(c, records_map(db, [c.record_a_id, c.record_b_id]))
    d["case"] = {"id": case.id, "code": case.code, "name": case.name}
    d["history"] = [review_out(a) for a in db.query(ReviewAction).filter(ReviewAction.conflict_id == c.id)
                    .order_by(ReviewAction.created_at.desc())]
    return d


class ReviewIn(BaseModel):
    action: str
    note: str = Field(default="", max_length=2000)


ACTIONS = {
    "mark_reviewed": ("reviewed", "marked as reviewed"),
    "accept": ("accepted", "accepted the explanation for"),
    "resolve": ("resolved", "resolved"),
    "escalate": ("escalated", "escalated"),
    "reopen": ("requires_review", "reopened"),
    "note": (None, "added a note to"),
}


def review_out(a: ReviewAction):
    return {"id": a.id, "case_id": a.case_id, "conflict_id": a.conflict_id, "record_id": a.record_id,
            "user": a.user_name, "role": a.role, "action": a.action, "note": a.note, "from": a.from_status,
            "to": a.to_status, "from_label": CONFLICT_STATUS_LABELS.get(a.from_status or "", a.from_status),
            "to_label": CONFLICT_STATUS_LABELS.get(a.to_status or "", a.to_status), "subject": a.subject,
            "at": iso(a.created_at)}


@router.post("/conflicts/{conflict_id}/review")
def review_conflict(conflict_id: int, body: ReviewIn, user: User = Depends(require("review:note")),
                    db: Session = Depends(get_db)):
    c = db.get(Conflict, conflict_id)
    if not c:
        raise HTTPException(404, "Conflict not found.")
    case = get_case_or_404(db, user, c.case_id)
    if body.action not in ACTIONS:
        raise HTTPException(422, "Unknown review action.")
    if body.action != "note" and not has(user, "conflict:review"):
        audit(db, user, "Access denied: review decision", category="security", result="denied", target_type="conflict",
              target_id=c.id, target_label=c.type, case_id=c.case_id)
        raise HTTPException(403, f"Your role ({ROLE_LABELS[user.role]}) can add notes but cannot make review decisions.")
    note = body.note.strip()
    if body.action in ("resolve", "accept", "escalate", "note") and len(note) < 3:
        raise HTTPException(422, "Please provide a reason or note (at least 3 characters).")
    new_status, verb = ACTIONS[body.action]
    old = c.status
    if new_status:
        c.status = new_status
        c.updated_at = utcnow()
    a = ReviewAction(case_id=c.case_id, conflict_id=c.id, user_id=user.id, user_name=user.name,
                     role=ROLE_LABELS[user.role], action=body.action, note=note, from_status=old,
                     to_status=new_status or old, subject=f"{c.type} — {c.field}")
    db.add(a)
    db.commit()
    audit(db, user, f"{ROLE_LABELS[user.role]} {verb} {c.type}", category="review", target_type="conflict",
          target_id=c.id, target_label=c.field, case_id=c.case_id,
          details=(f"Reason: {note}" if note else "") + (f" (status {CONFLICT_STATUS_LABELS[old]} → {CONFLICT_STATUS_LABELS[new_status]})" if new_status and new_status != old else ""))
    recompute_statuses(db, c.case_id)
    return get_conflict(c.id, user, db)


class BulkReviewIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    action: str
    note: str = Field(default="", max_length=2000)


@router.post("/conflicts/bulk-review")
def bulk_review(body: BulkReviewIn, user: User = Depends(require("conflict:review")), db: Session = Depends(get_db)):
    """Applies one decision (with one shared reason) to several conflicts. Each item is audited individually."""
    if body.action not in ("mark_reviewed", "accept", "resolve", "escalate", "reopen"):
        raise HTTPException(422, "Unknown bulk action.")
    note = body.note.strip()
    if body.action in ("resolve", "accept", "escalate") and len(note) < 3:
        raise HTTPException(422, "Please provide a reason (at least 3 characters). It is recorded for every selected item.")
    allowed = accessible_case_ids(db, user)
    new_status, verb = ACTIONS[body.action]
    done, skipped, cases = [], [], set()
    for cid in dict.fromkeys(body.ids):
        c = db.get(Conflict, cid)
        if not c or (allowed is not None and c.case_id not in allowed):
            skipped.append({"id": cid, "reason": "Not found or not assigned to you"})
            continue
        old = c.status
        if old == new_status:
            skipped.append({"id": cid, "reason": f"Already {CONFLICT_STATUS_LABELS[old]}"})
            continue
        c.status, c.updated_at = new_status, utcnow()
        db.add(ReviewAction(case_id=c.case_id, conflict_id=c.id, user_id=user.id, user_name=user.name,
                            role=ROLE_LABELS[user.role], action=body.action, note=note, from_status=old,
                            to_status=new_status, subject=f"{c.type} — {c.field}"))
        db.commit()
        audit(db, user, f"{ROLE_LABELS[user.role]} {verb} {c.type} (bulk)", category="review", target_type="conflict",
              target_id=c.id, target_label=c.field, case_id=c.case_id,
              details=(f"Reason: {note} " if note else "") + f"(status {CONFLICT_STATUS_LABELS[old]} → {CONFLICT_STATUS_LABELS[new_status]})")
        done.append(c.id)
        cases.add(c.case_id)
    for case_id in cases:
        recompute_statuses(db, case_id)
    return {"updated": done, "skipped": skipped, "status": new_status,
            "status_label": CONFLICT_STATUS_LABELS[new_status]}


class NoteIn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)
    record_id: int | None = None


@router.post("/cases/{case_id}/notes", status_code=201)
def add_case_note(case_id: int, body: NoteIn, user: User = Depends(require("review:note")), db: Session = Depends(get_db)):
    case = get_case_or_404(db, user, case_id)
    subject = case.name
    if body.record_id:
        r = db.get(Record, body.record_id)
        if not r or r.case_id != case.id:
            raise HTTPException(404, "Record not found in this case.")
        subject = r.filename
    a = ReviewAction(case_id=case.id, record_id=body.record_id, user_id=user.id, user_name=user.name,
                     role=ROLE_LABELS[user.role], action="note", note=body.note.strip(), subject=subject)
    db.add(a)
    db.commit()
    audit(db, user, "Added review note", category="review", target_type="record" if body.record_id else "case",
          target_id=body.record_id or case.id, target_label=subject, case_id=case.id, record_id=body.record_id,
          details=body.note.strip()[:300])
    return review_out(a)


@router.get("/reviews")
def list_reviews(case_id: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                 user: User = Depends(require("analysis:view")), db: Session = Depends(get_db)):
    q = db.query(ReviewAction)
    allowed = accessible_case_ids(db, user)
    if allowed is not None:
        q = q.filter(ReviewAction.case_id.in_(allowed or [-1]))
    if case_id:
        q = q.filter(ReviewAction.case_id == case_id)
    total = q.count()
    rows = q.order_by(ReviewAction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    cases = {c.id: c for c in db.query(Case).filter(Case.id.in_({r.case_id for r in rows} or {-1}))}
    items = []
    for a in rows:
        d = review_out(a)
        cs = cases.get(a.case_id)
        d["case"] = {"id": cs.id, "code": cs.code, "name": cs.name} if cs else None
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
