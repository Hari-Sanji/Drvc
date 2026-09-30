"""Record processing pipeline and case-level analysis.

UPLOAD → VALIDATE → SECURE STORAGE → SHA-256 → METADATA → OCR/TEXT → ENTITIES → EVENTS →
SIMILARITY → RELATIONSHIPS → TIMELINE → CONFLICTS → REVIEW STATUS
"""
import hashlib
import logging
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from ..db import SessionLocal
from ..models import Case, Conflict, Entity, Event, Record, Relationship, utcnow
from ..security import audit
from ..settings_store import get_settings
from ..storage import storage
from . import nlp
from .extract import extract_metadata, extract_text, metadata_flags

log = logging.getLogger("drcv.analysis")
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="drcv-pipeline")
_case_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)

RECORD_STAGES = [
    ("uploading", "Uploading", "Uploading"),
    ("validating", "Validating file", "Securing"),
    ("securing", "Securing file", "Securing"),
    ("hashing", "Generating SHA-256", "Hashing"),
    ("metadata", "Extracting metadata", "Extracting"),
    ("ocr", "Running OCR / text extraction", "Extracting"),
    ("entities", "Extracting entities", "Analyzing"),
    ("events", "Detecting events", "Analyzing"),
    ("relationships", "Finding relationships", "Analyzing"),
    ("conflicts", "Checking conflicts", "Analyzing"),
    ("complete", "Complete", "Completed"),
]
STATUS_BY_STAGE = {k: s for k, _, s in RECORD_STAGES}
LABEL_BY_STAGE = {k: l for k, l, _ in RECORD_STAGES}

CASE_STAGES = [
    ("securing", "Securing records"),
    ("hashing", "Generating hash"),
    ("extracting", "Extracting information"),
    ("connecting", "Connecting records"),
    ("timeline", "Building timeline"),
    ("consistency", "Checking consistency"),
    ("complete", "Analysis complete"),
]

CONSISTENCY_FIELDS = {
    "subject_name": ("Identity Mismatch", "high"),
    "id_number": ("Identifier Mismatch", "high"),
    "dob": ("Date Mismatch", "medium"),
    "degree_conferred": ("Date Mismatch", "medium"),
    "transaction_amount": ("Amount Mismatch", "high"),
    "invoice_no": ("Identifier Mismatch", "high"),
    "po_no": ("Identifier Mismatch", "medium"),
    "vendor": ("Identity Mismatch", "medium"),
    "buyer": ("Identity Mismatch", "medium"),
    "delivery_location": ("Location Mismatch", "medium"),
    "tenant": ("Identity Mismatch", "high"),
    "landlord": ("Identity Mismatch", "high"),
    "monthly_rent": ("Amount Mismatch", "medium"),
    "property_address": ("Location Mismatch", "medium"),
}
CHRONOLOGY_RULES = [
    ("order_date", "invoice_date", "The invoice is dated before the purchase order it references."),
    ("invoice_date", "receipt_date", "The receipt is dated before the invoice it acknowledges."),
    ("payment_date", "receipt_date", "The receipt is dated before the payment it records."),
    ("dob", "issue_date", "A document issue date precedes the recorded date of birth."),
]
RECOMMEND = {
    "Identity Mismatch": "Compare against the original issuing register or a primary identity record.",
    "Identifier Mismatch": "Confirm the identifier with the issuing authority's records.",
    "Date Mismatch": "Check which record is authoritative for this date and whether a later correction exists.",
    "Amount Mismatch": "Reconcile against the ledger / bank statement and check for partial payments or adjustments.",
    "Location Mismatch": "Confirm the correct location with the counterparty or shipping documents.",
    "Metadata Anomaly": "Request the original file from the issuer and compare it with this copy.",
    "Integrity Signal": "Obtain a fresh copy from the signer and compare fingerprints; do not rely on this copy alone.",
}


def _now():
    return datetime.now(timezone.utc)


# ================================================================== record pipeline
def _set_stage(db, rec: Record, stage: str, detail: str = "", ok: bool = True, started: float | None = None):
    rec.stage = stage
    rec.status = STATUS_BY_STAGE.get(stage, rec.status)
    log_ = list(rec.stage_log or [])
    ms = int((time.time() - started) * 1000) if started else None
    log_.append({"stage": stage, "label": LABEL_BY_STAGE.get(stage, stage), "at": _now().isoformat(),
                 "ms": ms, "ok": ok, "detail": detail})
    rec.stage_log = log_
    db.commit()


