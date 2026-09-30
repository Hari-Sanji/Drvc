"""File validation, metadata extraction and text / OCR extraction.

Nothing here fabricates data: if a property cannot be read it is reported as not available.
"""
import io
import logging
import os
import threading
import zipfile
from datetime import datetime, timezone

from .. import config

log = logging.getLogger("drcv.extract")

MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain"}


class ValidationError(Exception):
    pass


# ------------------------------------------------------------------ validation
def validate_file(filename: str, data: bytes, max_bytes: int) -> tuple[str, str, str]:
    """Returns (ext, mime, kind). Checks extension, size and magic bytes (content must match the extension)."""
    name = (filename or "").strip()
    if not name or len(name) > 255:
        raise ValidationError("Invalid file name.")
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in MIME:
        raise ValidationError("Unsupported file type. Allowed: PDF, JPG, JPEG, PNG, DOCX, TXT.")
    if len(data) == 0:
        raise ValidationError("The file is empty.")
    if len(data) > max_bytes:
        raise ValidationError(f"File exceeds the maximum size of {max_bytes // (1024 * 1024)} MB.")
    head = data[:16]
    ok = True
    if ext == ".pdf":
        ok = b"%PDF" in data[:1024]
    elif ext in (".jpg", ".jpeg"):
        ok = head.startswith(b"\xff\xd8\xff")
    elif ext == ".png":
        ok = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext == ".docx":
        ok = head.startswith(b"PK")
        if ok:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    ok = "word/document.xml" in z.namelist()
            except zipfile.BadZipFile:
                ok = False
    elif ext == ".txt":
        ok = b"\x00" not in data[:4096]
    if not ok:
        raise ValidationError("File content does not match its extension. Please verify the file type and try again.")
    kind = "image" if ext in (".jpg", ".jpeg", ".png") else "document"
    return ext, MIME[ext], kind


# ------------------------------------------------------------------ metadata
EXPECTED = [("created", "Created date"), ("modified", "Modified date"), ("author", "Author / creator"),
            ("software", "Producing software"), ("device", "Device information"), ("location", "Location (GPS)")]


