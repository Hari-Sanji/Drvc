import hashlib
import html
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, Case, Conflict, Entity, Event, Record, Relationship, Report, ReviewAction, User, utcnow
from ..pipeline import nlp
from ..security import accessible_case_ids, audit, get_case_or_404, require
from ..ser import CONFLICT_STATUS_LABELS, case_out, event_flags, iso, merge_events, records_map
from ..settings_store import get_settings

router = APIRouter(prefix="/api", tags=["Reports"])

DISCLAIMER = ("This report presents extracted digital evidence signals and detected relationships or inconsistencies. "
              "It does not establish absolute authenticity or prove a real-world event. Final determination remains "
              "subject to human verification.")
LIMITATIONS = [
    "SHA-256 fingerprints show whether stored content has changed relative to the recorded hash; they do not prove the real-world truth of a document.",
    "Metadata can be missing, stripped or altered; absence of metadata is not evidence of tampering.",
    "OCR and entity extraction are automated and may contain recognition errors, especially on low-quality scans.",
    "Relationship signals are probabilistic (Likely Related / Possible Match / Relationship Signal) and never certain.",
    "Potential inconsistencies may have legitimate explanations (corrections, partial payments, typographical errors).",
]


def build_report(db: Session, case: Case, user: User) -> dict:
    recs = db.query(Record).filter(Record.case_id == case.id).order_by(Record.id).all()
    ents = db.query(Entity).filter(Entity.case_id == case.id).all()
    evs = db.query(Event).filter(Event.case_id == case.id).order_by(Event.date, Event.id).all()
    flags = event_flags(db, case.id, evs)
    rels = db.query(Relationship).filter(Relationship.case_id == case.id).order_by(Relationship.score.desc()).all()
    confs = db.query(Conflict).filter(Conflict.case_id == case.id).order_by(Conflict.id).all()
    reviews = db.query(ReviewAction).filter(ReviewAction.case_id == case.id).order_by(ReviewAction.created_at).all()
    audits = db.query(AuditLog).filter(AuditLog.case_id == case.id).order_by(AuditLog.ts).all()
    rmap = {r.id: r for r in recs}
    name = lambda rid: rmap[rid].filename if rid in rmap else f"Record #{rid}"
    co = case_out(db, case)
    data = {
        "report_type": "Contextual Verification Report",
        "generated_at": iso(utcnow()), "generated_by": {"name": user.name, "role": user.role},
        "organization": get_settings(db)["organization_name"],
        "synthetic_demo_data": case.is_demo,
        "case": {k: co[k] for k in ("code", "name", "description", "category", "status_label", "created_at",
                                     "record_count", "conflict_count", "unresolved_count", "review_status")}
        | {"owner": co["owner"]["name"] if co["owner"] else None},
        "records": [{
            "id": r.id, "filename": r.filename, "type": r.ext[1:].upper(), "document_type": r.doc_type, "size": r.size,
            "sha256": r.sha256, "uploaded_at": iso(r.uploaded_at), "processed_at": iso(r.processed_at),
            "status": r.status, "text_method": r.text_method, "ocr_confidence": r.ocr_confidence,
            "metadata": r.meta or {}, "extracted_fields": {k: {"label": v["label"], "value": v["raw"]} for k, v in (r.fields or {}).items()},
            "text_excerpt": (r.text or "")[:600],
            "entities": [{"type": e.type, "value": e.value} for e in ents if e.record_id == r.id],
        } for r in recs],
        "entities_summary": {},
        "timeline": [{"date": m["date"], "time": m["time"], "event": m["label"],
                      "source": ", ".join(s["filename"] for s in m["sources"]), "sources": len(m["sources"]),
                      "confidence": m["confidence"], "flag": m["flag"]} for m in merge_events(evs, rmap, flags)],
        "relationships": [{"a": name(x.source_record_id), "b": name(x.target_record_id), "type": x.rel_type,
                           "label": x.label, "score": x.score, "evidence": x.evidence} for x in rels],
        "conflicts": [{"id": c.id, "type": c.type, "field": c.field, "record_a": name(c.record_a_id), "value_a": c.value_a,
                       "record_b": name(c.record_b_id), "value_b": c.value_b, "explanation": c.explanation,
                       "severity": c.severity, "status": CONFLICT_STATUS_LABELS.get(c.status, c.status),
                       "evidence": c.evidence} for c in confs],
        "review_actions": [{"at": iso(a.created_at), "user": a.user_name, "role": a.role, "action": a.action,
                            "subject": a.subject, "note": a.note,
                            "status_change": f"{CONFLICT_STATUS_LABELS.get(a.from_status or '', a.from_status)} → {CONFLICT_STATUS_LABELS.get(a.to_status or '', a.to_status)}" if a.from_status != a.to_status else None}
                           for a in reviews],
        "audit": [{"ts": iso(a.ts), "user": a.user_name, "role": a.role, "action": a.action, "result": a.result,
                   "details": a.details} for a in audits],
        "limitations": LIMITATIONS, "disclaimer": DISCLAIMER,
    }
    for e in ents:
        data["entities_summary"].setdefault(e.type, set()).add(e.value)
    data["entities_summary"] = {k: sorted(v) for k, v in data["entities_summary"].items()}
    return data