def _pace(t0, pace):
    if pace:
        rest = pace - (time.time() - t0)
        if rest > 0:
            time.sleep(rest)


def extract_record(db, rec: Record, data: bytes, settings: dict, pace: float = 0.0, log_audit: bool = True):
    """Metadata → text/OCR → entities → events for one record (idempotent)."""
    t0 = time.time()
    _set_stage(db, rec, "metadata")
    rec.meta = extract_metadata(rec.ext, data)
    db.commit()
    if log_audit:
        n = len(rec.meta.get("available", []))
        audit(db, None, "System extracted metadata", category="pipeline", target_type="record", target_id=rec.id,
              target_label=rec.filename, case_id=rec.case_id, record_id=rec.id,
              details=f"{n} properties available; {len(rec.meta.get('not_available', []))} not available")
    _pace(t0, pace)

    t0 = time.time()
    _set_stage(db, rec, "ocr")
    tx = extract_text(rec.ext, data, settings.get("ocr_enabled", True))
    rec.text = tx["text"]
    rec.text_method = tx["method"] if not tx["error"] else "failed"
    rec.ocr_confidence = tx["confidence"]
    rec.error = tx["error"]
    db.commit()
    if log_audit:
        if tx["error"]:
            audit(db, None, "Text extraction could not be completed", category="pipeline", target_type="record",
                  target_id=rec.id, target_label=rec.filename, case_id=rec.case_id, record_id=rec.id,
                  result="failed", details=tx["error"])
        else:
            is_ocr = tx["method"].startswith("OCR")
            conf = f" (confidence {tx['confidence']:.0f}%)" if tx["confidence"] is not None else ""
            audit(db, None, "System completed OCR" if is_ocr else "System extracted text", category="pipeline",
                  target_type="record", target_id=rec.id, target_label=rec.filename, case_id=rec.case_id,
                  record_id=rec.id, details=f"{tx['method']}: {len(rec.text)} characters{conf}")
    _pace(t0, pace)

    t0 = time.time()
    _set_stage(db, rec, "entities")
    rec.doc_type = nlp.guess_doc_type(rec.filename, rec.text, rec.kind)
    fields = nlp.extract_fields(rec.text)
    rec.fields = fields
    meta = dict(rec.meta or {})
    meta["flags"] = metadata_flags(meta, fields, rec.uploaded_at)
    rec.meta = meta
    db.query(Entity).filter(Entity.record_id == rec.id).delete()
    ents = nlp.extract_entities(rec.text, fields)
    for e in ents:
        db.add(Entity(case_id=rec.case_id, record_id=rec.id, type=e["type"], value=e["value"][:300],
                      norm=e["norm"][:300], label=e["label"], start=e["start"], end=e["end"],
                      confidence=e["confidence"]))
    db.commit()
    if log_audit:
        counts = Counter(e["type"] for e in ents)
        audit(db, None, f"System extracted {len(ents)} entities", category="pipeline", target_type="record",
              target_id=rec.id, target_label=rec.filename, case_id=rec.case_id, record_id=rec.id,
              details=", ".join(f"{k}: {v}" for k, v in counts.most_common()) or "No entities found")
    _pace(t0, pace)

    t0 = time.time()
    _set_stage(db, rec, "events")
    db.query(Event).filter(Event.record_id == rec.id).delete()
    evs = nlp.extract_events(rec.text, rec.doc_type)
    for ev in evs:
        db.add(Event(case_id=rec.case_id, record_id=rec.id, date=ev["date"], time=ev["time"], label=ev["label"],
                     kind=ev["kind"], snippet=ev["snippet"], confidence=ev["confidence"]))
    db.commit()
    if log_audit:
        audit(db, None, f"System detected {len(evs)} events", category="pipeline", target_type="record",
              target_id=rec.id, target_label=rec.filename, case_id=rec.case_id, record_id=rec.id)
    _pace(t0, pace)