def _pdf_date(v):
    if not v:
        return None
    s = str(v)
    if s.startswith("D:"):
        s = s[2:]
    try:
        return datetime.strptime(s[:14], "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        try:
            return datetime.strptime(s[:8], "%Y%m%d").date().isoformat()
        except ValueError:
            return s


def _gps_to_deg(vals, ref):
    try:
        d, m, s = [float(x) for x in vals]
        deg = d + m / 60 + s / 3600
        return -deg if ref in ("S", "W") else deg
    except Exception:
        return None


def extract_metadata(ext: str, data: bytes) -> dict:
    items: list[dict] = []
    found: set[str] = set()
    notes: list[str] = []

    def add(key, label, value, group="File"):
        if value is None or value == "":
            return
        items.append({"key": key, "label": label, "value": str(value), "group": group})
        found.add(key)

    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(data))
            add("pages", "Page count", len(r.pages), "Document")
            add("encrypted", "Encrypted", "Yes" if r.is_encrypted else "No", "Document")
            try:
                box = r.pages[0].mediabox
                add("page_size", "Page size (pt)", f"{float(box.width):.0f} × {float(box.height):.0f}", "Document")
            except Exception:
                pass
            md = r.metadata or {}
            add("title", "Title", md.get("/Title"), "Document")
            add("author", "Author", md.get("/Author"), "Authoring")
            add("software", "Creator application", md.get("/Creator"), "Authoring")
            add("producer", "PDF producer", md.get("/Producer"), "Authoring")
            add("created", "Created date", _pdf_date(md.get("/CreationDate")), "Dates")
            add("modified", "Modified date", _pdf_date(md.get("/ModDate")), "Dates")
            if md.get("/CreationDate") and md.get("/ModDate") and md.get("/CreationDate") != md.get("/ModDate"):
                notes.append("Embedded modified date differs from created date (may indicate the file was re-saved).")
        elif ext == ".docx":
            import docx
            d = docx.Document(io.BytesIO(data))
            cp = d.core_properties
            add("title", "Title", cp.title, "Document")
            add("author", "Author", cp.author, "Authoring")
            add("last_modified_by", "Last modified by", cp.last_modified_by, "Authoring")
            add("created", "Created date", cp.created.isoformat() if cp.created else None, "Dates")
            add("modified", "Modified date", cp.modified.isoformat() if cp.modified else None, "Dates")
            add("revision", "Revision", cp.revision, "Document")
            add("paragraphs", "Paragraph count", len(d.paragraphs), "Document")
            add("tables", "Table count", len(d.tables), "Document")
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    if "docProps/app.xml" in z.namelist():
                        import re
                        app = z.read("docProps/app.xml").decode("utf-8", "ignore")
                        m = re.search(r"<Application>(.*?)</Application>", app)
                        add("software", "Application", m.group(1) if m else None, "Authoring")
            except Exception:
                pass
        elif ext in (".jpg", ".jpeg", ".png"):
            from PIL import ExifTags, Image
            im = Image.open(io.BytesIO(data))
            add("dimensions", "Dimensions (px)", f"{im.width} × {im.height}", "Image")
            add("format", "Image format", im.format, "Image")
            add("color_mode", "Color mode", im.mode, "Image")
            dpi = im.info.get("dpi")
            if dpi:
                add("dpi", "Resolution (DPI)", f"{round(float(dpi[0]))} × {round(float(dpi[1]))}", "Image")
            for k in ("Software", "Author", "Creation Time", "Description", "Comment"):
                if im.info.get(k):
                    add(k.lower().replace(" ", "_"), f"PNG text: {k}", im.info.get(k), "Embedded text")
                    if k == "Software":
                        found.add("software")
                    if k == "Creation Time":
                        found.add("created")
            exif = im.getexif()
            if exif:
                tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                try:
                    tags.update({ExifTags.TAGS.get(k, k): v for k, v in exif.get_ifd(0x8769).items()})
                except Exception:
                    pass
                make, model = tags.get("Make"), tags.get("Model")
                if make or model:
                    add("device", "Camera / device", " ".join(str(x).strip() for x in (make, model) if x), "Device")
                add("software", "Software", tags.get("Software"), "Authoring")
                add("created", "Captured (EXIF)", tags.get("DateTimeOriginal") or tags.get("DateTime"), "Dates")
                add("orientation", "Orientation", tags.get("Orientation"), "Image")
                try:
                    gps = exif.get_ifd(0x8825)
                    if gps and 2 in gps and 4 in gps:
                        lat = _gps_to_deg(gps[2], gps.get(1))
                        lon = _gps_to_deg(gps[4], gps.get(3))
                        if lat is not None and lon is not None:
                            add("location", "GPS coordinates", f"{lat:.5f}, {lon:.5f}", "Location")
                except Exception:
                    pass
            else:
                notes.append("No EXIF block present (common for screenshots, scans and exported images).")
        elif ext == ".txt":
            enc = "UTF-8"
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                enc = "Latin-1 (fallback)"
            txt = data.decode("utf-8", "replace")
            add("encoding", "Text encoding", enc, "Document")
            add("lines", "Line count", txt.count("\n") + 1, "Document")
            add("characters", "Character count", len(txt), "Document")
            notes.append("Plain-text files carry no embedded authoring metadata.")
    except Exception as e:  # corrupted metadata should never stop the pipeline
        log.warning("metadata extraction failed: %s", e)
        notes.append("Some metadata could not be read from this file.")

    signatures = extract_signatures(data) if ext == ".pdf" else []
    for sg in signatures:
        state = {True: "intact", False: "CHANGED after signing", None: "not cryptographically checked"}[sg["intact"]]
        add(f"signature_{sg['field']}", "Digital signature", f"{sg['signer'] or 'Unknown signer'} — {state}", "Signature")
    if ext == ".pdf" and not signatures:
        notes.append("No digital signature is embedded in this PDF.")
    missing = [label for key, label in EXPECTED if key not in found]
    return {"available": items, "not_available": missing, "notes": notes, "signatures": signatures}


