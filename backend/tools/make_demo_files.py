"""Generates the SYNTHETIC demo records shipped in backend/demo_files/.

All people, institutions, companies and identifiers are fictional. Intentional inconsistencies
are embedded so the analysis pipeline has something to surface. Run: python tools/make_demo_files.py
"""
import io
import random
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "demo_files"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SYN = "SYNTHETIC DEMO DATA - fictional record for demonstration only"


def pdf_doc(path, title, subtitle, header, rows, table=None, footer_rows=None, author="Controller of Examinations",
            created=datetime(2026, 6, 15, 10, 30), modified=None, accent=(59, 31, 122)):
    pdf = FPDF(format="A4")
    pdf.add_font("DV", "", FONT)
    pdf.add_font("DV", "B", FONT_B)
    pdf.set_author(author)
    pdf.set_creator("WGU Examination Records System 4.2 (synthetic)")
    pdf.set_title(title)
    pdf.set_creation_date(created)
    pdf.add_page()
    pdf.set_fill_color(*accent)
    pdf.rect(0, 0, 210, 34, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DV", "B", 17)
    pdf.set_xy(14, 8)
    pdf.cell(0, 9, header)
    pdf.set_font("DV", "", 9.5)
    pdf.set_xy(14, 18)
    pdf.cell(0, 6, subtitle)
    pdf.set_text_color(20, 20, 30)
    pdf.set_xy(14, 42)
    pdf.set_font("DV", "B", 14)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DV", "", 8)
    pdf.set_text_color(160, 60, 60)
    pdf.cell(0, 5, SYN, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(20, 20, 30)
    pdf.ln(3)
    pdf.set_font("DV", "", 10.5)
    for label, value in rows:
        pdf.set_x(14)
        pdf.cell(0, 7, f"{label}: {value}", new_x="LMARGIN", new_y="NEXT")
    if table:
        pdf.ln(4)
        pdf.set_font("DV", "B", 9.5)
        widths = table["widths"]
        pdf.set_fill_color(238, 234, 250)
        pdf.set_x(14)
        for w, h in zip(widths, table["head"]):
            pdf.cell(w, 7, h, border=1, fill=True)
        pdf.ln()
        pdf.set_font("DV", "", 9.5)
        for row in table["rows"]:
            pdf.set_x(14)
            for w, v in zip(widths, row):
                pdf.cell(w, 7, str(v), border=1)
            pdf.ln()
    if footer_rows:
        pdf.ln(4)
        pdf.set_font("DV", "", 10.5)
        for label, value in footer_rows:
            pdf.set_x(14)
            pdf.cell(0, 7, f"{label}: {value}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("DV", "", 9)
    pdf.set_x(130)
    pdf.cell(0, 6, "Authorised Signatory")
    pdf.output(str(OUT / path))
    if modified:
        # re-save with a different modified date to demonstrate metadata comparison
        from pypdf import PdfReader, PdfWriter
        r = PdfReader(str(OUT / path))
        w = PdfWriter()
        for p in r.pages:
            w.add_page(p)
        md = dict(r.metadata or {})
        md["/ModDate"] = modified.strftime("D:%Y%m%d%H%M%S")
        w.add_metadata(md)
        with open(OUT / path, "wb") as f:
            w.write(f)


def text_image(lines, size=(1100, 700), bg=(250, 250, 252), title_color=(40, 30, 110), band=None, rotate=0.0,
               noise=False):
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(FONT_B, 34)
    f_b = ImageFont.truetype(FONT_B, 27)
    f = ImageFont.truetype(FONT, 27)
    f_s = ImageFont.truetype(FONT, 19)
    y = 30
    if band:
        d.rectangle([0, 0, size[0], 112], fill=band)
    for kind, text in lines:
        if kind == "title":
            d.text((40, y), text, font=f_title, fill=(255, 255, 255) if band and y < 100 else title_color)
            y += 50
        elif kind == "sub":
            d.text((40, y), text, font=f_s, fill=(235, 235, 255) if band and y < 110 else (90, 90, 110))
            y += 34
        elif kind == "gap":
            y += int(text)
        elif kind == "kv":
            k, v = text
            d.text((40, y), f"{k}:", font=f_b, fill=(30, 30, 45))
            w = d.textlength(f"{k}: ", font=f_b)
            d.text((40 + w, y), v, font=f, fill=(30, 30, 45))
            y += 44
        elif kind == "small":
            d.text((40, y), text, font=f_s, fill=(170, 60, 60))
            y += 32
    if noise:
        px = img.load()
        rnd = random.Random(7)
        for _ in range(9000):
            x, yy = rnd.randrange(size[0]), rnd.randrange(size[1])
            c = rnd.randrange(170, 235)
            px[x, yy] = (c, c, c)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=(245, 245, 240))
    return img


def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.glob("*"):
        if p.is_file():
            p.unlink()

    # ---------------- Academic Record Verification ----------------
    courses = {"widths": [30, 92, 22, 22, 18], "head": ["Code", "Course", "Credits", "Grade", "Points"],
               "rows": [["CS8801", "Distributed Systems", 3, "A", 9], ["CS8802", "Information Security", 3, "A+", 10],
                        ["CS8811", "Project Work", 10, "A", 9], ["CS8003", "Digital Forensics (Elective)", 3, "B+", 8]]}
    pdf_doc("01_Semester_Marksheet_Sem8.pdf", "STATEMENT OF MARKS - SEMESTER VIII",
            "Office of the Controller of Examinations, Coimbatore", "WESTERN GHATS UNIVERSITY",
            [("Student Name", "Rahul Kumar"), ("Register Number", "WGU22CS045"), ("Date of Birth", "14/03/2004"),
             ("Programme", "B.E. Computer Science and Engineering"), ("Examination Held On", "28 April 2026")],
            courses, [("SGPA", "8.61"), ("Result Published On", "02 June 2026"), ("Date of Issue", "15 June 2026"),
                      ("Place", "Coimbatore")], created=datetime(2026, 6, 15, 10, 30))
    sign_pdf(OUT / "01_Semester_Marksheet_Sem8.pdf")
    pdf_doc("02_Consolidated_Marksheet.pdf", "CONSOLIDATED STATEMENT OF MARKS",
            "Office of the Controller of Examinations, Coimbatore", "WESTERN GHATS UNIVERSITY",
            [("Student Name", "Rahul Kumar"), ("Register Number", "WGU22CS045"), ("Date of Birth", "14/03/2004"),
             ("Programme", "B.E. Computer Science and Engineering"), ("Period of Study", "2022 - 2026"),
             ("CGPA", "8.42"), ("Classification", "First Class with Distinction")],
            {"widths": [40, 50, 50, 44], "head": ["Semester", "Credits Earned", "SGPA", "Session"],
             "rows": [["I-II", 44, "8.10", "2022-23"], ["III-IV", 46, "8.35", "2023-24"], ["V-VI", 45, "8.52", "2024-25"],
                      ["VII-VIII", 38, "8.61", "2025-26"]]},
            [("Date of Issue", "28 August 2026"), ("Place", "Coimbatore")],
            created=datetime(2026, 8, 28, 11, 5), modified=datetime(2026, 9, 3, 16, 42))

    d = Document()
    d.core_properties.author = "Registrar Office (synthetic)"
    d.core_properties.title = "Degree Certificate"
    d.core_properties.created = datetime(2026, 9, 10, 9, 15)
    d.core_properties.modified = datetime(2026, 9, 8, 17, 40)  # deliberate anomaly: modified before created
    d.core_properties.last_modified_by = "records.clerk"
    h = d.add_heading("WESTERN GHATS UNIVERSITY", 0)
    d.add_paragraph("Coimbatore, Tamil Nadu")
    p = d.add_paragraph()
    r = p.add_run(SYN)
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor(0xA0, 0x3C, 0x3C)
    d.add_heading("DEGREE CERTIFICATE", 1)
    d.add_paragraph("Certificate No: WGU/DC/2026/11873")
    d.add_paragraph("This is to certify that Rahul Kumaar, having been found qualified at the examinations held by "
                    "Western Ghats University, has been admitted to the degree of Bachelor of Engineering in Computer "
                    "Science and Engineering. The degree was conferred at the convocation on 10 September 2026.")
    t = d.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in [("Awarded To", "Rahul Kumaar"), ("Register Number", "WGU22CS045"),
                 ("Programme", "B.E. Computer Science and Engineering"), ("Classification", "First Class with Distinction"),
                 ("Degree Conferred On", "10 September 2026"), ("Place", "Coimbatore")]:
        row = t.add_row().cells
        row[0].text, row[1].text = k, v
    d.add_paragraph("")
    d.add_paragraph("Date of Issue: 10 September 2026")
    d.add_paragraph("Registrar, Western Ghats University")
    d.save(OUT / "03_Degree_Certificate.docx")

    id_img = text_image([
        ("title", "WESTERN GHATS UNIVERSITY"), ("sub", "STUDENT IDENTITY CARD  -  Coimbatore Campus"), ("gap", 40),
        ("kv", ("Name", "Rahul Kumar")), ("kv", ("Student ID No", "WGU22CS045")),
        ("kv", ("Date of Birth", "14-03-2004")), ("kv", ("Programme", "B.E. CSE")), ("kv", ("Batch", "2022 - 2026")),
        ("kv", ("Date of Issue", "01 Aug 2022")), ("kv", ("Valid Till", "31 Jul 2026")),
        ("small", "SYNTHETIC DEMO DATA - fictional identity card"),
    ], size=(1150, 720), band=(52, 34, 128))
    dd = ImageDraw.Draw(id_img)
    dd.rounded_rectangle([860, 160, 1100, 450], 16, outline=(120, 110, 170), width=4, fill=(236, 233, 250))
    dd.ellipse([930, 200, 1030, 300], fill=(180, 170, 215))
    dd.rounded_rectangle([900, 310, 1060, 430], 40, fill=(180, 170, 215))
    id_img.save(OUT / "04_Student_ID_Card.png", pnginfo=_pnginfo({"Software": "ID Card Printer Suite 2.1 (synthetic)"}))

    (OUT / "05_Academic_Transcript.txt").write_text("""WESTERN GHATS UNIVERSITY
Student Records Portal - Academic Transcript (text export)
SYNTHETIC DEMO DATA - fictional record for demonstration only

Student Name: Rahul Kumar
Register Number: WGU22CS054
Date of Birth: 14/03/2004
Programme: B.E. Computer Science and Engineering
Period of Study: 2022 - 2026
CGPA: 8.42
Degree Conferred On: 12 September 2026
Date of Issue: 15 September 2026
Place: Coimbatore

Semester Summary
Semester I-II   : 44 credits, SGPA 8.10
Semester III-IV : 46 credits, SGPA 8.35
Semester V-VI   : 45 credits, SGPA 8.52
Semester VII-VIII: 38 credits, SGPA 8.61

This transcript was generated electronically by Western Ghats University.
""", encoding="utf-8")

    # ---------------- Invoice Verification ----------------
    pdf_doc("11_Invoice_INV-2026-1142.pdf", "TAX INVOICE", "Plot 18, SIDCO Industrial Estate, Coimbatore 641021 | GSTIN 33AAAAA0000A1Z5 (synthetic)",
            "NILGIRI INDUSTRIAL SUPPLIES PVT LTD",
            [("Invoice No", "INV-2026-1142"), ("Invoice Date", "08 September 2026"), ("PO Reference", "PO-2026-0781"),
             ("Bill To", "Sreeram Textiles"), ("Ship To", "Erode")],
            {"widths": [80, 22, 40, 42], "head": ["Item", "Qty", "Rate (Rs.)", "Amount (Rs.)"],
             "rows": [["Industrial sewing motor 550W", 12, "6,850.00", "82,200.00"],
                      ["Spindle bearing kit", 40, "925.00", "37,000.00"],
                      ["Belt drive assembly", 16, "415.47", "6,647.46"]]},
            [("Subtotal", "Rs. 1,25,847.46"), ("GST @ 18%", "Rs. 22,652.54"), ("Grand Total", "Rs. 1,48,500.00"),
             ("Due Date", "22 September 2026")], author="Accounts - Nilgiri Industrial Supplies",
            created=datetime(2026, 9, 8, 15, 2), accent=(14, 95, 122))

    d = Document()
    d.core_properties.author = "Purchase Dept, Sreeram Textiles (synthetic)"
    d.core_properties.title = "Purchase Order PO-2026-0781"
    d.core_properties.created = datetime(2026, 9, 2, 12, 40)
    d.core_properties.modified = datetime(2026, 9, 2, 13, 5)
    d.add_heading("SREERAM TEXTILES", 0)
    d.add_paragraph("Avinashi Road, Tiruppur, Tamil Nadu")
    p = d.add_paragraph()
    r = p.add_run(SYN)
    r.font.size = Pt(8)
    d.add_heading("PURCHASE ORDER", 1)
    t = d.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in [("PO Number", "PO-2026-0781"), ("Order Date", "02 September 2026"), ("Buyer", "Sreeram Textiles"),
                 ("Vendor", "Nilgiri Industrial Supplies Pvt Ltd"), ("Ship To", "Tiruppur")]:
        row = t.add_row().cells
        row[0].text, row[1].text = k, v
    d.add_paragraph("")
    it = d.add_table(rows=1, cols=3)
    it.style = "Table Grid"
    it.rows[0].cells[0].text, it.rows[0].cells[1].text, it.rows[0].cells[2].text = "Item", "Qty", "Amount"
    for a, b, c in [("Industrial sewing motor 550W", "12", "₹82,200.00"), ("Spindle bearing kit", "40", "₹37,000.00"),
                    ("Belt drive assembly", "16", "₹6,647.46"), ("GST 18%", "-", "₹22,652.54")]:
        cells = it.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = a, b, c
    d.add_paragraph("")
    d.add_paragraph("Grand Total: ₹1,48,500.00")
    d.add_paragraph("Delivery expected by 15 September 2026.")
    d.save(OUT / "12_Purchase_Order_PO-2026-0781.docx")

    rc = text_image([
        ("title", "PAYMENT RECEIPT"), ("sub", "Nilgiri Industrial Supplies Pvt Ltd - Coimbatore"), ("gap", 30),
        ("kv", ("Receipt No", "RCP-5531")), ("kv", ("Receipt Date", "05/09/2026")),
        ("kv", ("Received From", "Sreeram Textiles")), ("kv", ("Against Invoice", "INV-2026-1142")),
        ("kv", ("Amount Received", "Rs. 1,45,800.00")), ("kv", ("Mode", "Bank Transfer")),
        ("kv", ("Issued By", "Nilgiri Industrial Supplies Pvt Ltd")),
        ("small", "SYNTHETIC DEMO DATA - scanned copy of a fictional receipt"),
    ], size=(1240, 760), bg=(247, 246, 240), noise=True, rotate=0.6)
    buf = io.BytesIO()
    rc.save(buf, "JPEG", quality=88)
    pdf = FPDF(format="A4")
    pdf.set_creator("ScanStation Pro (synthetic)")
    pdf.set_creation_date(datetime(2026, 9, 12, 18, 20))
    pdf.add_page()
    pdf.image(buf, x=8, y=12, w=194)
    pdf.output(str(OUT / "13_Receipt_RCP-5531_scanned.pdf"))

    pay = text_image([
        ("title", "FUND TRANSFER CONFIRMATION"), ("sub", "Kaveri Demo Bank - Internet Banking (synthetic)"), ("gap", 34),
        ("kv", ("Transaction ID", "TXN88213490")), ("kv", ("Transaction Date", "12-09-2026 14:32")),
        ("kv", ("Remitter", "Sreeram Textiles")), ("kv", ("Beneficiary", "Nilgiri Industrial Supplies Pvt Ltd")),
        ("kv", ("Amount", "Rs. 1,48,500.00")), ("kv", ("Remarks", "Payment for INV-2026-1142")),
        ("kv", ("Status", "SUCCESS")), ("small", "SYNTHETIC DEMO DATA - fictional bank record"),
    ], size=(1200, 760), band=(12, 88, 110))
    exif = pay.getexif()
    exif[0x010F] = "DemoCam"
    exif[0x0110] = "DRCV Synthetic Capture"
    exif[0x0131] = "Adobe Photoshop 25.0 (synthetic metadata)"
    exif[0x0132] = "2026:09:12 14:35:09"
    gps = {1: "N", 2: (11.0, 1.0, 1.2), 3: "E", 4: (76.0, 57.0, 29.4)}
    exif.get_ifd(0x8825).update(gps)
    pay.save(OUT / "14_Payment_Record_TXN88213490.jpg", "JPEG", quality=92, exif=exif)

    # ---------------- Lease Agreement Verification (consistent) ----------------
    (OUT / "21_Lease_Agreement.txt").write_text("""RESIDENTIAL LEASE AGREEMENT
SYNTHETIC DEMO DATA - fictional record for demonstration only

Agreement Date: 20 May 2026
Landlord: Meena Sundaram
Tenant: Arjun Prakash
Property Address: 14, Lake View Road, Coimbatore
Monthly Rent: ₹18,000.00
Security Deposit: ₹54,000.00
Lease Start Date: 01 June 2026
Lease Term: 11 months

Signed by both parties at Coimbatore.
""", encoding="utf-8")
    for month, rdate, pdate in (("June", "05 June 2026", "04 June 2026"), ("July", "05 July 2026", "03 July 2026")):
        (OUT / f"2{2 if month == 'June' else 3}_Rent_Receipt_{month}.txt").write_text(f"""RENT RECEIPT - {month.upper()} 2026
SYNTHETIC DEMO DATA - fictional record for demonstration only

Receipt No: RR-2026-{'06' if month == 'June' else '07'}01
Tenant: Arjun Prakash
Landlord: Meena Sundaram
Property Address: 14, Lake View Road, Coimbatore
Monthly Rent: ₹18,000.00
Payment Date: {pdate}
Receipt Date: {rdate}
""", encoding="utf-8")
    print("\n".join(sorted(p.name for p in OUT.iterdir())))


def sign_pdf(path):
    """Signs a demo PDF with a SELF-SIGNED synthetic certificate (pyHanko)."""
    import datetime as dt
    import os
    os.environ.setdefault("TZ", "UTC")
    from asn1crypto import keys as ak, x509 as ax
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Controller of Examinations (SYNTHETIC)"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Western Ghats University (fictional)")])
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1001).not_valid_before(start).not_valid_after(start + dt.timedelta(days=3650))
            .sign(key, hashes.SHA256()))
    signer = signers.SimpleSigner(
        signing_cert=ax.Certificate.load(cert.public_bytes(serialization.Encoding.DER)),
        signing_key=ak.PrivateKeyInfo.load(key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                                             serialization.NoEncryption())), cert_registry=None)
    w = IncrementalPdfFileWriter(io.BytesIO(path.read_bytes()))
    out = signers.sign_pdf(w, signers.PdfSignatureMetadata(field_name="ExaminationSeal", reason="Official statement of marks",
                                                           location="Coimbatore", name="Controller of Examinations"), signer=signer)
    path.write_bytes(out.getvalue())


def _pnginfo(d):
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    for k, v in d.items():
        info.add_text(k, v)
    return info


if __name__ == "__main__":
    main()