def process_record(record_id: int, data: bytes, actor_id: int | None = None, pace: float = 0.0,
                   uploaded_ts=None):
    """Runs the complete pipeline for a freshly uploaded record. Runs in a worker thread."""
    db = SessionLocal()
    try:
        rec = db.get(Record, record_id)
        if not rec:
            return
        settings = get_settings(db)
        t0 = time.time()
        _set_stage(db, rec, "validating", "Extension, size and file signature verified")
        audit(db, None, "System validated file", category="pipeline", target_type="record", target_id=rec.id,
              target_label=rec.filename, case_id=rec.case_id, record_id=rec.id,
              details=f"{rec.mime}, {rec.size} bytes; signature matches extension", ts=uploaded_ts)
        _pace(t0, pace)

        t0 = time.time()
        _set_stage(db, rec, "securing", "Stored under an opaque key in secure storage")
        storage.save(rec.storage_key, data)
        audit(db, None, "System secured record in storage", category="pipeline", target_type="record",
              target_id=rec.id, target_label=rec.filename, case_id=rec.case_id, record_id=rec.id, ts=uploaded_ts)
        _pace(t0, pace)

        t0 = time.time()
        _set_stage(db, rec, "hashing")
        rec.sha256 = hashlib.sha256(data).hexdigest()
        rec.hashed_at = _now()
        db.commit()
        dup = db.query(Record).filter(Record.case_id == rec.case_id, Record.sha256 == rec.sha256,
                                      Record.id != rec.id).first()
        audit(db, None, "System generated SHA-256", category="pipeline", target_type="record", target_id=rec.id,
              target_label=rec.filename, case_id=rec.case_id, record_id=rec.id,
              details=rec.sha256 + (f" — identical content to record #{dup.id} ({dup.filename})" if dup else ""))
        _pace(t0, pace)

        extract_record(db, rec, data, settings, pace)

        t0 = time.time()
        _set_stage(db, rec, "relationships")
        _pace(t0, pace)
        _set_stage(db, rec, "conflicts")
        run_case_analysis(rec.case_id)
        db.refresh(rec)
        rec.processed_at = _now()
        db.commit()
        recompute_statuses(db, rec.case_id)
    except Exception as e:  # never leave a record stuck in a processing state
        log.exception("pipeline failed for record %s", record_id)
        db.rollback()
        rec = db.get(Record, record_id)
        if rec:
            rec.status = "Failed"
            rec.stage = "failed"
            rec.error = "Unable to process this file. Please verify the file type and try again."
            db.commit()
            audit(db, None, "Record processing failed", category="pipeline", target_type="record",
                  target_id=rec.id, target_label=rec.filename, case_id=rec.case_id, record_id=rec.id,
                  result="failed", details=type(e).__name__)
    finally:
        db.close()


def submit_record(record_id: int, data: bytes, actor_id=None):
    executor.submit(process_record, record_id, data, actor_id, 0.35)


# ================================================================== case analysis
def _label_for(score: float) -> str:
    if score >= 0.75:
        return "Likely Related"
    if score >= 0.45:
        return "Possible Match"
    return "Relationship Signal"


def _field_values(rec: Record) -> dict:
    f = dict(rec.fields or {})
    amt = f.get("grand_total") or f.get("amount_paid")
    if amt:
        f["transaction_amount"] = amt
    return f


def run_case_analysis(case_id: int, db=None) -> dict:
    """Similarity, relationships and conflict detection across all analysed records in a case."""
    own = db is None
    db = db or SessionLocal()
    lock = _case_locks[case_id]
    try:
        with lock:
            settings = get_settings(db)
            recs = db.query(Record).filter(Record.case_id == case_id, Record.sha256.isnot(None),
                                           Record.stage.in_(["relationships", "conflicts", "complete"])).order_by(Record.id).all()
            ents_by = defaultdict(list)
            for e in db.query(Entity).filter(Entity.case_id == case_id):
                ents_by[e.record_id].append(e)
            rel_count = _relationships(db, case_id, recs, ents_by, settings)
            pending: list = []
            new_conf, total_conf = _conflicts(db, case_id, recs, settings, ents_by, pending)
            db.commit()
            for entry in pending:  # audit entries are chained, so they are written after the data commit
                audit(db, None, **entry)
            return {"relationships": rel_count, "new_conflicts": new_conf, "conflicts": total_conf}
    finally:
        if own:
            db.close()