def _h(s):
    return html.escape(str(s if s is not None else "—"))


def render_html(d: dict) -> str:
    c = d["case"]
    css = """
    *{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;color:#1b1d2a;margin:0;background:#f7f3ef;line-height:1.5}
    .wrap{max-width:1000px;margin:0 auto;padding:40px 32px;background:#fff}
    header{background:linear-gradient(120deg,#1a1512,#5a2e17 45%,#8a4a24);color:#fff;padding:36px 32px;border-radius:16px;margin-bottom:28px}
    header .k{letter-spacing:.18em;text-transform:uppercase;font-size:11px;opacity:.8}
    header h1{margin:6px 0 4px;font-size:28px}header p{margin:0;opacity:.85}
    .flow{margin-top:14px;font-size:11px;letter-spacing:.2em;opacity:.85}
    .disc{border:1.5px solid #e0a106;background:#fff8e6;padding:16px 18px;border-radius:12px;margin:20px 0;font-weight:600;color:#6b4a00}
    .demo{display:inline-block;background:#fbeadd;color:#9a4a22;font-size:11px;font-weight:700;padding:3px 10px;border-radius:99px;letter-spacing:.06em}
    h2{font-size:18px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid #f1e6dc;color:#5a2e17}
    h3{font-size:14px;margin:18px 0 6px}
    table{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0 10px}
    th{text-align:left;background:#f8f1ea;color:#6b3a1e;font-weight:600}
    th,td{padding:7px 9px;border-bottom:1px solid #efe7df;vertical-align:top}
    .mono{font-family:Consolas,SFMono-Regular,Menlo,monospace;font-size:11px;word-break:break-all}
    .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
    .stat{border:1px solid #f1e6dc;border-radius:12px;padding:12px}.stat b{font-size:22px;display:block;color:#5a2e17}
    .pill{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600}
    .p-requires_review,.p-Requires{background:#fff1d6;color:#8a5a00}.p-Resolved,.p-Accepted,.p-Reviewed{background:#dcf7ea;color:#0b6b43}
    .p-Escalated{background:#ffe0e6;color:#a1143a}
    .conf{border:1px solid #f1d7dd;border-left:4px solid #e11d48;border-radius:10px;padding:12px 14px;margin:10px 0}
    .conf .vals{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0}
    .conf .v{background:#fcf8f4;border-radius:8px;padding:8px}
    .muted{color:#6b6f85}.chips span{display:inline-block;margin:2px 4px 2px 0;background:#f6efe8;border-radius:6px;padding:2px 7px;font-size:11.5px}
    footer{margin-top:40px;font-size:11px;color:#6b6f85;border-top:1px solid #eee;padding-top:12px}
    .noprint{position:fixed;right:20px;top:20px}.noprint button{background:#5a2e17;color:#fff;border:0;border-radius:10px;padding:10px 16px;font-weight:600;cursor:pointer}
    @media print{.noprint{display:none}body{background:#fff}.wrap{padding:0}header{-webkit-print-color-adjust:exact;print-color-adjust:exact}h2{break-after:avoid}.conf{break-inside:avoid}}
    """
    p = []
    p.append(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Verification Report — {_h(c['code'])}</title><style>{css}</style></head><body>"
             "<div class='noprint'><button onclick='window.print()'>Print / Save as PDF</button></div><div class='wrap'>")
    p.append(f"<header><div class='k'>Contextual Verification Report · {_h(d['organization'])}</div><h1>{_h(c['name'])}</h1>"
             f"<p>{_h(c['code'])} · Generated {_h(d['generated_at'][:19].replace('T', ' '))} UTC by {_h(d['generated_by']['name'])}</p>"
             "<div class='flow'>SCATTERED → EXTRACT → CONNECT → ANALYZE → REVIEW</div></header>")
    if d["synthetic_demo_data"]:
        p.append("<span class='demo'>SYNTHETIC DEMO DATA</span>")
    p.append(f"<div class='disc'>⚠ {_h(d['disclaimer'])}</div>")
    p.append("<h2>1. Case details</h2><table>")
    for k, lbl in (("code", "Case ID"), ("name", "Case name"), ("description", "Description"), ("category", "Category"),
                   ("status_label", "Status"), ("owner", "Owner"), ("created_at", "Created"), ("review_status", "Review status")):
        p.append(f"<tr><th style='width:180px'>{lbl}</th><td>{_h(c.get(k))}</td></tr>")
    p.append("</table>")
    unresolved = sum(1 for x in d["conflicts"] if x["status"] in ("Requires Review", "Escalated"))
    p.append(f"<div class='grid'><div class='stat'><b>{len(d['records'])}</b>Records</div><div class='stat'><b>{sum(1 for r in d['records'] if r['sha256'])}</b>SHA-256 fingerprints</div>"
             f"<div class='stat'><b>{len(d['relationships'])}</b>Relationship signals</div><div class='stat'><b>{len(d['conflicts'])}</b>Potential inconsistencies ({unresolved} open)</div></div>")

    p.append("<h2>2. Record list &amp; integrity fingerprints</h2><table><tr><th>#</th><th>File</th><th>Type</th><th>Size</th><th>SHA-256</th><th>Status</th></tr>")
    for r in d["records"]:
        p.append(f"<tr><td>{r['id']}</td><td><b>{_h(r['filename'])}</b><br><span class='muted'>{_h(r['document_type'])}</span></td>"
                 f"<td>{_h(r['type'])}</td><td>{r['size']:,} B</td><td class='mono'>{_h(r['sha256'])}</td><td>{_h(r['status'])}</td></tr>")
    p.append("</table><p class='muted'>SHA-256 provides a content fingerprint and helps identify changes to file content relative to the recorded hash. It does not prove the real-world truth of a document.</p>")

    p.append("<h2>3. Metadata &amp; extracted information</h2>")
    for r in d["records"]:
        md = r["metadata"]
        p.append(f"<h3>{_h(r['filename'])} <span class='muted'>· {_h(r['text_method'])}"
                 + (f" · OCR confidence {r['ocr_confidence']:.0f}%" if r["ocr_confidence"] is not None else "") + "</span></h3>")
        if md.get("available"):
            p.append("<table>" + "".join(f"<tr><th style='width:200px'>{_h(m['label'])}</th><td>{_h(m['value'])}</td></tr>" for m in md["available"]) + "</table>")
        else:
            p.append("<p class='muted'>No readable metadata was available.</p>")
        if md.get("not_available"):
            p.append(f"<p class='muted'>Metadata not available: {_h(', '.join(md['not_available']))}</p>")
        if r["extracted_fields"]:
            p.append("<table>" + "".join(f"<tr><th style='width:200px'>{_h(v['label'])}</th><td>{_h(v['value'])}</td></tr>" for v in r["extracted_fields"].values()) + "</table>")
        if r["entities"]:
            p.append("<div class='chips'>" + "".join(f"<span><b>{_h(e['type'])}</b> {_h(e['value'])}</span>" for e in r["entities"]) + "</div>")

    p.append("<h2>4. Entities</h2><table>")
    for t, vals in d["entities_summary"].items():
        p.append(f"<tr><th style='width:140px'>{_h(t)}</th><td class='chips'>{''.join(f'<span>{_h(v)}</span>' for v in vals)}</td></tr>")
    p.append("</table>")

    p.append("<h2>5. Events &amp; timeline</h2>")
    if d["timeline"]:
        p.append("<table><tr><th>Date</th><th>Event</th><th>Source record</th><th>Confidence</th><th>Flag</th></tr>")
        for e in d["timeline"]:
            p.append(f"<tr><td>{_h(nlp.fmt_date(e['date']))}{(' ' + _h(e['time'])) if e['time'] else ''}</td><td>{_h(e['event'])}</td>"
                     f"<td>{_h(e['source'])}</td><td>{e['confidence']:.0%}</td><td>{_h({'conflict': 'Conflicting date', 'review': 'Requires review', 'resolved': 'Reviewed'}.get(e['flag'], 'Normal'))}</td></tr>")
        p.append("</table>")
    else:
        p.append("<p class='muted'>No dated events were extracted.</p>")

    p.append("<h2>6. Relationship summary</h2>")
    if d["relationships"]:
        p.append("<table><tr><th>Record A</th><th>Record B</th><th>Signal</th><th>Score</th><th>Evidence</th></tr>")
        for x in d["relationships"]:
            ev = "; ".join(f"{e['type']}: {e['value']}" for e in x["evidence"][:4])
            p.append(f"<tr><td>{_h(x['a'])}</td><td>{_h(x['b'])}</td><td>{_h(x['label'])}<br><span class='muted'>{_h(x['type'])}</span></td>"
                     f"<td>{x['score']:.0%}</td><td>{_h(ev)}</td></tr>")
        p.append("</table>")
    else:
        p.append("<p class='muted'>No significant relationship signals detected.</p>")

    p.append("<h2>7. Conflict summary — potential inconsistencies</h2>")
    if d["conflicts"]:
        for x in d["conflicts"]:
            p.append(f"<div class='conf'><b>{_h(x['type'])}</b> · {_h(x['field'])} <span class='pill p-{_h(x['status'].split()[0])}'>{_h(x['status'])}</span>"
                     f"<div class='vals'><div class='v'><span class='muted'>{_h(x['record_a'])}</span><br><b>{_h(x['value_a'])}</b></div>"
                     f"<div class='v'><span class='muted'>{_h(x['record_b'])}</span><br><b>{_h(x['value_b'])}</b></div></div>"
                     f"<div class='muted'>{_h(x['explanation'])}</div></div>")
    else:
        p.append("<p class='muted'>No potential inconsistencies detected in the currently analyzed records.</p>")

    p.append("<h2>8. Review actions</h2>")
    if d["review_actions"]:
        p.append("<table><tr><th>When</th><th>Reviewer</th><th>Action</th><th>Subject</th><th>Note</th></tr>")
        for a in d["review_actions"]:
            p.append(f"<tr><td>{_h(a['at'][:16].replace('T', ' '))}</td><td>{_h(a['user'])}<br><span class='muted'>{_h(a['role'])}</span></td>"
                     f"<td>{_h(a['action'].replace('_', ' ').title())}{('<br><span class=muted>' + _h(a['status_change']) + '</span>') if a['status_change'] else ''}</td>"
                     f"<td>{_h(a['subject'])}</td><td>{_h(a['note'])}</td></tr>")
        p.append("</table>")
    else:
        p.append("<p class='muted'>No review actions have been recorded yet.</p>")

    p.append(f"<h2>9. Audit information</h2><p class='muted'>{len(d['audit'])} audit entries recorded for this case (most recent 60 shown).</p><table><tr><th>Timestamp (UTC)</th><th>Actor</th><th>Action</th><th>Result</th></tr>")
    for a in d["audit"][-60:]:
        p.append(f"<tr><td class='mono'>{_h(a['ts'][:19].replace('T', ' '))}</td><td>{_h(a['user'])} <span class='muted'>({_h(a['role'])})</span></td>"
                 f"<td>{_h(a['action'])}<br><span class='muted'>{_h(a['details'][:160])}</span></td><td>{_h(a['result'])}</td></tr>")
    p.append("</table>")

    p.append("<h2>10. Limitations &amp; disclaimer</h2><ul>" + "".join(f"<li>{_h(l)}</li>" for l in d["limitations"]) + "</ul>")
    p.append(f"<div class='disc'>{_h(d['disclaimer'])}</div>")
    p.append("<footer>We surface evidence signals. Humans make the final determination. · Digital Record Context Verification</footer></div></body></html>")
    return "".join(p)


