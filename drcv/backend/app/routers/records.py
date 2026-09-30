import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, Case, Conflict, Entity, Event, Record, Relationship, ReviewAction, User, utcnow
from ..pipeline.analysis import RECORD_STAGES, recompute_statuses, run_case_analysis, submit_record
from ..pipeline.extract import ValidationError, validate_file
from ..security import accessible_case_ids, audit, get_case_or_404, require
from ..ser import (conflict_out, entity_out, event_flags, event_out, ilike_any, iso, record_brief, records_map,
                   relationship_out)
from ..settings_store import get_settings
from ..storage import storage

router = APIRouter(prefix="/api", tags=["Records"])


def get_record(db: Session, user: User, record_id: int) -> Record:
    r = db.get(Record, record_id)
    if not r:
        raise HTTPException(404, "Record not found.")
    get_case_or_404(db, user, r.case_id)
    return r


@router.get("/records")
def list_records(case_id: int | None = None, kind: str | None = None, ext: str | None = None,
                 status: str | None = None, q: str | None = None, has_conflict: bool | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                 user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    query = db.query(Record).join(Case, Case.id == Record.case_id).filter(Case.archived.is_(False))
    allowed = accessible_case_ids(db, user)
    if allowed is not None:
        query = query.filter(Record.case_id.in_(allowed or [-1]))
    if case_id:
        query = query.filter(Record.case_id == case_id)
    if kind in ("document", "image"):
        query = query.filter(Record.kind == kind)
    if ext:
        query = query.filter(Record.ext == "." + ext.lower().lstrip("."))
    if status:
        query = query.filter(Record.status == status)
    if q:
        query = query.filter(ilike_any([Record.filename, Record.doc_type, Record.sha256, Record.text], q.strip()))
    if has_conflict is not None:
        ids = {i for c in db.query(Conflict) for i in (c.record_a_id, c.record_b_id)}
        query = query.filter(Record.id.in_(ids or [-1])) if has_conflict else query.filter(~Record.id.in_(ids or [-1]))
    total = query.count()
    rows = query.order_by(Record.uploaded_at.desc(), Record.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [record_brief(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/cases/{case_id}/records", status_code=201)
async def upload_records(case_id: int, files: list[UploadFile] = File(...),
                         user: User = Depends(require("record:upload")), db: Session = Depends(get_db)):
    case = get_case_or_404(db, user, case_id)
    if case.archived:
        raise HTTPException(400, "Archived cases cannot receive new records.")
    if len(files) > 25:
        raise HTTPException(400, "You can upload up to 25 files at a time.")
    max_bytes = int(get_settings(db)["max_upload_mb"]) * 1024 * 1024
    results = []
    for f in files:
        data = await f.read(max_bytes + 1)
        name = (f.filename or "").replace("\\", "/").split("/")[-1][:255]
        try:
            ext, mime, kind = validate_file(name, data, max_bytes)
        except ValidationError as e:
            audit(db, user, "Upload rejected", category="upload", target_type="record", target_label=name,
                  case_id=case.id, result="failed", details=str(e))
            results.append({"filename": name, "ok": False, "error": str(e)})
            continue
        rec = Record(case_id=case.id, filename=name, ext=ext, mime=mime, kind=kind, size=len(data),
                     storage_key=storage.new_key(), status="Uploading", stage="uploading", uploaded_by=user.id,
                     stage_log=[{"stage": "uploading", "label": "Uploading", "at": iso(utcnow()), "ok": True,
                                 "detail": f"{len(data)} bytes received"}])
        db.add(rec)
        db.commit()
        audit(db, user, "Uploaded record", category="upload", target_type="record", target_id=rec.id,
              target_label=name, case_id=case.id, record_id=rec.id, details=f"{ext.upper()[1:]}, {len(data)} bytes")
        submit_record(rec.id, data, user.id)
        results.append({"filename": name, "ok": True, "record": record_brief(rec, case)})
    if case.status != "processing" and not case.status_locked and any(r["ok"] for r in results):
        case.status = "processing"
        case.updated_at = utcnow()
        db.commit()
    return {"results": results, "stages": [{"key": k, "label": l, "status": s} for k, l, s in RECORD_STAGES]}


@router.get("/records/{record_id}/status")
def record_status(record_id: int, user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    return record_brief(r)


@router.get("/records/{record_id}")
def record_detail(record_id: int, user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    case = db.get(Case, r.case_id)
    ents = db.query(Entity).filter(Entity.record_id == r.id).order_by(Entity.type, Entity.id).all()
    evs = db.query(Event).filter(Event.record_id == r.id).order_by(Event.date).all()
    case_events = db.query(Event).filter(Event.case_id == r.case_id).order_by(Event.date, Event.id).all()
    flags = event_flags(db, r.case_id, case_events)
    rels = db.query(Relationship).filter(or_(Relationship.source_record_id == r.id, Relationship.target_record_id == r.id)).all()
    confs = db.query(Conflict).filter(or_(Conflict.record_a_id == r.id, Conflict.record_b_id == r.id)).all()
    rmap = records_map(db, [x.source_record_id for x in rels] + [x.target_record_id for x in rels]
                       + [c.record_a_id for c in confs] + [c.record_b_id for c in confs] + [r.id])
    conf_ids = [c.id for c in confs]
    reviews = db.query(ReviewAction).filter(or_(ReviewAction.record_id == r.id,
                                                ReviewAction.conflict_id.in_(conf_ids or [-1]))).order_by(ReviewAction.created_at.desc()).all()
    audits = db.query(AuditLog).filter(AuditLog.record_id == r.id).order_by(AuditLog.ts.desc()).limit(100).all()
    positions = {e.id: i for i, e in enumerate(case_events)}
    return {
        "record": record_brief(r, case),
        "case": {"id": case.id, "code": case.code, "name": case.name},
        "metadata": r.meta or {"available": [], "not_available": [], "notes": []},
        "text": r.text, "text_method": r.text_method, "ocr_confidence": r.ocr_confidence,
        "fields": r.fields or {},
        "entities": [entity_out(e) for e in ents],
        "events": [dict(event_out(e, r, flags.get(e.id, "normal")), position=positions.get(e.id)) for e in evs],
        "timeline_size": len(case_events),
        "relationships": [relationship_out(x, rmap) for x in rels],
        "conflicts": [conflict_out(c, rmap) for c in confs],
        "reviews": [{"id": a.id, "user": a.user_name, "role": a.role, "action": a.action, "note": a.note,
                     "from": a.from_status, "to": a.to_status, "subject": a.subject, "at": iso(a.created_at)} for a in reviews],
        "audit": [{"id": a.id, "ts": iso(a.ts), "user": a.user_name, "role": a.role, "action": a.action,
                   "result": a.result, "details": a.details} for a in audits],
    }


@router.get("/records/{record_id}/metadata")
def record_metadata(record_id: int, user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    return r.meta or {}


@router.get("/records/{record_id}/text")
def record_text(record_id: int, user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    return {"text": r.text, "method": r.text_method, "confidence": r.ocr_confidence, "error": r.error}


@router.get("/records/{record_id}/entities")
def record_entities(record_id: int, user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    return [entity_out(e) for e in db.query(Entity).filter(Entity.record_id == r.id)]


@router.get("/records/{record_id}/hash")
def record_hash(record_id: int, user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    return {"algorithm": "SHA-256", "sha256": r.sha256, "size": r.size, "hashed_at": iso(r.hashed_at),
            "uploaded_at": iso(r.uploaded_at), "processed_at": iso(r.processed_at)}


@router.post("/records/{record_id}/verify")
def verify_integrity(record_id: int, user: User = Depends(require("record:view")), db: Session = Depends(get_db)):
    """Re-computes SHA-256 of the stored bytes and compares to the recorded fingerprint."""
    r = get_record(db, user, record_id)
    if not r.sha256 or not storage.exists(r.storage_key):
        raise HTTPException(409, "No stored content is available to verify for this record.")
    current = storage.sha256(r.storage_key)
    match = current == r.sha256
    audit(db, user, "Re-verified SHA-256 fingerprint", category="integrity", target_type="record", target_id=r.id,
          target_label=r.filename, case_id=r.case_id, record_id=r.id, result="success" if match else "failed",
          details="Stored content matches the recorded hash" if match else "Stored content differs from the recorded hash")
    return {"match": match, "recorded": r.sha256, "current": current, "checked_at": iso(utcnow())}


@router.post("/records/verify-file")
async def verify_external(file: UploadFile = File(...), user: User = Depends(require("record:view")),
                          db: Session = Depends(get_db)):
    """Hash a local copy and look for records with the same fingerprint (the file is not stored)."""
    h = hashlib.sha256()
    size = 0
    while chunk := await file.read(1024 * 1024):
        h.update(chunk)
        size += len(chunk)
        if size > 200 * 1024 * 1024:
            raise HTTPException(413, "File too large to verify.")
    digest = h.hexdigest()
    allowed = accessible_case_ids(db, user)
    q = db.query(Record).filter(Record.sha256 == digest)
    if allowed is not None:
        q = q.filter(Record.case_id.in_(allowed or [-1]))
    matches = [record_brief(r) for r in q]
    audit(db, user, "Compared a file against recorded fingerprints", category="integrity",
          details=f"{digest[:16]}… — {len(matches)} match(es)")
    return {"sha256": digest, "size": size, "matches": matches}


@router.get("/records/{record_id}/file")
def record_file(record_id: int, download: bool = False, user: User = Depends(require("record:view")),
                db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    if not storage.exists(r.storage_key):
        raise HTTPException(404, "The original file is not available.")
    data = storage.read(r.storage_key)
    safe = "".join(ch for ch in r.filename if ch.isalnum() or ch in "._- ") or "record"
    disp = "attachment" if download else "inline"
    if download:
        audit(db, user, "Downloaded original record", category="record", target_type="record", target_id=r.id,
              target_label=r.filename, case_id=r.case_id, record_id=r.id)
    return Response(data, media_type=r.mime, headers={
        "Content-Disposition": f'{disp}; filename="{safe}"', "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store", "Content-Security-Policy": "sandbox"})


@router.delete("/records/{record_id}")
def delete_record(record_id: int, user: User = Depends(require("record:delete")), db: Session = Depends(get_db)):
    r = get_record(db, user, record_id)
    case_id, key, name = r.case_id, r.storage_key, r.filename
    db.query(Conflict).filter(or_(Conflict.record_a_id == r.id, Conflict.record_b_id == r.id)).delete(synchronize_session=False)
    db.query(Relationship).filter(or_(Relationship.source_record_id == r.id, Relationship.target_record_id == r.id)).delete(synchronize_session=False)
    db.query(Entity).filter(Entity.record_id == r.id).delete()
    db.query(Event).filter(Event.record_id == r.id).delete()
    db.query(ReviewAction).filter(ReviewAction.record_id == r.id).update({"record_id": None})
    db.delete(r)
    db.commit()
    try:
        storage.delete(key)
    except Exception:
        pass
    audit(db, user, "Deleted record", category="record", target_type="record", target_id=record_id, target_label=name,
          case_id=case_id)
    run_case_analysis(case_id)
    recompute_statuses(db, case_id)
    return {"ok": True}
