# Digital Record Context Verification (DRCV)

**Establishing the Context, Integrity, Chronology & Relationships of Digital Records**

DRCV is an investigation and verification platform. Upload the scattered digital records that belong to one case (PDFs, scans, images, DOCX, TXT), and it secures them, fingerprints them with SHA-256, extracts metadata/text/OCR, detects entities and events, connects related records, rebuilds the timeline, flags potential inconsistencies, routes them to a human reviewer, and produces a downloadable verification report.

> **We surface evidence signals. Humans make the final determination.**
> DRCV never declares a document "genuine" or "fake". It reports *potential inconsistencies* and *integrity information*.

`SCATTERED → EXTRACT → CONNECT → ANALYZE → REVIEW`

---

## Quick start (Windows)

1. Install **Python 3.12** from <https://www.python.org/downloads/> (tick "Add python.exe to PATH").
2. Double-click **`start-windows.bat`**.
3. The first run installs dependencies (a few minutes) and prepares the synthetic demo data (~20 s). Your browser opens at **http://localhost:8000**.
4. Click **Launch Demo**.

macOS / Linux: `./start-mac-linux.sh`

With Docker + PostgreSQL: `docker compose up --build`, then open http://localhost:8000.

The frontend is **pre-built** (`frontend/dist`) and served by the backend, so Node.js is not needed to run the app.

## Demo accounts (synthetic)

| Role | Email | Password | What they can do |
|---|---|---|---|
| Admin | `admin@demo.local` | `Admin@123` | Everything: cases, records, reviews, users, settings, audit export |
| Investigator | `investigator@demo.local` | `Investigator@123` | Create cases, upload records, run analysis, add notes, generate reports |
| Reviewer | `reviewer@demo.local` | `Reviewer@123` | Assigned cases only; resolve / accept / escalate conflicts; reports |
| Viewer | `viewer@demo.local` | `Viewer@123` | Read-only |

RBAC is enforced by the API on every request (403 + an audit entry for denied attempts); the UI also hides actions a role cannot perform.

## Guided demo (for judges)

**Launch Demo** signs in as the demo Admin, opens *Academic Record Verification*, and re-runs the real analysis pipeline live (Securing → Hash → Extract → Connect → Timeline → Consistency → Complete). A 10-step guide then walks through: Open Case → Records → Record → SHA-256 → Extracted Information → Relationship Graph → Timeline → Conflict → Review → Report.

### Synthetic demo data
All people, institutions, companies and identifiers are fictional and labelled **Synthetic Demo Data**. The demo files in `backend/demo_files` are real files that go through the real pipeline:

| Case | Records | Intentional inconsistencies surfaced by the pipeline |
|---|---|---|
| Academic Record Verification | Semester marksheet (PDF), consolidated marksheet (PDF), degree certificate (DOCX), student ID (PNG, OCR), transcript (TXT) | Name variation *Rahul Kumar / Rahul Kumaar*, register number *WGU22CS045 / WGU22CS054*, conferral date *10 Sep / 12 Sep 2026* |
| Invoice Verification | Invoice (PDF), purchase order (DOCX), receipt (scanned PDF, OCR), payment record (JPG with EXIF/GPS, OCR) | Amount *₹1,48,500 / ₹1,45,800*, receipt dated before invoice and payment, delivery location *Erode / Tiruppur* |
| Lease Agreement Verification | Lease + two rent receipts (TXT) | None — shows the "no inconsistencies" state; marked Completed |

Admins can rebuild the demo cases from **Settings → Reset demo**.

## What's new in v1.1

