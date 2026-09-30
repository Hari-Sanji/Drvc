"""PDF rendering of verification reports (full report and one-page executive summary).

Built with fpdf2 and bundled DejaVu fonts (so ₹, arrows and quotes render on any machine).
Both PDFs are rendered from the stored report snapshot, so they match the HTML report exactly.
"""
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
INK = (28, 23, 20)
MUTED = (110, 100, 92)
COPPER = (184, 92, 46)
BAND = (26, 21, 18)
SOFT = (248, 241, 234)
LINE = (230, 220, 210)
RED = (190, 18, 60)
AMBER = (180, 83, 9)
GREEN = (4, 120, 87)
STATUS_COL = {"Requires Review": AMBER, "Escalated": RED, "Resolved": GREEN, "Accepted": GREEN, "Reviewed": GREEN}


def _d(s):
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).strftime("%d %b %Y %H:%M UTC")
    except ValueError:
        return str(s)


def _day(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return str(iso or "—")


class ReportPDF(FPDF):
    def __init__(self, data: dict, title: str):
        super().__init__(format="A4")
        self.data, self.title_text = data, title
        self.add_font("DV", "", str(FONTS / "DejaVuSans.ttf"))
        self.add_font("DV", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
        self.add_font("DVM", "", str(FONTS / "DejaVuSansMono.ttf"))
        self.set_auto_page_break(True, margin=18)
        self.set_margins(16, 16, 16)
        self.alias_nb_pages()
        self.set_title(title)
        self.set_author(data.get("organization") or "DRCV")
        self.set_creator("Digital Record Context Verification")

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("DV", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"{self.title_text} · {self.data['case']['code']}", align="L")
        self.ln(7)

    def footer(self):
        self.set_y(-12)
        self.set_font("DV", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 5, "We surface evidence signals. Humans make the final determination.", align="L")
        self.cell(0, 5, f"Page {self.page_no()} / {{nb}}", align="R")

    # -- building blocks
    def cover(self, subtitle: str):
        self.add_page()
        self.set_fill_color(*BAND)
        self.rect(0, 0, 210, 44, "F")
        self.set_fill_color(*COPPER)
        self.rect(0, 44, 210, 1.4, "F")
        self.set_xy(16, 10)
        self.set_text_color(232, 168, 107)
        self.set_font("DV", "B", 8)
        self.cell(0, 5, subtitle.upper() + " · " + (self.data.get("organization") or ""))
        self.set_xy(16, 17)
        self.set_text_color(245, 238, 233)
        self.set_font("DV", "B", 18)
        self.cell(0, 9, self.data["case"]["name"])
        self.set_xy(16, 28)
        self.set_font("DV", "", 9)
        self.set_text_color(210, 200, 190)
        gb = self.data.get("generated_by", {})
        self.cell(0, 5, f"{self.data['case']['code']} · Generated {_d(self.data.get('generated_at'))} by {gb.get('name', '')}")
        self.set_xy(16, 35)
        self.set_font("DV", "B", 7)
        self.set_text_color(232, 168, 107)
        self.cell(0, 5, "SCATTERED → EXTRACT → CONNECT → ANALYZE → REVIEW")
        self.set_y(52)
        if self.data.get("synthetic_demo_data"):
            self.set_font("DV", "B", 7.5)
            self.set_text_color(190, 24, 93)
            self.cell(0, 5, "SYNTHETIC DEMO DATA — all people, organisations and identifiers are fictional")
            self.ln(7)
        self.disclaimer()

    def disclaimer(self):
        self.set_fill_color(255, 247, 230)
        self.set_draw_color(224, 161, 6)
        self.set_text_color(107, 74, 0)
        self.set_font("DV", "B", 8.5)
        self.multi_cell(0, 5, "⚠ " + self.data.get("disclaimer", ""), border=1, fill=True, padding=3, align="L")
        self.ln(4)

    def h2(self, text):
        if self.get_y() > 250:
            self.add_page()
        self.ln(2)
        self.set_text_color(*COPPER)
        self.set_font("DV", "B", 12)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*LINE)
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(3)
        self.set_text_color(*INK)

    def para(self, text, size=9, color=INK, bold=False):
        self.set_font("DV", "B" if bold else "", size)
        self.set_text_color(*color)
        self.multi_cell(0, 4.8, text, new_x="LMARGIN", new_y="NEXT", align="L")

    def kv(self, rows, w1=48):
        self.set_font("DV", "", 8.5)
        self.set_text_color(*INK)
        self.set_draw_color(*LINE)
        head = FontFace(emphasis="BOLD", color=MUTED, fill_color=SOFT)
        with self.table(col_widths=(w1, 178 - w1), first_row_as_headings=False, line_height=5.2,
                        borders_layout="HORIZONTAL_LINES", text_align="LEFT") as t:
            for k, v in rows:
                r = t.row()
                r.cell(str(k), style=head)
                r.cell(str(v if v not in (None, "") else "—"))
        self.ln(2)

    def grid(self, head, rows, widths, mono_cols=()):
        self.set_font("DV", "", 8)
        self.set_draw_color(*LINE)
        hs = FontFace(emphasis="BOLD", color=(90, 46, 23), fill_color=SOFT)
        with self.table(col_widths=widths, headings_style=hs, line_height=4.8, borders_layout="HORIZONTAL_LINES",
                        text_align="LEFT") as t:
            r = t.row()
            for h in head:
                r.cell(h)
            for row in rows:
                r = t.row()
                for i, v in enumerate(row):
                    if i in mono_cols:
                        r.cell(str(v), style=FontFace(family="DVM", size_pt=6.5))
                    else:
                        r.cell(str(v if v not in (None, "") else "—"))
        self.set_font("DV", "", 9)
        self.ln(2)

    def stats(self, items):
        w = 178 / len(items)
        y = self.get_y()
        for i, (n, label) in enumerate(items):
            x = 16 + i * w
            self.set_fill_color(*SOFT)
            self.set_draw_color(*LINE)
            self.rect(x + 1, y, w - 2, 17, "DF")
            self.set_xy(x + 4, y + 2)
            self.set_font("DV", "B", 14)
            self.set_text_color(*COPPER)
            self.cell(w - 8, 7, str(n))
            self.set_xy(x + 4, y + 9.5)
            self.set_font("DV", "", 7.5)
            self.set_text_color(*MUTED)
            self.cell(w - 8, 5, label)
        self.set_y(y + 21)
        self.set_text_color(*INK)

    def conflict(self, c, compact=False):
        if self.get_y() > (262 if compact else 240):
            self.add_page()
        col = STATUS_COL.get(c.get("status"), AMBER)
        y0 = self.get_y()
        self.set_x(20)
        self.set_font("DV", "B", 9.5)
        self.set_text_color(*INK)
        self.cell(120, 5.5, f"{c['type']} · {c['field']}")
        self.set_font("DV", "B", 7.5)
        self.set_text_color(*col)
        self.cell(0, 5.5, c.get("status", "").upper(), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_font("DV", "", 8.5)
        self.set_text_color(*INK)
        self.set_x(20)
        self.multi_cell(170, 4.6, f"A · {c['record_a']}:  {c['value_a']}\nB · {c['record_b']}:  {c['value_b']}",
                        new_x="LMARGIN", new_y="NEXT")
        if not compact:
            self.set_x(20)
            self.set_text_color(*MUTED)
            self.set_font("DV", "", 8)
            self.multi_cell(170, 4.3, c.get("explanation", ""), new_x="LMARGIN", new_y="NEXT")
            ev = c.get("evidence") or {}
            quotes = [q for q in (ev.get("a"), ev.get("b")) if q and q.get("quote")]
            if quotes:
                self.set_x(20)
                self.set_font("DVM", "", 7)
                self.set_text_color(90, 46, 23)
                self.multi_cell(170, 4, "\n".join(f"“{q['quote']}”" for q in quotes), new_x="LMARGIN", new_y="NEXT")
            for reason in (ev.get("reasons") or [])[:4]:
                self.set_x(20)
                self.set_font("DV", "", 7.5)
                self.set_text_color(*MUTED)
                self.multi_cell(170, 4, "• " + reason, new_x="LMARGIN", new_y="NEXT")
        y1 = self.get_y() + 1
        self.set_fill_color(*col)
        self.rect(16, y0, 1.6, y1 - y0, "F")
        self.set_y(y1 + 2.5)
        self.set_text_color(*INK)


def _open(c):
    return c.get("status") in ("Requires Review", "Escalated")


def build_full_pdf(d: dict, report_sha: str) -> bytes:
    pdf = ReportPDF(d, "Contextual Verification Report")
    pdf.cover("Contextual Verification Report")
    c = d["case"]
    confs = d.get("conflicts", [])
    pdf.h2("1. Case details")
    pdf.kv([("Case ID", c.get("code")), ("Case name", c.get("name")), ("Description", c.get("description")),
            ("Category", c.get("category")), ("Status", c.get("status_label")), ("Owner", c.get("owner")),
            ("Created", _d(c.get("created_at"))), ("Review status", c.get("review_status"))])
    pdf.stats([(len(d.get("records", [])), "Records"), (sum(1 for r in d.get("records", []) if r.get("sha256")), "SHA-256 fingerprints"),
               (len(d.get("relationships", [])), "Relationship signals"), (len(confs), f"Potential inconsistencies ({sum(1 for x in confs if _open(x))} open)")])

    pdf.h2("2. Records & integrity fingerprints")
    pdf.grid(["#", "File", "Type", "Size", "SHA-256", "Status"],
             [[r["id"], f"{r['filename']}\n{r.get('document_type', '')}", r.get("type"), f"{r.get('size', 0):,} B", r.get("sha256") or "—",
               r.get("status")] for r in d.get("records", [])], (8, 50, 12, 18, 66, 24), mono_cols=(4,))
    pdf.para("SHA-256 provides a content fingerprint and helps identify changes to file content relative to the recorded "
             "hash. It does not prove the real-world truth of a document.", 8, MUTED)

    pdf.h2("3. Metadata, signatures & extracted information")
    for r in d.get("records", []):
        md = r.get("metadata") or {}
        pdf.para(f"{r['filename']}  ·  {r.get('text_method')}"
                 + (f"  ·  OCR confidence {r['ocr_confidence']:.0f}%" if r.get("ocr_confidence") is not None else ""), 9.5, INK, True)
        rows = [(m["label"], m["value"]) for m in md.get("available", [])]
        rows += [(f.get("label"), f.get("value")) for f in (r.get("extracted_fields") or {}).values()]
        if rows:
            pdf.kv(rows)
        else:
            pdf.para("No readable metadata was available.", 8.5, MUTED)
        if md.get("not_available"):
            pdf.para("Metadata not available: " + ", ".join(md["not_available"]), 8, MUTED)
        for sg in md.get("signatures", []):
            state = {True: "intact", False: "changed after signing", None: "not checked"}[sg.get("intact")]
            pdf.para(f"Digital signature: {sg.get('signer') or sg.get('field')} — {state}"
                     f"{'' if sg.get('trusted') else ' (certificate not from a trusted authority)'}", 8, MUTED)
        for fl in md.get("flags", []):
            pdf.para(f"Metadata signal ({fl['severity']}): {fl['title']} — {fl['value_a']} / {fl['value_b']}", 8, AMBER)
        pdf.ln(2)

    pdf.h2("4. Entities")
    ent = d.get("entities_summary", {})
    pdf.kv([(k, ", ".join(v)) for k, v in ent.items()] or [("Entities", "None detected")], 30)

    pdf.h2("5. Timeline")
    tl = d.get("timeline", [])
    if tl:
        flag = {"conflict": "Conflicting date", "review": "Requires review", "resolved": "Reviewed"}
        pdf.grid(["Date", "Event", "Source record(s)", "Conf.", "Flag"],
                 [[_day(e["date"]) + (f" {e['time']}" if e.get("time") else ""), e["event"], e["source"], f"{e['confidence']:.0%}",
                   flag.get(e.get("flag"), "Normal")] for e in tl], (24, 44, 70, 14, 26))
    else:
        pdf.para("No dated events were extracted.", 8.5, MUTED)

    pdf.h2("6. Relationship summary")
    rel = d.get("relationships", [])
    if rel:
        pdf.grid(["Record A", "Record B", "Signal", "Score", "Evidence"],
                 [[x["a"], x["b"], f"{x['label']}\n{x['type']}", f"{x['score']:.0%}",
                   "; ".join(f"{e['type']}: {e['value']}" for e in x.get("evidence", [])[:3])] for x in rel], (38, 38, 32, 14, 56))
    else:
        pdf.para("No significant relationship signals detected.", 8.5, MUTED)

    pdf.h2("7. Potential inconsistencies")
    if confs:
        for x in confs:
            pdf.conflict(x)
    else:
        pdf.para("No potential inconsistencies detected in the currently analyzed records.", 8.5, MUTED)

    pdf.h2("8. Review actions")
    rv = d.get("review_actions", [])
    if rv:
        pdf.grid(["When", "Reviewer", "Action", "Subject", "Note"],
                 [[_d(a["at"]), f"{a['user']}\n{a['role']}", a["action"].replace("_", " ").title() + (f"\n{a['status_change']}" if a.get("status_change") else ""),
                   a.get("subject"), a.get("note")] for a in rv], (30, 30, 30, 40, 48))
    else:
        pdf.para("No review actions have been recorded yet.", 8.5, MUTED)

    pdf.h2("9. Audit information")
    au = d.get("audit", [])
    pdf.para(f"{len(au)} audit entries recorded for this case (most recent 60 shown). The audit log is hash-chained.", 8, MUTED)
    pdf.grid(["Timestamp", "Actor", "Action", "Result"],
             [[_d(a["ts"]), f"{a['user']} ({a['role']})", a["action"] + (f"\n{a['details'][:140]}" if a.get("details") else ""), a["result"]]
              for a in au[-60:]], (32, 38, 90, 18))

    pdf.h2("10. Limitations & disclaimer")
    for l in d.get("limitations", []):
        pdf.para("• " + l, 8.5)
    pdf.ln(3)
    pdf.disclaimer()
    pdf.para(f"HTML report SHA-256: {report_sha}", 7, MUTED)
    return bytes(pdf.output())


def build_summary_pdf(d: dict, report_sha: str) -> bytes:
    pdf = ReportPDF(d, "Executive Summary")
    pdf.cover("Executive Summary")
    c = d["case"]
    confs = d.get("conflicts", [])
    open_c = [x for x in confs if _open(x)]
    recs = d.get("records", [])
    sigs = [s for r in recs for s in (r.get("metadata") or {}).get("signatures", [])]
    flags = [f for r in recs for f in (r.get("metadata") or {}).get("flags", [])]
    pdf.stats([(len(recs), "Records analysed"), (len(d.get("relationships", [])), "Relationship signals"),
               (len(open_c), "Open inconsistencies"), (len(confs) - len(open_c), "Reviewed / closed")])
    pdf.h2("Overview")
    ocr = sum(1 for r in recs if str(r.get("text_method", "")).startswith("OCR"))
    span = sorted(e["date"] for e in d.get("timeline", []))
    pdf.para(f"{c.get('name')} ({c.get('code')}) contains {len(recs)} records, all fingerprinted with SHA-256"
             f"{f'; {ocr} required OCR' if ocr else ''}. "
             + (f"Extracted events span {_day(span[0])} to {_day(span[-1])}. " if span else "")
             + f"The analysis found {len(d.get('relationships', []))} relationship signals and {len(confs)} potential "
               f"inconsistencies, of which {len(open_c)} still await a reviewer's decision.", 9.5)
    pdf.ln(1)
    pdf.kv([("Status", c.get("status_label")), ("Owner", c.get("owner")), ("Review status", c.get("review_status")),
            ("Digital signatures", (f"{len(sigs)} found — " + ", ".join(
                {True: "intact", False: "changed", None: "not checked"}[s.get("intact")] for s in sigs)) if sigs else "None embedded"),
            ("Metadata signals", f"{len(flags)} ({sum(1 for f in flags if f['severity'] != 'low')} need review)" if flags else "None")])
    pdf.h2("Key findings requiring attention")
    if open_c:
        for x in open_c[:8]:
            pdf.conflict(x, compact=True)
        if len(open_c) > 8:
            pdf.para(f"… and {len(open_c) - 8} more in the full report.", 8, MUTED)
    else:
        pdf.para("No open potential inconsistencies. All flagged items have been reviewed.", 9, GREEN, True)
    decided = [a for a in d.get("review_actions", []) if a.get("action") != "note"]
    if decided:
        pdf.h2("Recent review decisions")
        for a in decided[-5:]:
            pdf.para(f"• {a['user']} ({a['role']}) — {a['action'].replace('_', ' ')}: {a.get('subject')}"
                     + (f". Reason: {a['note']}" if a.get("note") else ""), 8.5)
    pdf.h2("Recommendation")
    pdf.para(("Resolve or escalate the open items above before relying on these records. "
              if open_c else "The evidence signals are consistent after review. ")
             + "Findings are signals for human judgement and do not establish authenticity.", 9)
    pdf.ln(2)
    pdf.para(f"Full report reference (HTML SHA-256): {report_sha}", 7, MUTED)
    return bytes(pdf.output())
