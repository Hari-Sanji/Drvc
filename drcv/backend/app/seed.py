"""Seeds demo users and SYNTHETIC demo cases.

Demo records are real files (backend/demo_files) processed through the real pipeline: they get genuine
SHA-256 fingerprints, metadata, OCR, entities, relationships and conflicts. Only their upload timeline is
spread over the previous days so the dashboard activity chart has history; it is labelled synthetic.
"""
import logging
from datetime import timedelta

from .config import DEMO_FILES_DIR
from .models import (AuditLog, Case, CaseAssignment, Conflict, Entity, Event, Record, Relationship, Report,
                     ReviewAction, User, utcnow)
from .pipeline.analysis import process_record, recompute_statuses
from .pipeline.extract import validate_file
from .security import ROLE_LABELS, audit, hash_password, rechain_from
from .storage import storage

log = logging.getLogger("drcv.seed")

DEMO_USERS = [
    ("admin@demo.local", "Aditi Rao", "admin", "Admin@123"),
    ("investigator@demo.local", "Vikram Nair", "investigator", "Investigator@123"),
    ("reviewer@demo.local", "Priya Menon", "reviewer", "Reviewer@123"),
    ("viewer@demo.local", "Karthik Iyer", "viewer", "Viewer@123"),
]

DEMO_CASES = [
    {
        "code": "CASE-2026-0001", "name": "Academic Record Verification", "category": "Academic Records",
        "description": "Synthetic Demo Data — verification of a fictional graduate's academic records (marksheets, "
                       "degree certificate, student ID and transcript) from the fictional Western Ghats University. "
                       "Contains intentional name, identifier and date inconsistencies.",
        "owner": "investigator@demo.local", "uploader": "investigator@demo.local", "assign": True, "days_ago": 9,
        "files": ["01_Semester_Marksheet_Sem8.pdf", "02_Consolidated_Marksheet.pdf", "03_Degree_Certificate.docx",
                  "04_Student_ID_Card.png", "05_Academic_Transcript.txt"],
    },
    {
        "code": "CASE-2026-0002", "name": "Invoice Verification", "category": "Financial Records",
        "description": "Synthetic Demo Data — reconciliation of a fictional supplier invoice with its purchase order, "
                       "scanned receipt and bank payment record. Contains intentional amount, date and delivery "
                       "location inconsistencies.",
        "owner": "investigator@demo.local", "uploader": "investigator@demo.local", "assign": True, "days_ago": 6,
        "files": ["11_Invoice_INV-2026-1142.pdf", "12_Purchase_Order_PO-2026-0781.docx",
                  "13_Receipt_RCP-5531_scanned.pdf", "14_Payment_Record_TXN88213490.jpg"],
        "reviews": [("Location Mismatch", "accept", "reviewer@demo.local",
                     "Buyer confirmed by email that delivery was redirected to its Erode warehouse after the PO was raised.")],
    },
    {
        "code": "CASE-2026-0003", "name": "Lease Agreement Verification", "category": "Property Records",
        "description": "Synthetic Demo Data — a fictional residential lease with two rent receipts. All extracted "
                       "values are consistent; the case has been marked completed.",
        "owner": "admin@demo.local", "uploader": "admin@demo.local", "assign": False, "days_ago": 12,
        "files": ["21_Lease_Agreement.txt", "22_Rent_Receipt_June.txt", "23_Rent_Receipt_July.txt"],
        "status": "completed",
    },
]


def seed_if_empty(db):
    if db.query(User).count() == 0:
        for email, name, role, pw in DEMO_USERS:
            db.add(User(email=email, name=name, role=role, password_hash=hash_password(pw), is_demo=True))
        db.commit()
        audit(db, None, "Created demo accounts", category="users", details=", ".join(ROLE_LABELS[r] for _, _, r, _ in DEMO_USERS))
        log.info("Demo accounts created")
    if db.query(Case).count() == 0:
        log.info("Preparing synthetic demo cases (runs the full pipeline once, ~20s)...")
        seed_demo_cases(db)
        log.info("Synthetic demo cases ready")


def seed_demo_cases(db):
    from sqlalchemy import func
    first_audit_id = (db.query(func.max(AuditLog.id)).scalar() or 0) + 1
    try:
        _seed_demo_cases(db)
    finally:
        # synthetic history back-dates the entries created above, so their chain links are recomputed once
        rechain_from(first_audit_id)