def _relationships(db, case_id, recs, ents_by, settings) -> int:
    db.query(Relationship).filter(Relationship.case_id == case_id).delete()
    if len(recs) < 2:
        return 0
    sim = nlp.tfidf_cosine_matrix([r.text for r in recs])
    thr = float(settings.get("similarity_threshold", 0.15))
    min_score = float(settings.get("relationship_min_score", 0.2))
    count = 0
    for i, a in enumerate(recs):
        for j in range(i + 1, len(recs)):
            b = recs[j]
            ev, weights = [], []
            ea, eb = ents_by[a.id], ents_by[b.id]
            for typ, w, rtype in (("ID", 0.45, "Shared Identifier"), ("DOC_REF", 0.5, "Shared Identifier"),
                                  ("PERSON", 0.35, "Shared Person"), ("ORG", 0.2, "Shared Organization"),
                                  ("LOCATION", 0.1, "Shared Location"), ("AMOUNT", 0.2, "Shared Amount")):
                na = {e.norm: e.value for e in ea if e.type == typ}
                nb = {e.norm: e.value for e in eb if e.type == typ}
                shared = set(na) & set(nb)
                for n in list(shared)[:3]:
                    ev.append({"type": rtype, "value": na[n], "detail": "Exact normalized match"})
                    weights.append(w)
                if typ == "PERSON":
                    for x, xv in na.items():
                        for y, yv in nb.items():
                            if x != y and x not in shared and y not in shared and nlp.similarity(x, y) >= 0.82:
                                ev.append({"type": "Shared Person", "value": f"{xv} ≈ {yv}",
                                           "detail": f"Possible match (name similarity {nlp.similarity(x, y):.0%})"})
                                weights.append(0.25)
            c = sim[i][j]
            if c >= thr:
                ev.append({"type": "Similar Content", "value": f"{c:.0%} TF-IDF cosine similarity",
                           "detail": "Overlapping vocabulary"})
                weights.append(min(0.5, c * 0.6))
            ev_dates = {e.date for e in db.query(Event).filter(Event.record_id == a.id, Event.kind != "mention")}
            shared_dates = ev_dates & {e.date for e in db.query(Event).filter(Event.record_id == b.id, Event.kind != "mention")}
            for d in list(shared_dates)[:2]:
                ev.append({"type": "Associated Event", "value": nlp.fmt_date(d), "detail": "Both records reference this event date"})
                weights.append(0.12)
            if not weights:
                continue
            p = 1.0
            for w in weights:
                p *= (1 - w)
            score = round(min(0.97, 1 - p), 3)  # never express certainty
            if score < min_score:
                continue
            strongest = max(zip(weights, ev), key=lambda t: t[0])[1]["type"]
            db.add(Relationship(case_id=case_id, source_record_id=a.id, target_record_id=b.id, rel_type=strongest,
                                score=score, label=_label_for(score), evidence=ev))
            count += 1
    return count


def _quote(rec, v: dict) -> dict:
    """The exact line of text a value was read from, for the reviewer."""
    lines = (rec.text or "").split("\n")
    i = v.get("line", -1)
    line = lines[i].strip() if 0 <= i < len(lines) else ""
    return {"record_id": rec.id, "label": v.get("source_label") or v.get("label"), "quote": line[:300],
            "value": str(v.get("raw", v.get("value")))}