# ------------------------------------------------------------------ digital signatures
def extract_signatures(data: bytes) -> list[dict]:
    """Finds PDF signatures. With pyHanko installed, the cryptographic integrity of the signed bytes is
    verified offline (no certificate trust lookups). Without it, only presence and declared details are read."""
    out = []
    try:
        import logging as _lg
        _lg.getLogger("pyhanko").setLevel(_lg.CRITICAL)
        _lg.getLogger("pyhanko_certvalidator").setLevel(_lg.CRITICAL)
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko_certvalidator import ValidationContext
        r = PdfFileReader(io.BytesIO(data), strict=False)
        for sig in r.embedded_signatures:
            item = {"field": sig.field_name, "signer": None, "organization": None, "signed_at": None,
                    "reason": None, "location": None, "intact": None, "trusted": False, "coverage": None,
                    "method": "pyHanko cryptographic check (offline)"}
            try:
                subj = sig.signer_cert.subject.native
                item["signer"] = subj.get("common_name")
                item["organization"] = subj.get("organization_name")
            except Exception:
                pass
            try:
                ts = sig.self_reported_timestamp
                item["signed_at"] = ts.isoformat() if ts else None
            except Exception:
                pass
            v = sig.sig_object
            item["reason"] = str(v.get("/Reason")) if v.get("/Reason") else None
            item["location"] = str(v.get("/Location")) if v.get("/Location") else None
            try:
                # pyHanko runs its own asyncio loop; use a fresh thread so it also works inside the server's loop
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=1) as ex:
                    st = ex.submit(validate_pdf_signature, sig, ValidationContext(allow_fetching=False)).result(timeout=60)
                item["intact"] = bool(st.intact and st.valid)
                item["trusted"] = bool(st.trusted)
                item["coverage"] = str(st.coverage).split(".")[-1].replace("_", " ").lower()
            except Exception as e:  # an error in checking is NOT evidence of tampering
                log.info("signature validation could not complete: %s", e)
                item["intact"] = None
                item["method"] = "Signature found; cryptographic check could not complete"
            out.append(item)
        return out
    except ImportError:
        pass
    except Exception as e:
        log.info("pyHanko could not read signatures: %s", e)
    try:  # presence-only fallback
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        for name, f in (r.get_fields() or {}).items():
            if f.get("/FT") == "/Sig" and f.get("/V"):
                v = f["/V"].get_object()
                out.append({"field": name, "signer": str(v.get("/Name")) if v.get("/Name") else None, "organization": None,
                            "signed_at": _pdf_date(v.get("/M")), "reason": str(v.get("/Reason")) if v.get("/Reason") else None,
                            "location": str(v.get("/Location")) if v.get("/Location") else None, "intact": None,
                            "trusted": False, "coverage": None, "method": "Presence only (install pyHanko to verify)"})
    except Exception:
        pass
    return out


# ------------------------------------------------------------------ metadata anomaly signals
EDITING_SOFTWARE = ["photoshop", "gimp", "canva", "pixlr", "paint.net", "affinity photo", "snapseed", "picsart",
                    "ilovepdf", "smallpdf", "sejda", "pdfescape", "pdf editor", "phantompdf", "pdfelement", "lightroom"]


def _parse_any_date(v):
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y:%m:%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s[:25] if "%z" in fmt else s[:19], fmt)
            return d.replace(tzinfo=None) if d.tzinfo is None else d.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(s)
        return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


