"""End-to-end API test: python tests/test_api.py  (uses a fresh temporary data directory)."""
import hashlib
import io
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
TMP = tempfile.mkdtemp(prefix="drcv-test-")
os.environ["DRCV_DATA_DIR"] = TMP
if len(sys.argv) > 1:
    os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASS = 0


def ok(cond, msg):
    global PASS
    if not cond:
        raise AssertionError(msg)
    PASS += 1
    print("  ✓", msg)


def login(c, email, pw):
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


with TestClient(app) as c:
    print("Authentication")
    ok(c.get("/api/health").status_code == 200, "health endpoint")
    ok(c.post("/api/auth/login", json={"email": "admin@demo.local", "password": "wrong"}).status_code == 401, "wrong password rejected")
    ok(c.get("/api/cases").status_code == 401, "unauthenticated request rejected")
    ok(c.get("/api/cases", headers={"Authorization": "Bearer garbage"}).status_code == 401, "invalid token rejected")
    A = login(c, "admin@demo.local", "Admin@123")
    I = login(c, "investigator@demo.local", "Investigator@123")
    R = login(c, "reviewer@demo.local", "Reviewer@123")
    V = login(c, "viewer@demo.local", "Viewer@123")
    ok(len(c.get("/api/auth/demo-accounts").json()) == 4, "demo accounts listed")
    ok("user:manage" in c.get("/api/auth/me", headers=A).json()["permissions"], "admin has user:manage")

    print("RBAC")
    ok(c.get("/api/users", headers=V).status_code == 403, "viewer cannot list users")
    ok(c.get("/api/users", headers=R).status_code == 403, "reviewer cannot manage users")
    ok(c.get("/api/users", headers=I).status_code == 403, "investigator cannot manage users")
    ok(c.get("/api/users", headers=A).status_code == 200, "admin can list users")
    ok(c.post("/api/cases", headers=V, json={"name": "Nope case"}).status_code == 403, "viewer cannot create case")
    ok(c.post("/api/cases", headers=R, json={"name": "Nope case"}).status_code == 403, "reviewer cannot create case")
    ok(c.put("/api/settings", headers=I, json={"ocr_enabled": False}).status_code == 403, "investigator cannot change settings")
    ok(c.get("/api/audit", headers=V).status_code == 403, "viewer cannot open audit log")
    ok(c.get("/api/audit/export", headers=I).status_code == 403, "investigator cannot export audit")
    cases_r = c.get("/api/cases", headers=R).json()["items"]
    cases_a = c.get("/api/cases", headers=A).json()["items"]
    ok(len(cases_r) == 2 and len(cases_a) == 3, "reviewer sees only assigned cases (2 of 3)")
    lease = next(x for x in cases_a if "Lease" in x["name"])
    ok(c.get(f"/api/cases/{lease['id']}", headers=R).status_code == 403, "reviewer blocked from unassigned case")

    print("Dashboard (computed from DB)")
    d = c.get("/api/dashboard", headers=A).json()
    ok(d["stats"]["total_records"] == 12 and d["stats"]["integrity_verified"] == 12, "12 records, all hashed")
    ok(d["stats"]["potential_conflicts"] == 9, f"9 potential conflicts incl. 2 metadata anomalies (got {d['stats']['potential_conflicts']})")
    ok(d["stats"]["requires_review"] == 8, f"8 unresolved review items (got {d['stats']['requires_review']})")

    print("Demo case analysis")
    acad = next(x for x in cases_a if x["name"] == "Academic Record Verification")
    confs = c.get(f"/api/conflicts?case_id={acad['id']}", headers=A).json()["items"]
    types = sorted(x["type"] for x in confs)
    ok(types == ["Date Mismatch", "Identifier Mismatch", "Identity Mismatch", "Metadata Anomaly"], f"academic conflicts: {types}")
    tl = c.get(f"/api/cases/{acad['id']}/timeline", headers=A).json()
    ok(len(tl["events"]) >= 8 and tl["counts"]["conflict"] >= 2, "timeline populated with conflicting dates flagged")
    g = c.get(f"/api/cases/{acad['id']}/graph", headers=A).json()
    ok(any(n["type"] == "person" for n in g["nodes"]) and any(e["type"] == "relationship" for e in g["edges"]), "graph has people and relationships")
    r = c.post("/api/demo/launch", headers=A).json()
    ok(r["started"], "demo launch starts analysis job")
    for _ in range(80):
        st = c.get(f"/api/cases/{acad['id']}/analysis-status", headers=A).json()["state"]
        if not st.get("running"):
            break
        time.sleep(0.5)
    ok(st.get("stage") == "complete" and len(st["stages"]) == 7, "analysis job ran all 7 stages")
    ok("5/5 fingerprints match" in st["stages"][1]["detail"], "stored SHA-256 fingerprints re-verified")
    ok(c.post("/api/demo/launch", headers=V).json()["started"] is False, "viewer demo launch is read-only")

    print("Case + upload pipeline")
    r = c.post("/api/cases", headers=I, json={"name": "Test upload case", "description": "t"})
    ok(r.status_code == 201, "investigator creates case")
    cid = r.json()["id"]
    txt1 = b"Invoice No: INV-9-777\nInvoice Date: 01 March 2026\nBill To: Alpha Traders\nGrand Total: Rs. 5,000.00\n"
    txt2 = b"Receipt No: RC-1\nReceipt Date: 25 February 2026\nAgainst Invoice: INV-9-777\nAmount Received: Rs. 4,000.00\n"
    files = [("files", ("inv.txt", txt1, "text/plain")), ("files", ("rcpt.txt", txt2, "text/plain")),
             ("files", ("evil.exe", b"MZ....", "application/octet-stream")),
             ("files", ("fake.pdf", b"not a pdf", "application/pdf"))]
    ok(c.post(f"/api/cases/{cid}/records", headers=V, files=files[:1]).status_code == 403, "viewer cannot upload")
    ok(c.post(f"/api/cases/{cid}/records", headers=R, files=files[:1]).status_code == 403, "reviewer cannot upload")
    up = c.post(f"/api/cases/{cid}/records", headers=I, files=files).json()["results"]
    ok(up[0]["ok"] and up[1]["ok"], "valid files accepted")
    ok(not up[2]["ok"] and not up[3]["ok"], "wrong type and spoofed PDF rejected")
    rid = up[0]["record"]["id"]
    for _ in range(60):
        s1 = c.get(f"/api/records/{rid}/status", headers=I).json()
        s2 = c.get(f"/api/records/{up[1]['record']['id']}/status", headers=I).json()
        if s1["stage"] in ("complete", "failed") and s2["stage"] in ("complete", "failed"):
            break
        time.sleep(0.4)
    ok(s1["sha256"] == hashlib.sha256(txt1).hexdigest(), "real SHA-256 matches hashlib")
    ok(s1["status"] in ("Completed", "Requires Review"), f"processing finished ({s1['status']})")
    det = c.get(f"/api/records/{rid}", headers=I).json()
    ok(any(e["type"] == "DOC_REF" for e in det["entities"]), "entities extracted")
    ok(len(det["relationships"]) == 1, "relationship detected between uploaded records")
    ctypes = sorted(x["type"] for x in c.get(f"/api/conflicts?case_id={cid}", headers=I).json()["items"])
    ok(ctypes == ["Amount Mismatch", "Date Mismatch"], f"amount + chronology conflicts detected ({ctypes})")
    ok(c.post(f"/api/records/{rid}/verify", headers=I).json()["match"], "integrity re-verification matches")
    fr = c.get(f"/api/records/{rid}/file", headers=I)
    ok(fr.status_code == 200 and fr.content == txt1, "original file retrievable")
    vf = c.post("/api/records/verify-file", headers=V, files={"file": ("copy.txt", txt1)}).json()
    ok(len(vf["matches"]) == 1, "external copy matched by fingerprint")

    print("Review workflow")
    conf = next(x for x in c.get(f"/api/conflicts?case_id={acad['id']}&status=unresolved", headers=R).json()["items"]
                if x["type"] == "Date Mismatch")
    ok(c.post(f"/api/conflicts/{conf['id']}/review", headers=V, json={"action": "resolve", "note": "x"}).status_code == 403, "viewer cannot review")
    ok(c.post(f"/api/conflicts/{conf['id']}/review", headers=I, json={"action": "resolve", "note": "xyz"}).status_code == 403, "investigator cannot resolve")
    ok(c.post(f"/api/conflicts/{conf['id']}/review", headers=I, json={"action": "note", "note": "Requested originals"}).status_code == 200, "investigator can add note")
    ok(c.post(f"/api/conflicts/{conf['id']}/review", headers=R, json={"action": "resolve", "note": ""}).status_code == 422, "resolve requires a reason")
    rr = c.post(f"/api/conflicts/{conf['id']}/review", headers=R, json={"action": "resolve", "note": "Supporting document confirmed the later date."})
    ok(rr.status_code == 200 and rr.json()["status"] == "resolved", "reviewer resolves conflict")
    au = c.get(f"/api/audit?case_id={acad['id']}&category=review", headers=A).json()["items"]
    ok(any("resolved" in a["action"] for a in au), "review action written to audit log")

    print("Reports")
    ok(c.post(f"/api/cases/{acad['id']}/reports", headers=V).status_code == 403, "viewer cannot generate report")
    rep = c.post(f"/api/cases/{acad['id']}/reports", headers=R)
    ok(rep.status_code == 201, "reviewer generates report")
    h = c.get(f"/api/reports/{rep.json()['id']}/download", headers=V)
    ok(h.status_code == 200 and "does not establish absolute authenticity" in h.text, "viewer downloads report with disclaimer")
    ok(hashlib.sha256(h.content).hexdigest() == rep.json()["sha256"], "report fingerprint matches content")
    js = c.get(f"/api/reports/{rep.json()['id']}/download?format=json", headers=A).json()
    ok(len(js["records"]) == 5 and js["synthetic_demo_data"], "JSON report complete")

    print("Search / audit / admin")
    s = c.get("/api/search?q=Kumaar", headers=V).json()
    ok(any(e["value"] == "Rahul Kumaar" for e in s["entities"]), "search finds name variant")
    s = c.get("/api/search?q=WGU22CS054", headers=A).json()
    ok(len(s["records"]) >= 1, "search finds mismatched identifier")
    ok(c.get("/api/audit?result=denied", headers=A).json()["total"] > 5, "denied access attempts audited")
    ok(c.delete(f"/api/records/{rid}", headers=I).status_code == 403, "investigator cannot delete record")
    ok(c.delete(f"/api/records/{rid}", headers=A).status_code == 200, "admin deletes record")
    nu = c.post("/api/users", headers=A, json={"email": "new@x.org", "name": "New Person", "role": "viewer", "password": "Passw0rd!"})
    ok(nu.status_code == 201, "admin creates user")
    ok(c.post("/api/users", headers=A, json={"email": "weak@x.org", "name": "Weak", "role": "viewer", "password": "abc"}).status_code == 422, "weak password rejected")
    ok(c.post(f"/api/cases/{cid}/archive", headers=A).json()["archived"], "admin archives case")
    ok(c.get("/api/notifications", headers=R).status_code == 200, "notifications load")
    ok(c.get("/api/nope", headers=A).status_code == 404, "unknown API path 404s cleanly")

    print("v1.1: sentence entities & events (#1)")
    txt3 = (b"This is to certify that Priya Sharma has completed the course. On 11 September 2026 the application "
            b"was submitted by Arjun Prakash to the registrar.")
    cid2 = c.post("/api/cases", headers=I, json={"name": "Sentence test"}).json()["id"]
    rid3 = c.post(f"/api/cases/{cid2}/records", headers=I, files=[("files", ("letter.txt", txt3, "text/plain"))]).json()["results"][0]["record"]["id"]
    for _ in range(60):
        if c.get(f"/api/records/{rid3}/status", headers=I).json()["stage"] == "complete":
            break
        time.sleep(0.3)
    det3 = c.get(f"/api/records/{rid3}", headers=I).json()
    people = {e["value"] for e in det3["entities"] if e["type"] == "PERSON"}
    ok({"Priya Sharma", "Arjun Prakash"} <= people, f"names found in running sentences ({people})")
    ok(any(e["label"] == "Application submitted" for e in det3["events"]), "event detected from sentence verb")

    print("v1.1: signatures & metadata anomalies (#3, #4)")
    recs1 = c.get(f"/api/cases/{acad['id']}/overview", headers=A).json()["records"]
    sem = next(r for r in recs1 if r["doc_type"] == "Semester Marksheet")
    sig = c.get(f"/api/records/{sem['id']}", headers=A).json()["metadata"]["signatures"]
    ok(len(sig) == 1 and sig[0]["intact"] is True and sig[0]["trusted"] is False, "PDF signature verified intact (self-signed, not trusted)")
    allc = c.get("/api/conflicts?page_size=100", headers=A).json()["items"]
    ok(any(x["field"] == "Modified date is earlier than created date" for x in allc), "modified-before-created anomaly flagged")
    ok(any(x["field"] == "Editing software recorded in metadata" for x in allc), "editing-software anomaly flagged")
    from app.pipeline.extract import extract_metadata
    good = (Path(__file__).resolve().parent.parent / "demo_files" / "01_Semester_Marksheet_Sem8.pdf").read_bytes()
    bad = bytearray(good)
    i = bad.find(b"STATEMENT")
    bad[i:i + 9] = b"STATEMENX"
    ok(extract_metadata(".pdf", bytes(bad))["signatures"][0]["intact"] is False, "tampered signed PDF detected as changed after signing")

    print("v1.1: timeline merge & conflict evidence (#8, #9)")
    tl = c.get(f"/api/cases/{acad['id']}/timeline", headers=A).json()
    dob = next(e for e in tl["events"] if e["label"] == "Date of birth recorded")
    ok(dob["count"] == 4 and len(dob["sources"]) == 4, "date of birth merged into one event with its 4 source records")
    ok(tl["raw_count"] > len(tl["events"]), f"duplicates merged ({tl['raw_count']} → {len(tl['events'])})")
    idm = next(x for x in allc if x["type"] == "Identifier Mismatch")
    ev = idm["evidence"]
    ok("WGU22CS054" in ev["b"]["quote"] and len(ev["reasons"]) >= 3, "conflict carries source quote and reasons")

    print("v1.1: PDF report & summary (#16)")
    rid_rep = rep.json()["id"]
    pdf = c.get(f"/api/reports/{rid_rep}/download?format=pdf", headers=V)
    summ = c.get(f"/api/reports/{rid_rep}/download?format=summary", headers=V)
    ok(pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 20000, "full PDF report downloads")
    ok(summ.status_code == 200 and summ.content[:4] == b"%PDF", "executive summary PDF downloads")

    print("v1.1: bulk review (#21)")
    inv = next(x for x in cases_a if x["name"] == "Invoice Verification")
    open_ids = [x["id"] for x in c.get(f"/api/conflicts?case_id={inv['id']}&status=unresolved", headers=R).json()["items"]][:2]
    ok(c.post("/api/conflicts/bulk-review", headers=V, json={"ids": open_ids, "action": "accept", "note": "x ok"}).status_code == 403, "viewer cannot bulk review")
    ok(c.post("/api/conflicts/bulk-review", headers=I, json={"ids": open_ids, "action": "accept", "note": "x ok"}).status_code == 403, "investigator cannot bulk review")
    ok(c.post("/api/conflicts/bulk-review", headers=R, json={"ids": open_ids, "action": "accept"}).status_code == 422, "bulk decision requires a reason")
    br = c.post("/api/conflicts/bulk-review", headers=R, json={"ids": open_ids, "action": "accept", "note": "Confirmed with accounts team"}).json()
    ok(sorted(br["updated"]) == sorted(open_ids), "reviewer bulk-accepts 2 items")
    ok(len(c.get(f"/api/audit?case_id={inv['id']}&q=bulk", headers=A).json()["items"]) >= 2, "each bulk item audited")

    print("v1.1: password change & 2FA (#24)")
    I2 = login(c, "investigator@demo.local", "Investigator@123")
    ok(c.post("/api/auth/change-password", headers=I2, json={"current_password": "nope", "new_password": "NewPass123"}).status_code == 400, "wrong current password rejected")
    ch = c.post("/api/auth/change-password", headers=I2, json={"current_password": "Investigator@123", "new_password": "NewPass123"})
    ok(ch.status_code == 200, "password changed")
    ok(c.get("/api/auth/me", headers=I).status_code == 401, "old sessions signed out after password change")
    I3 = {"Authorization": f"Bearer {ch.json()['token']}"}
    ok(c.get("/api/auth/me", headers=I3).status_code == 200, "new session works")
    c.post("/api/auth/change-password", headers=I3, json={"current_password": "NewPass123", "new_password": "Investigator@123"})
    from app.security import totp_at
    U = login(c, "new@x.org", "Passw0rd!")
    setup = c.post("/api/auth/2fa/setup", headers=U).json()
    ok(setup["secret"] and setup["otpauth_uri"].startswith("otpauth://") and (setup["qr_svg"] or "").startswith("<svg"), "2FA setup returns secret + QR")
    now_code = totp_at(setup["secret"], int(time.time()) // 30)
    ok(c.post("/api/auth/2fa/enable", headers=U, json={"code": "000000" if now_code != "000000" else "111111"}).status_code == 400, "wrong code cannot enable 2FA")
    ok(c.post("/api/auth/2fa/enable", headers=U, json={"code": now_code}).status_code == 200, "2FA enabled with valid code")
    step = c.post("/api/auth/login", json={"email": "new@x.org", "password": "Passw0rd!"}).json()
    ok(step.get("requires_2fa") is True and "token" not in step, "login asks for 2FA code")
    ok(c.post("/api/auth/login", json={"email": "new@x.org", "password": "Passw0rd!", "code": "123456" if now_code != "123456" else "654321"}).status_code == 401, "wrong 2FA code rejected")
    ok("token" in c.post("/api/auth/login", json={"email": "new@x.org", "password": "Passw0rd!", "code": totp_at(setup["secret"], int(time.time()) // 30)}).json(), "correct 2FA code signs in")
    ok(c.post(f"/api/users/{nu.json()['id']}/reset-2fa", headers=A).json()["totp_enabled"] is False, "admin can reset a user's 2FA")

    print("v1.1: public try-it (#41)")
    before = c.get("/api/records?page_size=1", headers=A).json()["total"]
    pub = c.post("/api/public/analyze", files={"file": ("inv.pdf", (Path(__file__).resolve().parent.parent / "demo_files" / "11_Invoice_INV-2026-1142.pdf").read_bytes(), "application/pdf")})
    pj = pub.json()
    ok(pub.status_code == 200 and pj["stored"] is False and len(pj["sha256"]) == 64 and pj["entities"], "public analysis works without login")
    ok(c.get("/api/records?page_size=1", headers=A).json()["total"] == before, "public analysis stores nothing")
    ok(c.post("/api/public/analyze", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422, "public analysis validates file type")
    codes = [c.post("/api/public/analyze", files={"file": ("a.txt", b"hello world", "text/plain")}).status_code for _ in range(6)]
    ok(429 in codes, "public analysis is rate limited")

    print("v1.1: tamper-evident audit log (#28)")
    vr = c.get("/api/audit/verify", headers=A).json()
    ok(vr["ok"] and vr["checked"] > 100, f"audit chain intact ({vr['checked']} entries)")
    ok(all(x["hash"] for x in c.get("/api/audit?page_size=5", headers=A).json()["items"]), "entries carry chain hashes")
    from app.db import SessionLocal
    from app.models import AuditLog
    s_ = SessionLocal()
    victim = s_.query(AuditLog).filter(AuditLog.action.like("%resolved%")).first()
    victim.details = "Reason: nothing to see here"
    s_.commit(); s_.close()
    vb = c.get("/api/audit/verify", headers=A).json()
    ok(vb["ok"] is False and vb["broken_at"] == victim.id, f"edited audit entry #{victim.id} detected")

print(f"\nALL {PASS} CHECKS PASSED")