def _conflicts(db, case_id, recs, settings, ents_by, pending):
    found: dict[str, dict] = {}
    name_thr = float(settings.get("name_variation_threshold", 0.72))
    vals = {r.id: _field_values(r) for r in recs}
    by_id = {r.id: r for r in recs}

    for field, (ctype, severity) in CONSISTENCY_FIELDS.items():
        pairs = [(r.id, vals[r.id][field]) for r in recs if field in vals[r.id]]
        if len(pairs) < 2:
            continue
        norm = lambda v: str(v["value"])
        counts = Counter(norm(v) for _, v in pairs)
        if len(counts) < 2:
            continue
        top = max(counts.items(), key=lambda kv: (kv[1], -min(rid for rid, v in pairs if norm(v) == kv[0])))[0]
        base_id, base_v = next((rid, v) for rid, v in pairs if norm(v) == top)
        for rid, v in pairs:
            if norm(v) == top:
                continue
            label = nlp.FIELD_LABELS.get(field, "Transaction amount" if field == "transaction_amount" else field)
            if field == "transaction_amount":
                label = "Transaction amount"
            va, vb = _display(base_v), _display(v)
            if ctype == "Identity Mismatch":
                s = nlp.similarity(norm(base_v), norm(v))
                if s >= name_thr:
                    expl = (f"A slight variation of the {label.lower()} was extracted from related records "
                            f"(“{va}” vs “{vb}”, {s:.0%} similar). This may be a typographical difference "
                            f"or may refer to a different party.")
                else:
                    expl = f"Different values for {label.lower()} were extracted from related records."
            elif ctype == "Identifier Mismatch":
                s = nlp.similarity(norm(base_v), norm(v))
                expl = (f"Different {label.lower()} values were extracted from related records"
                        + (f"; the identifiers are {s:.0%} similar, which may indicate transposed or mistyped characters." if s >= 0.7 else "."))
            elif ctype == "Amount Mismatch":
                diff = abs(float(base_v["value"]) - float(v["value"]))
                expl = (f"Different amounts were extracted from related records (difference of "
                        f"{nlp.fmt_amount(diff, base_v.get('raw', ''))}). This could reflect a partial payment, an "
                        f"adjustment, or an inconsistency.")
            elif ctype == "Date Mismatch":
                expl = f"Different dates were extracted from related records for the {label.lower()}."
            else:
                expl = f"Different {label.lower()} values were extracted from related records."
            a, b = sorted([base_id, rid])
            key = f"{field}:{a}:{b}"
            ra, rb = (base_id, rid)
            reasons = [f"Both records contain a “{label}” field (read from “{base_v.get('source_label', label)}” and "
                       f"“{v.get('source_label', label)}”).",
                       f"The extracted values differ: {va} vs {vb}."]
            if ctype in ("Identity Mismatch", "Identifier Mismatch"):
                reasons.append(f"String similarity between the two values: {nlp.similarity(norm(base_v), norm(v)):.0%}.")
            if ctype == "Amount Mismatch":
                reasons.append(f"Difference: {nlp.fmt_amount(abs(float(base_v['value']) - float(v['value'])), base_v.get('raw', ''))}.")
            if ctype == "Date Mismatch":
                try:
                    gap = abs((date.fromisoformat(str(v["value"])) - date.fromisoformat(str(base_v["value"]))).days)
                    reasons.append(f"The dates are {gap} day{'s' if gap != 1 else ''} apart.")
                except ValueError:
                    pass
            if len(pairs) > 2:
                reasons.append(f"{counts[top]} of {len(pairs)} records agree on {va}; this record is the outlier.")
            found[key] = dict(type=ctype, field=label, record_a_id=ra, record_b_id=rb, value_a=va, value_b=vb,
                              explanation=expl + " " + RECOMMEND.get(ctype, ""), severity=severity,
                              evidence={"a": _quote(by_id[ra], base_v), "b": _quote(by_id[rb], v), "reasons": reasons,
                                        "rule": f"Consistency check on “{label}” across records in the case"})

    refs = {r.id: {e.norm for e in ents_by[r.id] if e.type in ("ID", "DOC_REF")} for r in recs}
    for early_f, late_f, text in CHRONOLOGY_RULES:
        for ra in recs:
            if early_f not in vals[ra.id]:
                continue
            for rb in recs:
                if late_f not in vals[rb.id]:
                    continue
                # only compare chronology within one record or between records sharing a document reference
                if ra.id != rb.id and not (refs[ra.id] & refs[rb.id]):
                    continue
                e, l = vals[ra.id][early_f]["value"], vals[rb.id][late_f]["value"]
                if l < e:
                    key = f"chrono:{early_f}>{late_f}:{ra.id}:{rb.id}"
                    found[key] = dict(
                        type="Date Mismatch", field=f"Chronology: {nlp.FIELD_LABELS[early_f]} → {nlp.FIELD_LABELS[late_f]}",
                        record_a_id=ra.id, record_b_id=rb.id,
                        value_a=f"{nlp.FIELD_LABELS[early_f]}: {nlp.fmt_date(e)}",
                        value_b=f"{nlp.FIELD_LABELS[late_f]}: {nlp.fmt_date(l)}",
                        explanation=f"{text} Extracted dates are out of the expected order. " + RECOMMEND["Date Mismatch"],
                        severity="medium",
                        evidence={"a": _quote(ra, vals[ra.id][early_f]), "b": _quote(rb, vals[rb.id][late_f]),
                                  "rule": f"Chronology rule: {nlp.FIELD_LABELS[early_f]} should not be later than {nlp.FIELD_LABELS[late_f]}",
                                  "reasons": [text,
                                              f"{nlp.FIELD_LABELS[late_f]} ({nlp.fmt_date(l)}) is "
                                              f"{(date.fromisoformat(e) - date.fromisoformat(l)).days} days before "
                                              f"{nlp.FIELD_LABELS[early_f].lower()} ({nlp.fmt_date(e)}).",
                                              ("Both values come from the same record." if ra.id == rb.id else
                                               "The records are linked by a shared reference: "
                                               + ", ".join(sorted(refs[ra.id] & refs[rb.id])[:3]) + ".")]})

    # metadata / signature anomalies (medium & high) become reviewable items on the record itself
    for r in recs:
        for fl in (r.meta or {}).get("flags", []):
            if fl.get("severity") not in ("medium", "high"):
                continue
            ctype = "Integrity Signal" if fl["code"].startswith("signature_") else "Metadata Anomaly"
            found[f"meta:{fl['code']}:{r.id}"] = dict(
                type=ctype, field=fl["title"], record_a_id=r.id, record_b_id=r.id, value_a=fl["value_a"],
                value_b=fl["value_b"], explanation=fl["detail"] + " " + RECOMMEND[ctype], severity=fl["severity"],
                evidence={"a": {"label": "File metadata", "quote": fl["value_a"], "value": fl["value_a"]},
                          "b": {"label": "File metadata", "quote": fl["value_b"], "value": fl["value_b"]},
                          "rule": "Metadata / signature integrity rule", "reasons": [fl["detail"]]})

    existing = {c.key: c for c in db.query(Conflict).filter(Conflict.case_id == case_id)}
    new = 0
    for key, d in found.items():
        if key in existing:
            c = existing[key]
            for k in ("type", "field", "value_a", "value_b", "explanation", "severity", "record_a_id", "record_b_id", "evidence"):
                setattr(c, k, d.get(k))
        else:
            c = Conflict(case_id=case_id, key=key, status="requires_review", **d)
            db.add(c)
            db.flush()
            new += 1
            ra, rb = by_id.get(d["record_a_id"]), by_id.get(d["record_b_id"])
            pending.append(dict(action=f"Conflict identified: {d['type']}", category="conflict", target_type="conflict",
                                target_id=c.id, target_label=d["field"], case_id=case_id,
                                details=f"{ra.filename if ra else '?'}: {d['value_a']}  |  {rb.filename if rb else '?'}: {d['value_b']}"))
    for key, c in existing.items():
        if key not in found and c.status == "requires_review":
            db.delete(c)
    return new, len(found)