def metadata_flags(meta: dict, fields: dict, uploaded_at=None) -> list[dict]:
    """Signals worth a human look. Absence of metadata is never treated as suspicious."""
    vals = {m["key"]: m["value"] for m in meta.get("available", [])}
    flags = []
    created, modified = _parse_any_date(vals.get("created")), _parse_any_date(vals.get("modified"))
    if created and modified and (created - modified).total_seconds() > 60:
        flags.append({"code": "modified_before_created", "severity": "high",
                      "title": "Modified date is earlier than created date",
                      "detail": "The embedded modified date precedes the created date, which does not happen in a normal "
                                "save sequence. It can result from a clock error, a conversion tool, or manual editing of metadata.",
                      "value_a": f"Created: {created:%d %b %Y %H:%M}", "value_b": f"Modified: {modified:%d %b %Y %H:%M}"})
    now = datetime.utcnow()
    for key, dt in (("created", created), ("modified", modified)):
        if dt and (dt - now).days >= 1:
            flags.append({"code": f"{key}_in_future", "severity": "medium", "title": f"{key.title()} date is in the future",
                          "detail": "An embedded date lies after the time the record was analysed.",
                          "value_a": f"{key.title()}: {dt:%d %b %Y}", "value_b": f"Analysed: {now:%d %b %Y}"})
    soft = " ".join(str(vals.get(k, "")) for k in ("software", "producer", "last_modified_by")).lower()
    hit = next((s for s in EDITING_SOFTWARE if s in soft), None)
    if hit:
        tool = next(str(vals[k]) for k in ("software", "producer", "last_modified_by") if hit in str(vals.get(k, "")).lower())
        flags.append({"code": "editing_software", "severity": "medium", "title": "Editing software recorded in metadata",
                      "detail": f"The file's metadata names an image/PDF editing tool ({tool}). Editing is often legitimate "
                                "(cropping, compressing), but the content should be compared with an original.",
                      "value_a": f"Software: {tool}", "value_b": "Expected: capture / issuing system"})
    for sg in meta.get("signatures", []):
        if sg.get("intact") is False:
            flags.append({"code": f"signature_broken_{sg['field']}", "severity": "high",
                          "title": "Signed content changed after signing",
                          "detail": "The cryptographic check shows the signed bytes no longer match the signature. The document "
                                    "may have been altered after it was signed.",
                          "value_a": f"Signature: {sg.get('signer') or sg['field']}", "value_b": "Signed bytes: modified"})
    issue = (fields or {}).get("issue_date", {}).get("value")
    if created and issue:
        try:
            gap = (datetime.fromisoformat(issue) - created).days
            if gap > 30:
                flags.append({"code": "created_long_before_issue", "severity": "low",
                              "title": "File created well before its stated issue date",
                              "detail": f"The file was created {gap} days before the issue date written in the document.",
                              "value_a": f"File created: {created:%d %b %Y}", "value_b": f"Stated issue date: {issue}"})
        except ValueError:
            pass
    return flags


# ------------------------------------------------------------------ OCR
_ocr_lock = threading.Lock()
_ocr_engine = None
_ocr_name = None


def ocr_engine_name() -> str | None:
    _load_ocr()
    return _ocr_name


def _limit_onnx_memory():
    """Keep ONNX Runtime's memory use small (matters on 512 MB hosts): no arena / memory-pattern caching."""
    try:
        import onnxruntime as ort
        if getattr(ort, "_drcv_patched", False):
            return
        orig = ort.InferenceSession

        class _Lean(orig):
            def __init__(self, path_or_bytes, sess_options=None, *a, **k):
                if sess_options is None:
                    sess_options = ort.SessionOptions()
                sess_options.enable_cpu_mem_arena = False
                sess_options.enable_mem_pattern = False
                super().__init__(path_or_bytes, sess_options, *a, **k)
        ort.InferenceSession = _Lean
        ort._drcv_patched = True
    except Exception as e:  # pragma: no cover
        log.info("Could not limit ONNX memory: %s", e)


