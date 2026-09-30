"""Deterministic information extraction: labelled fields, entities, dates, events, similarity.

Works fully offline using regex, date parsing, gazetteers, normalized string comparison and
TF-IDF cosine similarity. No external AI service is required.
"""
import math
import re
from collections import Counter
from datetime import date
from difflib import SequenceMatcher

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

DATE_PATTERNS = [
    ("dmy_text", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s-]+{_MON}\.?,?[\s-]+(\d{{4}})\b", re.I)),
    ("mdy_text", re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)),
    ("iso", re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")),
    ("dmy_num", re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")),
]
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?\b")
AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR|USD|\$|€|EUR)\s?(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", re.I)
ID_RE = re.compile(r"\b(?=[A-Z0-9/-]*\d{3})(?=[A-Z0-9/-]*[A-Z]{2})[A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+)*\b")
HONORIFIC_RE = re.compile(r"\b(?:Mr|Ms|Mrs|Dr|Prof|Shri|Smt|Sri)\.?[ \t]+((?:[A-Z][a-z]+|[A-Z]\.)(?:[ \t]+(?:[A-Z][a-z]+|[A-Z]\.)){0,3})")
ORG_SUFFIX = (r"University|College|Institute(?: of [A-Z][a-z]+)*|School|Board|Council|Authority|Bank|Corporation|"
              r"Company|Department|Ministry|Pvt\.? Ltd\.?|Private Limited|Limited|Ltd\.?|Inc\.?|LLP|LLC|Traders|"
              r"Textiles|Supplies|Enterprises|Industries|Solutions|Technologies|Associates|Agency|Registry")
ORG_RE = re.compile(rf"\b((?:[A-Z][A-Za-z&'.-]+[ \t]+){{1,6}}(?:{ORG_SUFFIX})(?:[ \t]+(?:of[ \t]+)?[A-Z][a-z]+)?)\b")

LOCATIONS = [
    "Coimbatore", "Chennai", "Madurai", "Tiruppur", "Erode", "Salem", "Trichy", "Tiruchirappalli", "Vellore",
    "Ooty", "Pollachi", "Karur", "Namakkal", "Tirunelveli", "Thanjavur", "Kanyakumari", "Hosur", "Nilgiris",
    "Bengaluru", "Bangalore", "Mysuru", "Mysore", "Mangaluru", "Hyderabad", "Kochi", "Cochin",
    "Thiruvananthapuram", "Kozhikode", "Palakkad", "Mumbai", "Pune", "Nagpur", "Delhi", "New Delhi",
    "Noida", "Gurugram", "Kolkata", "Ahmedabad", "Surat", "Jaipur", "Lucknow", "Kanpur", "Bhopal", "Indore",
    "Patna", "Bhubaneswar", "Visakhapatnam", "Vijayawada", "Goa", "Chandigarh", "Puducherry", "Pondicherry",
    "Tamil Nadu", "Kerala", "Karnataka", "Andhra Pradesh", "Telangana", "Maharashtra", "Gujarat", "India",
    "London", "New York", "Singapore", "Dubai", "Sydney", "Toronto", "Paris", "Berlin", "Tokyo",
]
LOC_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(l) for l in LOCATIONS), key=len, reverse=True)) + r")\b")