def _display(v: dict) -> str:
    if v["type"] == "DATE":
        return nlp.fmt_date(v["value"])
    if v["type"] == "AMOUNT":
        return nlp.fmt_amount(float(v["value"]), v.get("raw", ""))
    return str(v.get("raw") or v["value"])


def recompute_statuses(db, case_id: int):
    """Record status → Completed / Requires Review; case status is derived unless locked by a user."""
    unresolved = db.query(Conflict).filter(Conflict.case_id == case_id,
                                           Conflict.status.in_(["requires_review", "escalated"])).all()
    flagged = {c.record_a_id for c in unresolved} | {c.record_b_id for c in unresolved}
    settings = get_settings(db)
    low = float(settings.get("low_ocr_confidence", 70))
    recs = db.query(Record).filter(Record.case_id == case_id).all()
    processing = False
    for r in recs:
        if r.stage in ("complete",) or r.stage in ("relationships", "conflicts") and r.processed_at:
            needs = (r.id in flagged or r.text_method == "failed"
                     or (r.ocr_confidence is not None and r.ocr_confidence < low))
            r.status = "Requires Review" if needs else "Completed"
            r.stage = "complete"
        elif r.stage != "failed":
            processing = True
    case = db.get(Case, case_id)
    if case and not case.status_locked and not case.archived:
        case.status = "processing" if processing else ("requires_review" if unresolved else "active")
        case.updated_at = utcnow()
    db.commit()