def _load_ocr():
    global _ocr_engine, _ocr_name
    if _ocr_name is not None:
        return
    try:
        _limit_onnx_memory()
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        _ocr_name = "RapidOCR (ONNX)"
        return
    except Exception as e:
        log.info("rapidocr_onnxruntime unavailable: %s", e)
    try:  # rapidocr v3 (supports Python 3.13+)
        from rapidocr import RapidOCR as RapidOCR3
        _ocr_engine = ("v3", RapidOCR3())
        _ocr_name = "RapidOCR v3 (ONNX)"
        return
    except Exception as e:
        log.info("rapidocr v3 unavailable: %s", e)
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _ocr_engine = "tesseract"
        _ocr_name = "Tesseract"
        return
    except Exception as e:
        log.info("Tesseract unavailable: %s", e)
    _ocr_name = ""


def _group_lines(boxes):
    """boxes: list of (x, y_center, height, text, score) -> ordered lines of text."""
    boxes.sort(key=lambda b: (b[1], b[0]))
    lines: list[list] = []
    for b in boxes:
        if lines and abs(lines[-1][0][1] - b[1]) < max(8, 0.55 * b[2]):
            lines[-1].append(b)
        else:
            lines.append([b])
    out = []
    for ln in lines:
        ln.sort(key=lambda b: b[0])
        out.append(" ".join(b[3] for b in ln))
    return out


def clean_ocr_text(text: str) -> str:
    """Normalizes common OCR spacing artefacts (merged words, glued labels/values, stray glyphs)."""
    import re
    text = re.sub(r"[\u2E80-\u9FFF\uAC00-\uD7AF\u3000-\u303F]", "", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)                   # RahulKumar -> Rahul Kumar
    text = re.sub(r"(?<=[A-Za-z]):(?=\S)", ": ", text)                 # Name:Rahul -> Name: Rahul
    text = re.sub(r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})(?=\d{1,2}:\d{2})", r"\1 ", text)  # date+time glued
    text = re.sub(r"(?<=\d)(?=[A-Z][a-z])", " ", text)                 # 31Jul -> 31 Jul
    text = re.sub(r"(?<=Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?=\d{4}\b)", " ", text)              # Jul2026 -> Jul 2026
    text = re.sub(r"[ \t]{2,}", " ", text)
    return "\n".join(l.strip() for l in text.split("\n"))


def ocr_image(img) -> tuple[str, float | None]:
    """Run OCR on a PIL image. Returns (text, confidence 0-100)."""
    _load_ocr()
    if not _ocr_name:
        raise RuntimeError("No OCR engine installed")
    img = img.convert("RGB")
    cap = int(os.getenv("DRCV_OCR_MAX_SIDE", "0") or 0)   # e.g. 1000 on small hosts
    if cap and max(img.size) > cap:
        k = cap / max(img.size)
        img = img.resize((int(img.width * k), int(img.height * k)))
    if not cap and max(img.size) < 1000:
        scale = 1000 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    with _ocr_lock:
        if _ocr_engine == "tesseract":
            import pytesseract
            d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            boxes, confs = [], []
            for i, t in enumerate(d["text"]):
                if t.strip() and float(d["conf"][i]) >= 0:
                    boxes.append((d["left"][i], d["top"][i] + d["height"][i] / 2, d["height"][i], t, float(d["conf"][i])))
                    confs.append(float(d["conf"][i]))
            text = clean_ocr_text("\n".join(_group_lines(boxes)))
            return text, (sum(confs) / len(confs)) if confs else None
        import numpy as np
        if isinstance(_ocr_engine, tuple):
            out = _ocr_engine[1](np.array(img))
            if out is None or out.boxes is None or not len(out.txts):
                return "", None
            result = [(b.tolist(), t, s) for b, t, s in zip(out.boxes, out.txts, out.scores)]
        else:
            result, _ = _ocr_engine(np.array(img))
        if not result:
            return "", None
        boxes = []
        for box, text, score in result:
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            boxes.append((min(xs), (min(ys) + max(ys)) / 2, max(ys) - min(ys), text, float(score)))
        text = clean_ocr_text("\n".join(_group_lines(boxes)))
        conf = sum(b[4] for b in boxes) / len(boxes) * 100
        return text, conf