def _seed_demo_cases(db):
    users = {u.email: u for u in db.query(User)}
    reviewer = users.get("reviewer@demo.local")
    for spec in DEMO_CASES:
        if db.query(Case).filter(Case.code == spec["code"]).first():
            continue
        owner = users.get(spec["owner"]) or db.query(User).filter(User.role == "admin").first()
        uploader = users.get(spec["uploader"]) or owner
        base = utcnow() - timedelta(days=spec["days_ago"], hours=3)
        case = Case(code=spec["code"], name=spec["name"], description=spec["description"], category=spec["category"],
                    owner_id=owner.id if owner else None, is_demo=True, status="active", created_at=base, updated_at=base)
        db.add(case)
        db.commit()
        audit(db, owner, "Created case", category="case", target_type="case", target_id=case.id, target_label=case.code,
              case_id=case.id, details=case.name + " (synthetic demo data)", ts=base)
        if spec["assign"] and reviewer:
            db.add(CaseAssignment(case_id=case.id, user_id=reviewer.id))
            db.commit()
        for i, fname in enumerate(spec["files"]):
            path = DEMO_FILES_DIR / fname
            if not path.exists():
                log.warning("demo file missing: %s", fname)
                continue
            data = path.read_bytes()
            ext, mime, kind = validate_file(fname, data, 50 * 1024 * 1024)
            ts = base + timedelta(days=min(i, spec["days_ago"] - 1), minutes=17 * i + 5)
            rec = Record(case_id=case.id, filename=fname, ext=ext, mime=mime, kind=kind, size=len(data),
                         storage_key=storage.new_key(), status="Uploading", stage="uploading",
                         uploaded_by=uploader.id if uploader else None, is_demo=True, uploaded_at=ts,
                         stage_log=[{"stage": "uploading", "label": "Uploading", "at": ts.isoformat(), "ok": True,
                                     "detail": f"{len(data)} bytes received (synthetic demo upload)"}])
            db.add(rec)
            db.commit()
            audit(db, uploader, "Uploaded record", category="upload", target_type="record", target_id=rec.id,
                  target_label=fname, case_id=case.id, record_id=rec.id, details=f"{ext[1:].upper()}, {len(data)} bytes", ts=ts)
            start = utcnow()
            process_record(rec.id, data, uploader.id if uploader else None, 0.0)
            # shift this record's processing timestamps onto the synthetic upload day
            db.expire_all()
            rec = db.get(Record, rec.id)
            shift = start - ts - timedelta(seconds=40)
            rec.hashed_at = rec.hashed_at - shift if rec.hashed_at else None
            rec.processed_at = rec.processed_at - shift if rec.processed_at else None
            rec.stage_log = [dict(s, at=ts.isoformat()) for s in (rec.stage_log or [])]
            for a in db.query(AuditLog).filter(AuditLog.ts >= start):
                a.ts = a.ts - shift
            for c in db.query(Conflict).filter(Conflict.case_id == case.id, Conflict.detected_at >= start):
                c.detected_at = c.detected_at - shift
                c.updated_at = c.detected_at
            db.commit()
        for ctype, action, email, note in spec.get("reviews", []):
            c = db.query(Conflict).filter(Conflict.case_id == case.id, Conflict.type == ctype).first()
            u = users.get(email)
            if c and u:
                status = {"accept": "accepted", "resolve": "resolved", "escalate": "escalated"}[action]
                when = base + timedelta(days=spec["days_ago"] - 2, hours=2)
                db.add(ReviewAction(case_id=case.id, conflict_id=c.id, user_id=u.id, user_name=u.name,
                                    role=ROLE_LABELS[u.role], action=action, note=note, from_status=c.status,
                                    to_status=status, subject=f"{c.type} — {c.field}", created_at=when))
                c.status = status
                db.commit()
                audit(db, u, f"{ROLE_LABELS[u.role]} {'accepted the explanation for' if action == 'accept' else action + 'd'} {c.type}",
                      category="review", target_type="conflict", target_id=c.id, target_label=c.field, case_id=case.id,
                      details=f"Reason: {note}", ts=when)
        if spec.get("status"):
            case.status = spec["status"]
            case.status_locked = True
            db.commit()
        recompute_statuses(db, case.id)
        case.updated_at = base + timedelta(days=spec["days_ago"] - 1)
        db.commit()


def reset_demo_cases(db, actor=None) -> int:
    demo = db.query(Case).filter(Case.is_demo.is_(True)).all()
    for c in demo:
        keys = [r.storage_key for r in db.query(Record).filter(Record.case_id == c.id)]
        for model in (ReviewAction, Report, Conflict, Relationship, Event, Entity):
            db.query(model).filter(model.case_id == c.id).delete()
        db.query(Record).filter(Record.case_id == c.id).delete()
        db.query(CaseAssignment).filter(CaseAssignment.case_id == c.id).delete()
        # audit entries are never deleted (the log is append-only and hash-chained)
        db.delete(c)
        db.commit()
        for k in keys:
            try:
                storage.delete(k)
            except Exception:
                pass
    # shared demo accounts get their published passwords back and 2FA removed
    for email, _name, _role, pw in DEMO_USERS:
        u = db.query(User).filter(User.email == email).first()
        if u:
            u.password_hash = hash_password(pw)
            u.totp_enabled, u.totp_secret, u.is_active = False, None, True
            u.token_version = (u.token_version or 0) + 1
    db.commit()
    seed_demo_cases(db)
    audit(db, actor, "Reset synthetic demo data", category="settings",
          details=f"{len(DEMO_CASES)} demo cases restored; demo account passwords and 2FA reset")
    return len(DEMO_CASES)