| # | Improvement | Where to see it |
|---|---|---|
| 1 | **Names & events in normal sentences** — "This is to certify that Rahul Kumaar…", "On 11 Sep 2026 the application was submitted…" | Record → Extracted information |
| 3 | **PDF digital signatures** — detected and cryptographically checked offline (pyHanko): intact / changed after signing, signer, time, trust | Record → Integrity (the semester marksheet is signed) |
| 4 | **Suspicious metadata signals** — modified-before-created, future dates, editing software (Photoshop, Canva…), broken signatures; medium/high signals go to the review queue | Degree certificate & payment record in the demo |
| 8 | **Merged timeline events** — the same event stated in several records appears once, listing every source | Case → Timeline ("Stated in 4 records") |
| 9 | **Explainable conflicts** — every conflict shows the rule, the reasons and the exact source line from each record with the value highlighted | Any conflict → "Why was this flagged?" |
| 16 | **PDF report + one-page executive summary** (bundled fonts, ₹ supported) | Reports → PDF / Summary |
| 21 | **Bulk review** — select several conflicts, apply one decision with one reason; each item is audited | Conflict Center / Review Center |
| 24 | **Password self-change & two-factor login** (authenticator app, QR setup); changing a password signs out other sessions; admins can reset 2FA | Settings → Security, Users |
| 28 | **Tamper-evident audit log** — each entry stores the SHA-256 of the previous one; one click verifies the whole chain | Audit Logs → Verify integrity |
| 41 | **Try it with your own file** — no sign-in, analysed in memory, nothing stored, rate-limited | Landing page |

Existing databases from v1.0 are upgraded automatically on start (new columns added, audit chain backfilled). Re-run a case's analysis to add the new evidence and signals to older cases. "Reset demo" (Settings, Admin) also restores the shared demo accounts' passwords and turns their 2FA off.

## Architecture

```
frontend/  React 18 + Vite, React Flow (@xyflow/react) + d3-force graph, hand-built SVG charts,
           canvas background animation (always running; slows for prefers-reduced-motion)
backend/   Python FastAPI + SQLAlchemy
  app/pipeline/extract.py   file validation (extension + size + magic bytes), metadata, text, OCR
  app/pipeline/nlp.py       labelled fields, entities, dates, events, TF-IDF cosine similarity
  app/pipeline/analysis.py  record pipeline, relationships, conflict + chronology checks, statuses
  app/routers/              auth, users, cases, records/upload, analysis, reviews, reports, audit, search…
  app/storage.py            secure file-storage abstraction (opaque keys, never exposed)
  app/seed.py               demo users + synthetic demo cases
```

**Pipeline per upload:** validate → secure storage → SHA-256 → metadata → OCR/text → entities → events → similarity → relationships → timeline → conflicts → review status. Processing runs in a background worker; the UI polls live stage progress.

**No external AI service is required.** Analysis is deterministic: regex, sentence-context rules, date parsing, a location gazetteer, normalized/fuzzy string comparison and TF-IDF cosine similarity. OCR uses RapidOCR (ONNX models bundled in the pip wheel) or Tesseract if installed. PDF signatures are verified with pyHanko (offline, no certificate lookups).

### Database
PostgreSQL is the primary database (`DATABASE_URL=postgresql+psycopg://…`, see `backend/.env.example` and `docker-compose.yml`). If `DATABASE_URL` is not set, a local SQLite file is used so the app runs with zero setup. The test suite passes on both.

### Security
PBKDF2-SHA256 password hashing, optional TOTP two-factor login, signed JWT sessions that are revoked on password change, server-side RBAC on every route, reviewer case-assignment scoping, login throttling, file type + size + signature validation, opaque storage keys, sandboxed file responses, security headers, generic error messages (no stack traces or paths), secrets from environment variables (a random signing key is generated per installation if none is provided), and a complete hash-chained (tamper-evident) audit trail including denied access attempts.

## Tests

```
cd backend
python tests/test_api.py                                              # 95 end-to-end API checks (SQLite)
python tests/test_api.py postgresql+psycopg://user:pass@localhost/db  # same suite on PostgreSQL
node ../e2e/walkthrough.mjs                                           # browser walkthrough (Playwright), fails on console errors
node ../e2e/features_v11.mjs                                          # browser checks for the v1.1 features
```

## Developing the frontend

```
cd frontend && npm install && npm run dev     # http://localhost:5173 (proxies /api to :8000)
npm run build                                 # refresh frontend/dist
```

## Limitations
SHA-256 shows whether stored content changed relative to the recorded hash; it does not prove a document's real-world truth. Metadata can be missing or altered. OCR and extraction can make recognition errors. Relationship signals are probabilistic. Potential inconsistencies may have legitimate explanations. Final determination always rests with a human reviewer.