def report_meta(r: Report, case: Case | None = None):
    return {"id": r.id, "case_id": r.case_id, "case_code": case.code if case else None, "case_name": case.name if case else None,
            "title": r.title, "created_by": r.created_by_name, "created_at": iso(r.created_at), "sha256": r.sha256,
            "summary": r.summary}


@router.post("/cases/{case_id}/reports", status_code=201)
def generate(case_id: int, user: User = Depends(require("report:generate")), db: Session = Depends(get_db)):
    case = get_case_or_404(db, user, case_id)
    if db.query(Record).filter(Record.case_id == case.id).count() == 0:
        raise HTTPException(400, "No records uploaded. Add records before generating a report.")
    data = build_report(db, case, user)
    body = render_html(data)
    digest = hashlib.sha256(body.encode()).hexdigest()
    summary = {"records": len(data["records"]), "relationships": len(data["relationships"]),
               "conflicts": len(data["conflicts"]), "reviews": len(data["review_actions"]), "events": len(data["timeline"]),
               "unresolved": sum(1 for x in data["conflicts"] if x["status"] in ("Requires Review", "Escalated"))}
    r = Report(case_id=case.id, title=f"Verification Report — {case.code}", created_by=user.id, created_by_name=user.name,
               content_html=body, content_json=data, sha256=digest, summary=summary)
    db.add(r)
    db.commit()
    audit(db, user, "Generated verification report", category="report", target_type="report", target_id=r.id,
          target_label=r.title, case_id=case.id, details=f"Report SHA-256 {digest[:16]}…")
    return report_meta(r, case)