# ------------------------------------------------------------------ text
_DEMO_OCR_FILE = config.DEMO_FILES_DIR / "ocr_cache.json"
_demo_ocr_cache = None


def _demo_ocr_lookup(data: bytes):
    """The bundled synthetic demo scans were OCR'd once with the same engine; identical bytes reuse that result.
    This keeps first start-up light on small (512 MB) hosts. Any other file goes through the real OCR engine."""
    global _demo_ocr_cache
    if _demo_ocr_cache is None:
        try:
            import json
            _demo_ocr_cache = json.loads(_DEMO_OCR_FILE.read_text(encoding="utf-8")) if _DEMO_OCR_FILE.exists() else {}
        except Exception:
            _demo_ocr_cache = {}
    if not _demo_ocr_cache:
        return None
    import hashlib
    return _demo_ocr_cache.get(hashlib.sha256(data).hexdigest())


def extract_text(ext: str, data: bytes, ocr_enabled: bool = True) -> dict:
    """Returns {text, method, confidence, error, pages}."""
    out = {"text": "", "method": "none", "confidence": None, "error": None}
    cached = _demo_ocr_lookup(data) if ext in (".pdf", ".jpg", ".jpeg", ".png") and ocr_enabled else None
    if cached:
        return dict(cached)
    try:
        if ext == ".txt":
            try:
                out["text"] = data.decode("utf-8")
            except UnicodeDecodeError:
                out["text"] = data.decode("latin-1")
            out["method"] = "Plain text"
        elif ext == ".docx":
            import docx
            d = docx.Document(io.BytesIO(data))
            parts = [p.text for p in d.paragraphs if p.text.strip()]
            for t in d.tables:
                for row in t.rows:
                    cells = [c.text.strip() for c in row.cells]
                    # de-duplicate merged cells
                    uniq = []
                    for c in cells:
                        if c and (not uniq or uniq[-1] != c):
                            uniq.append(c)
                    if uniq:
                        parts.append(": ".join(uniq) if len(uniq) == 2 else " | ".join(uniq))
            out["text"] = "\n".join(parts)
            out["method"] = "DOCX text layer"
        elif ext == ".pdf":
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in r.pages)
            if len(text.strip()) >= 25:
                out["text"] = text
                out["method"] = "PDF text layer"
            else:
                if not ocr_enabled:
                    out["error"] = "This PDF has no text layer and OCR is disabled in settings."
                    return out
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(data)
                texts, confs = [], []
                for i in range(min(len(pdf), 10)):
                    img = pdf[i].render(scale=2.2).to_pil()
                    t, c = ocr_image(img)
                    texts.append(t)
                    if c is not None:
                        confs.append(c)
                out["text"] = "\n".join(texts)
                out["method"] = f"OCR ({_ocr_name}) on scanned PDF"
                out["confidence"] = round(sum(confs) / len(confs), 1) if confs else None
        elif ext in (".jpg", ".jpeg", ".png"):
            if not ocr_enabled:
                out["error"] = "OCR is disabled in system settings."
                return out
            from PIL import Image
            t, c = ocr_image(Image.open(io.BytesIO(data)))
            out["text"] = t
            out["method"] = f"OCR ({_ocr_name})"
            out["confidence"] = round(c, 1) if c is not None else None
    except Exception as e:
        log.warning("text extraction failed: %s", e)
        out["error"] = ("Text extraction could not be completed. The original record is still available "
                        "for manual review.")
    out["text"] = (out["text"] or "").replace("\r\n", "\n").replace("\x00", "")
    return out