# canonical fields: (field, entity type, label regex)
FIELD_DEFS = [
    ("subject_name", "PERSON", r"(student'?s? name|name of the (student|candidate|holder)|candidate'?s? name|holder'?s? name|name|awarded to|issued to|student)"),
    ("id_number", "ID", r"(register(ed)? (number|no\.?)|reg\.? ?no\.?|registration (number|no\.?)|enrol?ment (number|no\.?)|roll (number|no\.?)|student id( no\.?)?|id (number|no\.?)|university reg(istration)? no\.?)"),
    ("dob", "DATE", r"(date of birth|d\.?o\.?b\.?|birth date)"),
    ("degree_conferred", "DATE", r"(date of conferral|degree conferred( on)?|conferred on|date of convocation|convocation date|date of award|awarded on)"),
    ("issue_date", "DATE", r"(date of issue|issued on|issue date|date issued)"),
    ("programme", "TEXT", r"(programme|program|degree|course|branch)"),
    ("institution", "ORG", r"(institution|university|college|issuing authority)"),
    ("cgpa", "TEXT", r"(cgpa|gpa|sgpa|overall grade)"),
    ("invoice_no", "DOC_REF", r"(invoice (no\.?|number|#)|inv\.? no\.?|against invoice|invoice ref(erence)?)"),
    ("po_no", "DOC_REF", r"(p\.?o\.? (no\.?|number|#|ref(erence)?)|purchase order (no\.?|number|ref(erence)?)|order (no\.?|number))"),
    ("receipt_no", "DOC_REF", r"(receipt (no\.?|number|#))"),
    ("transaction_id", "ID", r"(transaction (id|ref(erence)?|no\.?)|txn (id|no\.?)|utr( no\.?)?|payment ref(erence)?)"),
    ("invoice_date", "DATE", r"(invoice date|date of invoice)"),
    ("order_date", "DATE", r"(order date|po date|date of order)"),
    ("payment_date", "DATE", r"(payment date|paid on|transaction date|date of payment|value date)"),
    ("receipt_date", "DATE", r"(receipt date|date of receipt|received on)"),
    ("due_date", "DATE", r"(due date|payment due)"),
    ("grand_total", "AMOUNT", r"(grand total|total amount|total payable|net payable|invoice total|order total|total value)"),
    ("amount_paid", "AMOUNT", r"(amount paid|amount received|amount|paid amount|payment amount|sum of)"),
    ("vendor", "ORG", r"(vendor|supplier|seller|beneficiary|payee|beneficiary name|issued by)"),
    ("buyer", "ORG", r"(buyer|bill to|billed to|customer|payer|received from|remitter|ordered by)"),
    ("delivery_location", "LOCATION", r"(ship to|delivery location|deliver to|place of delivery|delivery address|delivery city|shipping address)"),
    ("place", "LOCATION", r"(place|location|city|campus|branch location)"),
    ("tenant", "PERSON", r"(tenant|lessee)"),
    ("landlord", "PERSON", r"(landlord|lessor|owner|property owner)"),
    ("monthly_rent", "AMOUNT", r"(monthly rent|rent amount|rent)"),
    ("property_address", "LOCATION", r"(property address|premises|property)"),
    ("lease_start", "DATE", r"(lease start( date)?|commencement date|lease commences( on)?|start date)"),
    ("certificate_no", "DOC_REF", r"(certificate (no\.?|number|serial)|serial (no\.?|number)|document (no\.?|number)|ref(erence)? (no\.?|number))"),
    ("valid_till", "DATE", r"(valid (till|until|upto|up to)|expiry( date)?|expires( on)?)"),
]
_FIELD_COMPILED = [(f, t, re.compile(r"^\s*" + rx.replace(" ", r"\s*") + r"\s*$", re.I)) for f, t, rx in FIELD_DEFS]

FIELD_LABELS = {
    "subject_name": "Subject name", "id_number": "Registration / ID number", "dob": "Date of birth",
    "degree_conferred": "Degree conferral date", "issue_date": "Issue date", "programme": "Programme",
    "institution": "Institution", "cgpa": "CGPA", "invoice_no": "Invoice number", "po_no": "PO number",
    "receipt_no": "Receipt number", "transaction_id": "Transaction ID", "invoice_date": "Invoice date",
    "order_date": "Order date", "payment_date": "Payment date", "receipt_date": "Receipt date",
    "due_date": "Due date", "grand_total": "Total amount", "amount_paid": "Amount paid / received",
    "vendor": "Vendor / beneficiary", "buyer": "Buyer / payer", "delivery_location": "Delivery location",
    "place": "Place", "tenant": "Tenant", "landlord": "Landlord", "monthly_rent": "Monthly rent",
    "property_address": "Property address", "lease_start": "Lease start date",
    "certificate_no": "Certificate / document number", "valid_till": "Valid till",
}

STOP = set("""a an the and or of to in on for by with at from as is are was were be been this that these those it its
into than then there their them they he she his her we our you your i me my not no yes all any each per via
has have had do does did will shall may can could would should hereby certify certified above below said
page date name number no""".split())


# ------------------------------------------------------------------ normalization
def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def norm_person(s: str) -> str:
    s = re.sub(r"\b(mr|ms|mrs|dr|prof|shri|smt|sri)\b\.?", " ", (s or "").lower())
    return norm_text(s)