# ================================================================== full case job (demo / re-run)
def run_case_job(case_id: int, actor_id: int | None, pace: float = 0.8):
    """Re-runs the whole analysis for a case and reports stage progress in case.analysis_state."""
    db = SessionLocal()
    try:
        from ..models import User
        actor = db.get(User, actor_id) if actor_id else None
        case = db.get(Case, case_id)
        state = {"running": True, "stage": None, "stages": [], "started_at": _now().isoformat(), "error": None}

        def stage(key, detail=""):
            state["stage"] = key
            if state["stages"]:
                state["stages"][-1]["done"] = True
            state["stages"].append({"key": key, "label": dict(CASE_STAGES)[key], "detail": detail, "done": key == "complete"})
            case.analysis_state = dict(state)
            db.commit()

        recs = db.query(Record).filter(Record.case_id == case_id, Record.sha256.isnot(None)).order_by(Record.id).all()
        settings = get_settings(db)

        t0 = time.time()
        stage("securing", f"{len(recs)} records in secure storage")
        blobs = {}
        missing = 0
        for r in recs:
            if storage.exists(r.storage_key):
                blobs[r.id] = storage.read(r.storage_key)
            else:
                missing += 1
        _pace(t0, pace)

        t0 = time.time()
        stage("hashing")
        changed = []
        for r in recs:
            if r.id in blobs and hashlib.sha256(blobs[r.id]).hexdigest() != r.sha256:
                changed.append(r.filename)
        detail = (f"{len(recs) - len(changed) - missing}/{len(recs)} fingerprints match the recorded SHA-256"
                  + (f"; changed: {', '.join(changed)}" if changed else ""))
        state["stages"][-1]["detail"] = detail
        audit(db, None, "System re-verified SHA-256 fingerprints", category="pipeline", target_type="case",
              target_id=case.id, target_label=case.code, case_id=case.id,
              result="success" if not changed and not missing else "failed", details=detail)
        _pace(t0, pace)

        t0 = time.time()
        stage("extracting")
        for r in recs:
            if r.id in blobs:
                extract_record(db, r, blobs[r.id], settings, 0, log_audit=False)
                r.stage = "conflicts"
                db.commit()
        n_ent = db.query(Entity).filter(Entity.case_id == case_id).count()
        state["stages"][-1]["detail"] = f"{n_ent} entities extracted from {len(recs)} records"
        _pace(t0, pace)

        t0 = time.time()
        stage("connecting")
        res = run_case_analysis(case_id, db)
        state["stages"][-1]["detail"] = f"{res['relationships']} relationship signals between records"
        audit(db, None, f"System detected {res['relationships']} relationship signals", category="pipeline",
              target_type="case", target_id=case.id, target_label=case.code, case_id=case.id)
        _pace(t0, pace)

        t0 = time.time()
        n_ev = db.query(Event).filter(Event.case_id == case_id).count()
        stage("timeline", f"{n_ev} events placed in chronological order")
        _pace(t0, pace)

        t0 = time.time()
        stage("consistency", f"{res['conflicts']} potential inconsistencies ({res['new_conflicts']} new)")
        for r in recs:
            r.processed_at = r.processed_at or _now()
        db.commit()
        recompute_statuses(db, case_id)
        _pace(t0, pace)

        stage("complete", "Evidence signals ready for human review")
        state["running"] = False
        state["finished_at"] = _now().isoformat()
        state["result"] = res
        case.analysis_state = dict(state)
        db.commit()
        audit(db, actor, "Case analysis completed", category="analysis", target_type="case", target_id=case.id,
              target_label=case.code, case_id=case.id,
              details=f"{res['relationships']} relationships, {res['conflicts']} potential inconsistencies")
    except Exception as e:
        log.exception("case job failed")
        db.rollback()
        case = db.get(Case, case_id)
        if case:
            st = dict(case.analysis_state or {})
            st.update({"running": False, "error": "Analysis could not be completed. Please try again."})
            case.analysis_state = st
            db.commit()
    finally:
        db.close()
