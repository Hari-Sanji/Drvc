"""Public 'try it with your own file' analysis. Nothing is stored: no database rows, no files on disk."""
import hashlib
import threading
import time

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..pipeline import nlp
from ..pipeline.extract import ValidationError, extract_metadata, extract_text, metadata_flags, validate_file

router = APIRouter(prefix="/api/public", tags=["Public demo"])
MAX_BYTES = 5 * 1024 * 1024
_lock = threading.Lock()
_hits: dict[str, list[float]] = {}
LIMIT, WINDOW = 6, 60


def _rate_limit(ip: str):
    now = time.time()
    with _lock:
        recent = [t for t in _hits.get(ip, []) if now - t < WINDOW]
        if len(recent) >= LIMIT:
            raise HTTPException(429, "Too many tries in a minute. Please wait a moment and try again.")
        recent.append(now)
        _hits[ip] = recent


@router.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...)):
    _rate_limit(request.client.host if request.client else "unknown")
    data = await file.read(MAX_BYTES + 1)
    name = (file.filename or "").replace("\\", "/").split("/")[-1][:255]
    try:
        ext, mime, kind = validate_file(name, data, MAX_BYTES)
    except ValidationError as e:
        raise HTTPException(422, str(e).replace("20 MB", "5 MB"))
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(_run, name, ext, mime, kind, data)


def _run(name, ext, mime, kind, data):
    timings = {}
    t = time.time()
    sha = hashlib.sha256(data).hexdigest()
    timings["hash"] = time.time() - t
    t = time.time()
    meta = extract_metadata(ext, data)
    timings["metadata"] = time.time() - t
    t = time.time()
    tx = extract_text(ext, data, True)
    timings["text"] = time.time() - t
    text = tx["text"] or ""
    fields = nlp.extract_fields(text)
    ents = nlp.extract_entities(text, fields)
    doc_type = nlp.guess_doc_type(name, text, kind)
    events = nlp.extract_events(text, doc_type)
    flags = metadata_flags(meta, fields)
    return {
        "stored": False,
        "file": {"name": name, "type": ext[1:].upper(), "mime": mime, "size": len(data), "doc_type": doc_type},
        "sha256": sha,
        "metadata": {"available": meta["available"], "not_available": meta["not_available"], "notes": meta["notes"]},
        "signatures": meta.get("signatures", []),
        "flags": flags,
        "text": {"method": tx["method"], "confidence": tx["confidence"], "error": tx["error"],
                 "excerpt": text[:1500], "length": len(text)},
        "fields": [{"label": f["label"], "value": f["raw"]} for f in fields.values()],
        "entities": [{"type": e["type"], "value": e["value"]} for e in ents][:60],
        "events": [{"date": e["date"], "date_label": nlp.fmt_date(e["date"]), "label": e["label"]} for e in events],
        "timings_ms": {k: round(v * 1000) for k, v in timings.items()},
    }