def norm_org(s: str) -> str:
    s = norm_text(s)
    s = re.sub(r"\bprivate limited\b", "pvt ltd", s)
    s = re.sub(r"\blimited\b", "ltd", s)
    s = re.sub(r"\bm s\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_id(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def parse_amount(s: str) -> float | None:
    m = re.search(r"(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", s or "")
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", "")), 2)
    except ValueError:
        return None


def fmt_amount(v: float, sample: str = "") -> str:
    cur = "₹" if ("₹" in sample or "rs" in sample.lower() or "inr" in sample.lower() or not sample) else ""
    if "$" in sample or "usd" in sample.lower():
        cur = "$"
    whole, frac = f"{v:.2f}".split(".")
    if cur == "₹" and len(whole) > 3:  # Indian digit grouping
        head, tail = whole[:-3], whole[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        whole = f"{head},{tail}"
    else:
        whole = f"{int(whole):,}"
    return f"{cur}{whole}.{frac}"


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ------------------------------------------------------------------ dates
def _mk(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def find_dates(text: str):
    """Yields (start, end, raw, iso) for each date, without overlaps."""
    spans = []
    for kind, rx in DATE_PATTERNS:
        for m in rx.finditer(text):
            if any(not (m.end() <= s or m.start() >= e) for s, e, *_ in spans):
                continue
            g = m.groups()
            dt = None
            if kind == "dmy_text":
                dt = _mk(g[2], MONTHS[g[1][:3].lower()], g[0])
            elif kind == "mdy_text":
                dt = _mk(g[2], MONTHS[g[0][:3].lower()], g[1])
            elif kind == "iso":
                dt = _mk(g[0], g[1], g[2])
            elif kind == "dmy_num":
                dt = _mk(g[2], g[1], g[0]) or _mk(g[2], g[0], g[1])
            if dt and 1900 <= dt.year <= 2100:
                spans.append((m.start(), m.end(), m.group(0), dt.isoformat()))
    spans.sort()
    return spans


def fmt_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return d.strftime("%d %b %Y")
    except Exception:
        return iso


# ------------------------------------------------------------------ fields
def extract_fields(text: str) -> dict:
    """Parses 'Label: value' lines into canonical fields. First occurrence wins."""
    fields: dict = {}
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for part in re.split(r"\s{3,}|\t|\s\|\s", line):
            m = re.match(r"^\s*([A-Za-z][A-Za-z .'/#()&-]{1,48}?)\s*[:：]\s*(.+?)\s*$", part)
            if not m:
                continue
            label, value = m.group(1).strip(), m.group(2).strip()
            for field, etype, rx in _FIELD_COMPILED:
                if field in fields or not rx.match(label):
                    continue
                parsed = _parse_field_value(etype, value)
                if parsed is None:
                    continue
                fields[field] = {"label": FIELD_LABELS[field], "source_label": label, "raw": parsed[0],
                                 "value": parsed[1], "type": etype, "line": i}
                break
    return fields


def _parse_field_value(etype, value):
    value = value.strip().strip(",;")
    if not value:
        return None
    if etype == "DATE":
        ds = find_dates(value)
        return (ds[0][2], ds[0][3]) if ds else None
    if etype == "AMOUNT":
        v = parse_amount(value)
        return (value, v) if v is not None and v > 0 else None
    if etype in ("ID", "DOC_REF"):
        tok = re.search(r"[A-Za-z0-9][A-Za-z0-9/-]{3,}", value)
        if not tok or not re.search(r"\d", tok.group(0)):
            return None
        return (tok.group(0), norm_id(tok.group(0)))
    if etype == "PERSON":
        v = re.split(r"\s{2,}|,|\(", value)[0].strip()
        if not re.match(r"^[A-Za-z][A-Za-z .'-]{1,60}$", v) or len(v.split()) > 5:
            return None
        return (v, norm_person(v))
    if etype == "ORG":
        v = value.split(",")[0].strip()
        return (v, norm_org(v)) if len(v) > 2 else None
    if etype == "LOCATION":
        m = LOC_RE.search(value)
        v = m.group(1) if m else value.split(",")[-1].strip()
        return (v, norm_text(v)) if v else None
    return (value[:120], norm_text(value))


# ------------------------------------------------------------------ entities
def extract_entities(text: str, fields: dict) -> list[dict]:
    ents: list[dict] = []
    seen: set = set()

    def add(t, value, start=-1, end=-1, conf=0.8, label=None, norm=None):
        value = value.strip()
        if not value:
            return
        n = norm if norm is not None else {
            "PERSON": norm_person, "ORG": norm_org, "ID": norm_id, "DOC_REF": norm_id,
        }.get(t, norm_text)(value)
        if not n or (t, n) in seen:
            return
        seen.add((t, n))
        ents.append({"type": t, "value": value, "norm": n, "start": start, "end": end, "confidence": conf,
                     "label": label})

    def locate(v):
        i = text.find(v)
        return (i, i + len(v)) if i >= 0 else (-1, -1)

    # labelled fields are the highest-confidence source
    for f, info in fields.items():
        t = info["type"]
        if t == "TEXT":
            continue
        if t == "DATE":
            s, e = locate(info["raw"])
            add("DATE", fmt_date(info["value"]), s, e, 0.95, info["label"], norm=info["value"])
        elif t == "AMOUNT":
            s, e = locate(info["raw"])
            add("AMOUNT", fmt_amount(info["value"], info["raw"]), s, e, 0.93, info["label"], norm=f"{info['value']:.2f}")
        else:
            s, e = locate(info["raw"])
            add(t, info["raw"], s, e, 0.93, info["label"])

    for m in HONORIFIC_RE.finditer(text):
        add("PERSON", m.group(1), m.start(1), m.end(1), 0.75, "Honorific")
    for m in PERSON_CTX_RE.finditer(text):
        name = _clean_name(m.group(1))
        if name:
            st = m.start(1)
            add("PERSON", name, st, st + len(name), 0.7, "Sentence context")
    for m in ORG_RE.finditer(text):
        v = re.sub(r"^(The|This|At|From|To|By|Of)\s+", "", m.group(1)).strip()
        if len(v.split()) >= 2:
            add("ORG", v, m.start(1), m.end(1), 0.72)
    for m in LOC_RE.finditer(text):
        add("LOCATION", m.group(1), m.start(), m.end(), 0.8, "Gazetteer")
    for s, e, raw, iso in find_dates(text):
        add("DATE", fmt_date(iso), s, e, 0.85, None, norm=iso)
    for m in AMOUNT_RE.finditer(text):
        v = parse_amount(m.group(0))
        if v:
            add("AMOUNT", fmt_amount(v, m.group(0)), m.start(), m.end(), 0.85, None, norm=f"{v:.2f}")
    for m in ID_RE.finditer(text):
        tok = m.group(0)
        if len(tok) < 5 or re.fullmatch(r"\d+", tok) or re.match(r"^(GST|CGST|SGST|IGST|PAGE|ISO)\d*$", tok):
            continue
        add("ID", tok, m.start(), m.end(), 0.7, "Pattern")
    return ents


# people named in running sentences ("This is to certify that Rahul Kumar has...")
PERSON_CTX_RE = re.compile(
    r"(?i:\b(?:certify that|certified that|conferred (?:up)?on|awarded to|issued to|in (?:the )?favou?r of|signed by|"
    r"received from|paid by|submitted by|prepared by|approved by|verified by|attested by|belonging to|"
    r"name of (?:the )?(?:student|candidate|applicant|employee)|student|candidate|applicant|tenant|landlord|"
    r"employee|holder|accused|complainant|witness|son of|daughter of|wife of|s/o|d/o|w/o))[ \t]+"
    r"(?:(?:Mr|Ms|Mrs|Dr|Prof|Shri|Smt|Sri)\.?[ \t]+)?"
    r"((?:[A-Z][a-z]+|[A-Z]\.)(?:[ \t]+(?:[A-Z][a-z]+|[A-Z]\.)){1,3})")
NON_NAME = set("""university college institute school board bank department ministry company limited ltd pvt private
textiles supplies industrial industries traders enterprises solutions technologies corporation the this that degree
bachelor master engineering science computer arts commerce invoice receipt order payment certificate programme program
course semester has have is was who of and for with in on at by from to as tamil nadu kerala india coimbatore chennai
january february march april may june july august september october november december road street""".split())


def _clean_name(raw: str) -> str | None:
    toks = raw.split()
    out = []
    for t in toks:
        if t.lower().strip(".") in NON_NAME:
            break
        out.append(t)
    if len(out) < 2 or any(LOC_RE.fullmatch(t) for t in out):
        return None
    return " ".join(out)


# ------------------------------------------------------------------ doc type & events
DOC_TYPES = [
    (r"semester.*mark|mark.*semester|grade sheet", "Semester Marksheet"),
    (r"consolidated", "Consolidated Marksheet"),
    (r"transcript", "Academic Transcript"),
    (r"degree certificate|provisional certificate", "Degree Certificate"),
    (r"identity card|student id|id card", "Identity Document"),
    (r"purchase order", "Purchase Order"),
    (r"rent receipt", "Rent Receipt"),
    (r"receipt", "Receipt"),
    (r"tax invoice|invoice", "Invoice"),
    (r"payment (advice|confirmation|record)|transaction (details|receipt)|fund transfer", "Payment Record"),
    (r"lease|rental agreement|tenancy", "Lease Agreement"),
    (r"statement", "Statement"),
    (r"certificate", "Certificate"),
    (r"report", "Report"),
]


def guess_doc_type(filename: str, text: str, kind: str) -> str:
    head = (text[:600] + " " + filename.replace("_", " ").replace("-", " ")).lower()
    for rx, label in DOC_TYPES:
        if re.search(rx, head):
            return label
    return "Image" if kind == "image" else "Document"


EVENT_RULES = [
    (r"date of birth|\bd\.?o\.?b\b|birth", "birth", "Date of birth recorded"),
    (r"conferr|convocation|awarded on|date of award", "conferral", "Degree conferred"),
    (r"invoice date|date of invoice", "invoice", "Invoice issued"),
    (r"order date|po date|date of order", "order", "Purchase order placed"),
    (r"receipt date|date of receipt|received on", "receipt", "Receipt issued"),
    (r"payment date|paid on|transaction date|date of payment|value date", "payment", "Payment recorded"),
    (r"due date|payment due", "due", "Payment due"),
    (r"valid (till|until|upto)|expir", "validity", "Validity ends"),
    (r"lease start|commence", "lease", "Lease commenced"),
    (r"exam|examination|session", "exam", "Examination held"),
    (r"result|published|declared", "result", "Results published"),
    (r"admission|admitted|enrol|joined|batch", "admission", "Enrollment recorded"),
    (r"deliver|dispatch|shipped", "delivery", "Delivery recorded"),
    (r"signed|executed|agreement dated", "signed", "Document signed"),
    (r"date of issue|issued|issue date", "issue", None),
]
# extra verbs recognised anywhere in the sentence around a date
SENTENCE_RULES = EVENT_RULES + [
    (r"submitted|applied|application", "submission", "Application submitted"),
    (r"registered|filed|lodged", "registration", "Registration filed"),
    (r"incident|occurred|happened|accident", "incident", "Incident reported"),
    (r"graduated|completed|completion", "completion", "Completion recorded"),
    (r"\bpaid\b|transferred|remitted", "payment", "Payment recorded"),
    (r"received|acknowledged", "receipt", "Receipt acknowledged"),
]


def _sentence_around(text: str, s: int, e: int) -> str:
    a = max(text.rfind(ch, 0, s) for ch in (".", "\n", ";", "!", "?")) + 1
    ends = [i for i in (text.find(ch, e) for ch in (". ", ".\n", "\n", ";", "!", "?")) if i >= 0]
    b = min(ends) if ends else len(text)
    return text[a:b].strip()


def extract_events(text: str, doc_type: str) -> list[dict]:
    events, seen = [], set()
    lines = text.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    for s, e, raw, iso in find_dates(text):
        li = max(i for i, o in enumerate(offsets) if o <= s)
        line = lines[li]
        prefix = line[: s - offsets[li]].lower()
        ctx = prefix if prefix.strip() else line.lower()
        kind, label, conf = "mention", f"Date referenced in {doc_type}", 0.5
        for rx, k, lbl in EVENT_RULES:
            if re.search(rx, ctx):
                kind, label, conf = k, lbl or f"{doc_type} issued", 0.88
                break
        if kind == "mention" and re.search(r"\bdate\s*[:：]?\s*$", prefix):
            kind, label, conf = "issue", f"{doc_type} dated", 0.72
        if kind == "mention":  # fall back to the whole sentence ("On 10 Sep 2026 the degree was conferred")
            sent = _sentence_around(text, s, e)
            for rx, k, lbl in SENTENCE_RULES:
                if re.search(rx, sent.lower()):
                    kind, label, conf = k, lbl or f"{doc_type} issued", 0.74
                    line = sent
                    break
        tm = TIME_RE.search(line[e - offsets[li]:e - offsets[li] + 20])
        time = None
        if tm:
            h, mi = int(tm.group(1)), int(tm.group(2))
            if tm.group(4):
                h = h % 12 + (12 if tm.group(4).lower() == "pm" else 0)
            if h < 24 and mi < 60:
                time = f"{h:02d}:{mi:02d}"
        key = (iso, kind)
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": iso, "time": time, "kind": kind, "label": label, "snippet": line.strip()[:240],
                       "confidence": conf})
    return events


# ------------------------------------------------------------------ TF-IDF
def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9]{2,}", (text or "").lower()) if t not in STOP]


def tfidf_cosine_matrix(texts: list[str]) -> list[list[float]]:
    docs = [Counter(tokens(t)) for t in texts]
    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.keys())
    vecs = []
    for d in docs:
        total = sum(d.values()) or 1
        v = {w: (c / total) * (math.log((1 + n) / (1 + df[w])) + 1) for w, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        vecs.append({w: x / norm for w, x in v.items()})
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = vecs[i], vecs[j]
            if len(a) > len(b):
                a, b = b, a
            s = sum(x * b.get(w, 0.0) for w, x in a.items())
            mat[i][j] = mat[j][i] = round(s, 4)
    return mat