@router.get("/reports")
def list_reports(case_id: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                 user: User = Depends(require("report:view")), db: Session = Depends(get_db)):
    q = db.query(Report)
    allowed = accessible_case_ids(db, user)
    if allowed is not None:
        q = q.filter(Report.case_id.in_(allowed or [-1]))
    if case_id:
        q = q.filter(Report.case_id == case_id)
    total = q.count()
    rows = q.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    cases = {c.id: c for c in db.query(Case).filter(Case.id.in_({r.case_id for r in rows} or {-1}))}
    return {"items": [report_meta(r, cases.get(r.case_id)) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/reports/{report_id}/download")
def download(report_id: int, format: str = "html", user: User = Depends(require("report:view")), db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found.")
    case = get_case_or_404(db, user, r.case_id)
    audit(db, user, f"Downloaded report ({format.upper()})", category="report", target_type="report", target_id=r.id,
          target_label=r.title, case_id=r.case_id)
    base = f"DRCV-Report-{case.code}-{r.id}"
    if format in ("pdf", "summary"):
        from ..pdf_report import build_full_pdf, build_summary_pdf
        try:
            pdf = (build_full_pdf if format == "pdf" else build_summary_pdf)(r.content_json, r.sha256)
        except Exception:
            import logging
            logging.getLogger("drcv").exception("PDF rendering failed")
            raise HTTPException(500, "The PDF could not be generated. The HTML report is still available.")
        name = f"{base}.pdf" if format == "pdf" else f"DRCV-Summary-{case.code}-{r.id}.pdf"
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})
    if format == "json":
        return Response(json.dumps(r.content_json, indent=2, ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{base}.json"'})
    return Response(r.content_html, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{base}.html"'})
