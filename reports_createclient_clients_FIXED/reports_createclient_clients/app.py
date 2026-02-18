import os
import io
import re
import sqlite3
import subprocess
import base64
import json
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from flask import Flask, g, render_template, request, jsonify, redirect, url_for, send_file, abort

app = Flask(__name__)
app.secret_key = "dev-only-change-me"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")

# -------------------------
# DB helpers
# -------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NULL,
            bill_to_name TEXT NOT NULL,
            bill_to_email TEXT,
            bill_to_phone TEXT,
            bill_to_address TEXT,
            invoice_number TEXT NOT NULL UNIQUE,
            currency TEXT NOT NULL DEFAULT 'SGD',
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            notes TEXT,
            gst_rate REAL NOT NULL DEFAULT 9.0,
            subtotal REAL NOT NULL DEFAULT 0.0,
            gst_amount REAL NOT NULL DEFAULT 0.0,
            total_amount REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            line_total REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        );

        -- Minimal catalogue storage (used by Create Invoice picker)
        CREATE TABLE IF NOT EXISTS catalogue_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            description TEXT,
            unit_price REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    # Seed 1 item so the picker has something to show (safe no-op if already seeded)
    cur = db.execute("SELECT COUNT(*) AS c FROM catalogue_items")
    count = cur.fetchone()["c"]
    if count == 0:
        db.execute(
            """
            INSERT INTO catalogue_items (name, sku, category, description, unit_price)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("apple", "PRD-002", "Products", "", 200.0),
        )
    db.commit()

@app.before_request
def _ensure_db():
    init_db()

# -------------------------
# Pages
# -------------------------
@app.route("/")
def home():
    return redirect(url_for("dashboard_page"))

@app.route("/clients")
def clients_page():
    return render_template("clients.html", page="clients")

@app.route("/create-invoice")
def create_invoice_page():
    return render_template("create_invoice.html", page="create_invoice")


@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html", page="dashboard")

@app.route("/invoices")
def invoices_page():
    # If you arrive here from "Preview", pass invoice_id in querystring.
    invoice_id = request.args.get("invoice_id")
    if invoice_id and str(invoice_id).isdigit():
        return redirect(url_for("invoice_preview_page", invoice_id=int(invoice_id)))
    # Default: show latest invoice preview if exists; otherwise show empty state page.
    db = get_db()
    inv = db.execute("SELECT id FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
    if inv:
        return redirect(url_for("invoice_preview_page", invoice_id=inv["id"]))
    return render_template("invoice_preview.html", page="invoices", invoice=None)


@app.route("/invoice-preview/<int:invoice_id>")
def invoice_preview_page(invoice_id: int):
    db = get_db()
    inv = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        return abort(404)
    items = db.execute("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id ASC", (invoice_id,)).fetchall()

    invoice = {
        "id": inv["id"],
        "invoice_number": inv["invoice_number"],
        "issue_date": inv["issue_date"],
        "due_date": inv["due_date"],
        "gst_rate": inv["gst_rate"],
        "subtotal": inv["subtotal"],
        "gst": inv["gst_amount"],
        "total": inv["total_amount"],
        "client_name": inv["bill_to_name"],
        "client_email": inv["bill_to_email"] or "",
        "client_address": inv["bill_to_address"] or "",
        "items": [
            {
                "description": r["description"],
                "quantity": int(r["quantity"]) if float(r["quantity"]).is_integer() else r["quantity"],
                "unit_price": r["unit_price"],
            }
            for r in items
        ],
    }
    return render_template("invoice_preview.html", page="invoices", invoice=invoice)



from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

@app.route("/download/<int:invoice_id>")
def download_invoice_pdf(invoice_id):
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    items = db.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,)).fetchall()

    if not invoice:
        return abort(404)

    buffer = io.BytesIO()

    # Keep margins generous to match the preview/PDF reference layout
    from reportlab.lib.pagesizes import A4

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=48,
        bottomMargin=48,
    )
    content_width = doc.width
    elements = []
    styles = getSampleStyleSheet()

    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle

    # Fix alignment: ReportLab's built-in Title style is centered by default.
    # We want brand title left, and invoice title right (to match preview/reference).
    brand_title_style = ParagraphStyle('brand_title_style', parent=styles['Title'], alignment=TA_LEFT)
    invoice_title_style = ParagraphStyle('invoice_title_style', parent=styles['Title'], alignment=TA_RIGHT)
    right_meta_style = ParagraphStyle('right_meta_style', parent=styles['Normal'], alignment=TA_RIGHT)

    # --- Header (matches invoice preview layout) ---
    brand = Paragraph('<font color="#2563eb"><b>FourVoice</b></font>', brand_title_style)
    left_lines = [
        brand,
        Paragraph('123 Business Street', styles['Normal']),
        Paragraph('Singapore 123456', styles['Normal']),
        Paragraph('contact@fourvoice.com', styles['Normal']),
        Paragraph('+65 1234 5678', styles['Normal']),
    ]

    right_lines = [
        Paragraph('<b>INVOICE</b>', invoice_title_style),
        Paragraph(f'<b>{invoice["invoice_number"]}</b>', right_meta_style),
        Paragraph(f'Issue Date: {invoice["issue_date"]}', right_meta_style),
        Paragraph(f'Due Date: {invoice["due_date"]}', right_meta_style),
    ]

    header_tbl = Table(
        [[left_lines, right_lines]],
        colWidths=[content_width - (2.5 * inch), 2.5 * inch],
        hAlign='LEFT'
    )
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 0.35 * inch))

    # --- Bill To ---
    bill_to = [
        Paragraph('<b>Bill To:</b>', styles['Normal']),
        Paragraph(f'<b>{invoice["bill_to_name"] or ""}</b>', styles['Normal']),
    ]
    if invoice["bill_to_email"]:
        bill_to.append(Paragraph(invoice["bill_to_email"], styles['Normal']))
    if invoice["bill_to_address"]:
        bill_to.append(Paragraph(invoice["bill_to_address"], styles['Normal']))
    elements.append(Table([[bill_to]], colWidths=[content_width], hAlign='LEFT'))
    elements.append(Spacer(1, 0.25 * inch))

    # --- Line items table ---
    data = [["Description", "Qty", "Rate", "Amount"]]
    subtotal = 0.0
    for item in items:
        qty = float(item["quantity"])
        rate = float(item["unit_price"])
        amount = qty * rate
        subtotal += amount
        data.append([
            item["description"],
            str(int(qty) if qty.is_integer() else qty),
            f"S${rate:.2f}",
            f"S${amount:.2f}",
        ])

    items_tbl = Table(data, colWidths=[content_width - (0.8*inch + 1.1*inch + 1.1*inch), 0.8*inch, 1.1*inch, 1.1*inch])
    items_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#e5e7eb')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor('#f1f5f9')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(items_tbl)
    elements.append(Spacer(1, 0.25 * inch))

    # --- Totals (right aligned, blue grand total) ---
    gst_rate = float(invoice["gst_rate"] or 0)
    gst = subtotal * (gst_rate / 100.0)
    total = subtotal + gst

    totals_tbl = Table(
        [
            ["Subtotal", f"S${subtotal:.2f}"],
            [f"GST ({int(gst_rate) if gst_rate.is_integer() else gst_rate}%)", f"S${gst:.2f}"],
            [Paragraph('<b>Total Amount</b>', styles['Normal']),
             Paragraph(f'<para align="right"><font color="#2563eb"><b>S${total:.2f}</b></font></para>', styles['Normal'])],
        ],
        colWidths=[1.8 * inch, 1.2 * inch],
        hAlign='RIGHT'
    )
    totals_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor('#e5e7eb')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(totals_tbl)

    doc.build(elements)
    buffer.seek(0)

    safe_name = (invoice["invoice_number"] or f"invoice_{invoice_id}").strip()
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{safe_name}.pdf",
        mimetype='application/pdf'
    )

@app.route("/submit/<int:invoice_id>")
def submit_invoice(invoice_id: int):
    db = get_db()
    inv = db.execute("SELECT id FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        return abort(404)
    db.execute("UPDATE invoices SET status=? WHERE id=?", ("pending", invoice_id))
    db.commit()
    return redirect(url_for("approval_page"))

@app.route("/catalogue")
def catalogue_page():
    return render_template("catalogue.html", page="catalogue")

@app.route("/audit-log")
def audit_log_page():
    return render_template("audit_log.html", page="audit_log")

@app.route("/manage-users")
def manage_users_page():
    return render_template("manage_users.html", page="manage_users")

@app.route("/approval")
def approval_page():
    return render_template("approval.html", page="approval")

@app.route("/my-company")
def my_company_page():
    return render_template("my_company.html", page="my_company")

# -------------------------
# API: Clients
# -------------------------
def _client_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "address": row["address"],
        "created_at": row["created_at"],
    }

@app.get("/api/clients")
def api_list_clients():
    q = (request.args.get("q") or "").strip().lower()
    db = get_db()
    rows = db.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
    clients = [_client_to_dict(r) for r in rows]
    if q:
        def match(c):
            return (q in (c["name"] or "").lower()
                or q in (c["email"] or "").lower()
                or q in (c["phone"] or "").lower())
        clients = [c for c in clients if match(c)]
    return jsonify({"clients": clients})

@app.post("/api/clients")
def api_create_client():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    address = (data.get("address") or "").strip()

    errors = {}
    if not name:
        errors["name"] = "Name is required"
    if not email:
        errors["email"] = "Email is required"
    elif not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        errors["email"] = "Invalid email address"
    if not phone:
        errors["phone"] = "Phone is required"
    else:
        p = re.sub(r"\s+", "", phone)
        if not re.match(r"^\+?\d{8,15}$", p):
            errors["phone"] = "Invalid phone number (8–15 digits, + allowed)"
    if not address:
        errors["address"] = "Address is required"

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO clients (name,email,phone,address,created_at) VALUES (?,?,?,?,datetime('now'))",
        (name, email, phone, address),
    )
    db.commit()
    new_id = cur.lastrowid
    row = db.execute("SELECT * FROM clients WHERE id=?", (new_id,)).fetchone()
    return jsonify({"ok": True, "client": _client_to_dict(row)})

@app.put("/api/clients/<int:client_id>")
def api_update_client(client_id: int):
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    address = (data.get("address") or "").strip()

    errors = {}
    if not name:
        errors["name"] = "Name is required"
    if not email:
        errors["email"] = "Email is required"
    elif not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        errors["email"] = "Invalid email address"
    if not phone:
        errors["phone"] = "Phone is required"
    else:
        p = re.sub(r"\s+", "", phone)
        if not re.match(r"^\+?\d{8,15}$", p):
            errors["phone"] = "Invalid phone number (8–15 digits, + allowed)"
    if not address:
        errors["address"] = "Address is required"

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM clients WHERE id=?", (client_id,)).fetchone()
    if not exists:
        return jsonify({"ok": False, "error": "Client not found"}), 404

    db.execute(
        "UPDATE clients SET name=?, email=?, phone=?, address=? WHERE id=?",
        (name, email, phone, address, client_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    return jsonify({"ok": True, "client": _client_to_dict(row)})

@app.delete("/api/clients/<int:client_id>")
def api_delete_client(client_id: int):
    db = get_db()
    exists = db.execute("SELECT id FROM clients WHERE id=?", (client_id,)).fetchone()
    if not exists:
        return jsonify({"ok": False, "error": "Client not found"}), 404

    # We delete the client; invoices will keep a snapshot + client_id becomes NULL.
    db.execute("DELETE FROM clients WHERE id=?", (client_id,))
    db.commit()
    return jsonify({"ok": True})


# =========================
# Catalogue (minimal stub)
# =========================

@app.get("/api/catalogue-items")
def api_catalogue_items():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, sku, category, description, unit_price FROM catalogue_items ORDER BY id DESC"
    ).fetchall()
    items = [dict(r) for r in rows]
    return jsonify({"items": items})

# -------------------------
# API: Invoices (minimal)
# -------------------------
def _invoice_to_dict(row):
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "bill_to_name": row["bill_to_name"],
        "invoice_number": row["invoice_number"],
        "currency": row["currency"],
        "issue_date": row["issue_date"],
        "due_date": row["due_date"],
        "subtotal": row["subtotal"],
        "gst_rate": row["gst_rate"],
        "gst_amount": row["gst_amount"],
        "total_amount": row["total_amount"],
        "status": row["status"],
        "created_at": row["created_at"],
    }

@app.get("/api/invoices")
def api_list_invoices():
    client_id = request.args.get("client_id")
    db = get_db()
    if client_id:
        rows = db.execute(
            "SELECT * FROM invoices WHERE client_id=? OR bill_to_name IS NOT NULL ORDER BY issue_date DESC, id DESC",
            (client_id,),
        ).fetchall()
        # Filter down properly: for "history", we want either same client_id OR snapshot name match (client may have been deleted).
        # We'll pass optional bill_to_name in query for better match.
        bill_to_name = (request.args.get("bill_to_name") or "").strip()
        invoices = []
        for r in rows:
            if r["client_id"] == int(client_id):
                invoices.append(_invoice_to_dict(r))
            elif bill_to_name and (r["bill_to_name"] or "").strip() == bill_to_name:
                invoices.append(_invoice_to_dict(r))
        return jsonify({"invoices": invoices})

    rows = db.execute("SELECT * FROM invoices ORDER BY issue_date DESC, id DESC").fetchall()
    return jsonify({"invoices": [_invoice_to_dict(r) for r in rows]})

@app.get("/api/invoices/next-number")
def api_next_invoice_number():
    year = datetime.now().year
    db = get_db()
    rows = db.execute(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?",
        (f"INV-{year}-%",),
    ).fetchall()
    highest = 0
    for r in rows:
        m = re.match(rf"^INV-{year}-(\d+)$", r["invoice_number"] or "")
        if m:
            highest = max(highest, int(m.group(1)))
    next_num = str(highest + 1).zfill(3)
    return jsonify({"invoice_number": f"INV-{year}-{next_num}"})


@app.post("/api/invoices")
def api_create_invoice():
    data = request.get_json(force=True, silent=True) or {}
    client_mode = data.get("client_mode")  # 'saved' | 'oneoff'
    client_id = data.get("client_id")
    oneoff_name = (data.get("oneoff_name") or "").strip()

    invoice_number = (data.get("invoice_number") or "").strip()
    currency = (data.get("currency") or "SGD").strip()
    issue_date = (data.get("issue_date") or "").strip()
    due_date = (data.get("due_date") or "").strip()
    notes = (data.get("notes") or "").strip()
    gst_rate = float(data.get("gst_rate") or 9)

    items = data.get("items") or []
    # Validate basics
    errors = {}
    if not invoice_number:
        errors["invoice_number"] = "Invoice number is required"
    if not issue_date:
        errors["issue_date"] = "Issue date is required"
    if not due_date:
        errors["due_date"] = "Due date is required"

    if client_mode == "saved":
        if not client_id:
            errors["client"] = "Please select a client"
    else:
        if not oneoff_name:
            errors["client"] = "Please enter a one-off client name"

    valid_items = []
    for it in items:
        desc = (it.get("description") or "").strip()
        if not desc:
            continue
        try:
            qty = float(it.get("quantity") or 0)
            unit = float(it.get("unit_price") or 0)
        except Exception:
            continue
        if qty <= 0:
            qty = 1.0
        line_total = qty * unit
        valid_items.append({"description": desc, "quantity": qty, "unit_price": unit, "line_total": line_total})

    if len(valid_items) == 0:
        errors["items"] = "Add at least one line item"

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    db = get_db()

    # Bill-to snapshot (preserves data even if client changes later)
    bill_to = {"name": "", "email": "", "phone": "", "address": ""}
    linked_client_id = None
    if client_mode == "saved":
        row = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "errors": {"client": "Selected client not found"}}), 400
        bill_to["name"] = row["name"]
        bill_to["email"] = row["email"]
        bill_to["phone"] = row["phone"]
        bill_to["address"] = row["address"]
        linked_client_id = row["id"]
    else:
        bill_to["name"] = oneoff_name

    subtotal = sum(i["line_total"] for i in valid_items)
    gst_amount = subtotal * (gst_rate / 100.0)
    total_amount = subtotal + gst_amount

    try:
        cur = db.execute(
            """
            INSERT INTO invoices (
                client_id, bill_to_name, bill_to_email, bill_to_phone, bill_to_address,
                invoice_number, currency, issue_date, due_date, notes,
                gst_rate, subtotal, gst_amount, total_amount, status, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """,
            (
                linked_client_id,
                bill_to["name"], bill_to["email"], bill_to["phone"], bill_to["address"],
                invoice_number, currency, issue_date, due_date, notes,
                gst_rate, subtotal, gst_amount, total_amount,
                "draft",
            ),
        )
        invoice_id = cur.lastrowid
        for it in valid_items:
            db.execute(
                """
                INSERT INTO invoice_items (invoice_id, description, quantity, unit_price, line_total)
                VALUES (?,?,?,?,?)
                """,
                (invoice_id, it["description"], it["quantity"], it["unit_price"], it["line_total"]),
            )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "errors": {"invoice_number": "Invoice number already exists"}}), 400

    row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    return jsonify({"ok": True, "invoice": _invoice_to_dict(row)})


# -------------------------
# AI PO / Quote reader (PDF + TXT)
# -------------------------
NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

def _singularize(word: str) -> str:
    w = (word or "").strip().lower()
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("es"):
        return w[:-2]
    if len(w) > 2 and w.endswith("s"):
        return w[:-1]
    return w

def _parse_qty(token: str):
    t = (token or "").strip().lower()
    if t.isdigit():
        return float(t)
    if t in NUMBER_WORDS:
        return float(NUMBER_WORDS[t])
    return None


def _normalize_text(s: str) -> str:
    """Normalize a catalogue / extracted name for forgiving matching.
    - lowercase
    - remove punctuation
    - map number-words to digits (one -> 1)
    - singularize simple plurals (apples -> apple)
    """
    s = (s or "").strip().lower()
    if not s:
        return ""

    # Keep letters/numbers/spaces only
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    parts = []
    for w in s.split():
        # number word -> digit string
        if w in NUMBER_WORDS:
            w = str(NUMBER_WORDS[w])
        # singularize tokens to handle plurals
        w = _singularize(w)
        parts.append(w)

    return " ".join(parts)

# =========================
# AI (Vision-capable LLM) helper
# =========================
def _openai_get_output_text(resp_json: dict) -> str:
    """Extracts aggregated text from a Responses API JSON payload (no SDK)."""
    try:
        # SDKs expose output_text, but raw JSON may not.
        if isinstance(resp_json.get("output_text"), str) and resp_json["output_text"].strip():
            return resp_json["output_text"].strip()
    except Exception:
        pass

    out_chunks = []
    for item in (resp_json.get("output") or []):
        if not isinstance(item, dict):
            continue
        for c in (item.get("content") or []):
            if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                t = c.get("text")
                if isinstance(t, str) and t.strip():
                    out_chunks.append(t.strip())
    return "\n".join(out_chunks).strip()

def _openai_extract_items_from_image(image_bytes: bytes, mime: str, catalogue_items):
    """Use OpenAI vision model to extract (name, quantity) pairs from an uploaded PO/quote image."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None  # caller decides fallback

    model = (os.getenv("OPENAI_VISION_MODEL") or "gpt-4.1-mini").strip()

    # Keep the catalogue hint reasonably small to avoid huge prompts.
    cat_hint = "\n".join(
        f"- {c['name']} (SKU {c['sku']})"
        for c in (catalogue_items or [])[:200]
        if (c.get("name") or "").strip()
    )

    prompt = (
        "You are reading a Purchase Order / quotation image.\n"
        "Extract the LINE ITEMS only (ignore totals, tax, shipping, addresses).\n"
        "Return STRICT JSON with this shape and nothing else:\n"
        "{\n"
        "  \"items\": [\n"
        "    {\"name\": \"<item name as written>\", \"quantity\": <number>}\n"
        "  ]\n"
        "}\n"
        "If quantity is missing, assume 1.\n"
        "If the document is not an order/quote or has no line items, return {\"items\": []}.\n"
        "\n"
        "Catalogue (match items to these names if possible, but still output what you see):\n"
        f"{cat_hint}"
    )

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    payload = {
        "model": model,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url},
            ],
        }],
        "max_output_tokens": 900,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

    out_text = _openai_get_output_text(resp)
    if not out_text:
        return None

    # Strip accidental code fences
    cleaned = out_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    try:
        obj = json.loads(cleaned)
    except Exception:
        # Try to salvage first JSON object in the text
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None

    items = obj.get("items")
    if not isinstance(items, list):
        return None

    norm = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = (it.get("name") or "").strip()
        if not name:
            continue
        qty = it.get("quantity", 1)
        try:
            qty = float(qty)
        except Exception:
            qty = 1.0
        qty = max(1.0, min(qty, 999.0))
        norm.append({"name": name, "quantity": qty})
    return norm


def _extract_text_from_pdf(path: str) -> str:
    parts = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                txt = p.extract_text() or ""
                if txt.strip():
                    parts.append(txt)
    except Exception:
        return ""
    return "\n".join(parts).strip()

def _extract_text_from_upload(saved_path: str, filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()

    if ext == ".txt":
        try:
            with open(saved_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception:
            return ""

    if ext == ".pdf":
        return _extract_text_from_pdf(saved_path)

    # Images (PNG/JPG): OCR via system tesseract (no Pillow dependency)
    if ext in [".png", ".jpg", ".jpeg"]:
        try:
            # "stdout" makes tesseract print recognized text to stdout
            out = subprocess.check_output(
                ["tesseract", saved_path, "stdout", "--psm", "6"],
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            return (out or "").strip()
        except Exception:
            return ""

    return ""


def _get_catalogue_for_matching():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, sku, category, unit_price FROM catalogue_items ORDER BY name"
    ).fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "name": (r["name"] or "").strip(),
            "name_l": (r["name"] or "").strip().lower(),
            "sku": (r["sku"] or "").strip(),
            "category": (r["category"] or "").strip(),
            "unit_price": float(r["unit_price"] or 0),
            "norm": _normalize_text(r["name"] or ""),
        })
    return items

def _match_name_to_catalogue(token_name: str, catalogue_items):
    """Best-effort match of an extracted token to a catalogue item.

    Supports:
    - apple vs apples (singularization)
    - one vs 1 (number-word normalization)
    - minor punctuation/spacing differences (normalization)
    - fuzzy matching for near-misses
    """
    from rapidfuzz import process, fuzz

    needle = _normalize_text(token_name)
    if not needle:
        return None, 0

    # Exact normalized match first
    for c in catalogue_items:
        if c.get("norm") == needle:
            return c, 100

    # Fuzzy match on normalized names (token_set_ratio is robust to word order/noise)
    norms = [c.get("norm", "") for c in catalogue_items]
    if not norms:
        return None, 0

    best = process.extractOne(needle, norms, scorer=fuzz.token_set_ratio)
    if not best:
        return None, 0

    _norm, score, idx = best[0], int(best[1]), best[2]

    # Keep this reasonably strict to avoid wrong matches when catalogue items are similar.
    # (OCR/PO text is noisy, so don't make it *too* strict.)
    if score < 80:
        return None, score

    return catalogue_items[idx], score

def _match_line_to_catalogue(line_text: str, catalogue_items):
    """Match a *full line* of text to the most likely catalogue item.

    PO/quote lines are often multi-word (e.g. "2 x Web Design Package") and OCR
    introduces noise. This function is more robust than single-token matching.
    """
    from rapidfuzz import process, fuzz

    needle = _normalize_text(line_text)
    if not needle:
        return None, 0

    norms = [c.get("norm", "") for c in (catalogue_items or [])]
    if not norms:
        return None, 0

    best = process.extractOne(needle, norms, scorer=fuzz.token_set_ratio)
    if not best:
        return None, 0

    _norm, score, idx = best[0], int(best[1]), best[2]

    # Lines contain extra tokens (currency, unit, etc.) so allow a slightly lower threshold.
    if score < 72:
        return None, score

    return catalogue_items[idx], score

def _extract_line_items_from_text(raw_text: str, catalogue_items):
    text = (raw_text or "").strip()
    if not text:
        return []

    # Strategy (robust for real-world POs/quotes and OCR noise):
    # 1) Split into lines.
    # 2) Detect quantity patterns (e.g. "2", "2x", "Qty: 2", "two").
    # 3) Remove obvious qty/price tokens and fuzzy-match the remaining line to catalogue items.

    qty_re = re.compile(
        r"(?i)(?:^|\b)(?:qty\s*[:#-]?\s*)?(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(?:\s*(?:x|pcs?|units?)\b)?"
    )

    items = []
    for raw_line in text.splitlines():
        line = (raw_line or "").strip()
        if not line:
            continue

        low = line.lower()
        # Skip obvious non-line-item lines
        if any(k in low for k in ["subtotal", "total", "gst", "tax", "shipping", "address", "invoice", "quotation", "quote", "date"]):
            continue

        qty = 1.0
        m = qty_re.search(line)
        if m:
            qty = _parse_qty(m.group(1)) or 1.0

        # Remove qty-ish fragments + numbers/currency so matching focuses on the item name
        line_wo_qty = qty_re.sub(" ", line)
        line_wo_qty = re.sub(r"(?i)\b(sgd|usd|s\$|\$)\b", " ", line_wo_qty)
        line_wo_qty = re.sub(r"\b\d+(?:\.\d+)?\b", " ", line_wo_qty)
        line_wo_qty = re.sub(r"[^a-zA-Z0-9\s]", " ", line_wo_qty)
        line_wo_qty = re.sub(r"\s+", " ", line_wo_qty).strip()

        cat, score = _match_line_to_catalogue(line_wo_qty or line, catalogue_items)

        # Last resort: try a couple of tokens
        if not cat:
            toks = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", line)
            toks = sorted(toks, key=len, reverse=True)
            for t in toks[:3]:
                cat, score = _match_name_to_catalogue(t, catalogue_items)
                if cat:
                    break

        if not cat:
            continue

        rate = float(cat["unit_price"] or 0)
        desc = cat["name"]
        matched_sku = cat["sku"]
        confidence = int(score)

        qty = max(1.0, min(float(qty), 999.0))
        rate = max(0.0, min(float(rate), 999999.0))
        amount = round(qty * rate, 2)

        items.append({
            "description": desc,
            "quantity": qty,
            "rate": rate,
            "amount": amount,
            "matched_sku": matched_sku,
            "confidence": confidence,
        })

    # Deduplicate by description (sum qty) to avoid repeated matches in a sentence
    merged = {}
    for it in items:
        key = (it["matched_sku"] or it["description"]).lower()
        if key not in merged:
            merged[key] = it
        else:
            merged[key]["quantity"] = merged[key]["quantity"] + it["quantity"]
            merged[key]["amount"] = round(merged[key]["quantity"] * merged[key]["rate"], 2)

    return list(merged.values())

@app.post("/api/po-reader")
def po_reader_api():
    # Upload PO / Quote (PDF/TXT/Image) -> extract line items -> match to catalogue
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    filename = f.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".pdf", ".txt", ".png", ".jpg", ".jpeg"]:
        return jsonify({"ok": False, "error": "Unsupported file type. Upload PDF, TXT, PNG, or JPG."}), 400

    # Save to temp
    tmp_dir = os.path.join(BASE_DIR, "_uploads_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
    saved_path = os.path.join(tmp_dir, f"{datetime.now().timestamp()}_{safe_name}")
    f.save(saved_path)

    try:
        catalogue_items = _get_catalogue_for_matching()

        # 1) For images: prefer Vision-capable LLM (if OPENAI_API_KEY is configured)
        if ext in [".png", ".jpg", ".jpeg"]:
            try:
                with open(saved_path, "rb") as imgf:
                    img_bytes = imgf.read()
            except Exception:
                img_bytes = b""

            mime = "image/png" if ext == ".png" else "image/jpeg"
            extracted = _openai_extract_items_from_image(img_bytes, mime, catalogue_items) if img_bytes else None

            # Fallback: OCR (requires tesseract installed) -> then regex text parse
            raw_text = ""
            if extracted is None:
                raw_text = _extract_text_from_upload(saved_path, filename)

                if not raw_text:
                    return jsonify({
                        "ok": False,
                        "error": "Could not read text from the image. Tip: set OPENAI_API_KEY for Vision extraction, or install Tesseract OCR and retry."
                    }), 400
            else:
                # Convert extracted {name, quantity} to matched invoice line items
                line_items = []
                for ex in extracted:
                    cat, score = _match_name_to_catalogue(ex.get("name",""), catalogue_items)
                    if not cat:
                        continue
                    qty = float(ex.get("quantity") or 1.0)
                    rate = float(cat["unit_price"] or 0)
                    qty = max(1.0, min(qty, 999.0))
                    rate = max(0.0, min(rate, 999999.0))
                    line_items.append({
                        "description": cat["name"],
                        "quantity": qty,
                        "rate": rate,
                        "amount": round(qty * rate, 2),
                        "matched_sku": cat["sku"],
                        "confidence": int(score),
                    })

                # Merge duplicates
                merged = {}
                for it in line_items:
                    key = (it["matched_sku"] or it["description"]).lower()
                    if key not in merged:
                        merged[key] = it
                    else:
                        merged[key]["quantity"] = merged[key]["quantity"] + it["quantity"]
                        merged[key]["amount"] = round(merged[key]["quantity"] * merged[key]["rate"], 2)

                return jsonify({"ok": True, "line_items": list(merged.values())})

            # If we got here, we have raw_text via OCR fallback
            line_items = _extract_line_items_from_text(raw_text, catalogue_items)
            if not line_items:
                return jsonify({
                    "ok": False,
                    "error": "No catalogue items detected in the image text. Try a clearer image, or set OPENAI_API_KEY for Vision extraction."
                }), 400
            return jsonify({"ok": True, "line_items": line_items})

        # 2) PDF/TXT: extract text (pdfplumber for text-based PDFs)
        raw_text = _extract_text_from_upload(saved_path, filename)
        if not raw_text:
            return jsonify({
                "ok": False,
                "error": "Could not extract text. Upload a text-based PDF/TXT. For scanned PDFs, convert to image or enable Vision extraction via OPENAI_API_KEY."
            }), 400

        # Deterministic catalogue matching from extracted text
        line_items = _extract_line_items_from_text(raw_text, catalogue_items)

        # Optional: if deterministic parsing finds nothing, try a text LLM pass (no vision needed)
        if not line_items and os.getenv("OPENAI_API_KEY", "").strip():
            # Simple text-only prompt (still goes through Responses API, but without images)
            model = (os.getenv("OPENAI_TEXT_MODEL") or os.getenv("OPENAI_VISION_MODEL") or "gpt-4.1-mini").strip()
            prompt = (
                "You are reading a Purchase Order / quotation TEXT.\n"
                "Extract the LINE ITEMS only (ignore totals, tax, shipping, addresses).\n"
                "Return STRICT JSON: {\"items\": [{\"name\": \"...\", \"quantity\": 1}]} and nothing else.\n"
                "If quantity is missing, assume 1.\n"
                "\n"
                "TEXT:\n"
                + raw_text[:12000]
            )
            payload = {
                "model": model,
                "input": [{
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }],
                "max_output_tokens": 900,
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY').strip()}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    resp = json.loads(r.read().decode("utf-8"))
                out_text = _openai_get_output_text(resp)
                cleaned = (out_text or "").strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
                    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
                obj = json.loads(cleaned) if cleaned else {}
                items = obj.get("items") if isinstance(obj, dict) else None
                if isinstance(items, list):
                    tmp = []
                    for ex in items:
                        if not isinstance(ex, dict):
                            continue
                        cat, score = _match_name_to_catalogue(ex.get("name",""), catalogue_items)
                        if not cat:
                            continue
                        qty = ex.get("quantity", 1)
                        try:
                            qty = float(qty)
                        except Exception:
                            qty = 1.0
                        qty = max(1.0, min(qty, 999.0))
                        rate = float(cat["unit_price"] or 0)
                        tmp.append({
                            "description": cat["name"],
                            "quantity": qty,
                            "rate": rate,
                            "amount": round(qty * rate, 2),
                            "matched_sku": cat["sku"],
                            "confidence": int(score),
                        })
                    # Merge duplicates
                    merged = {}
                    for it in tmp:
                        key = (it["matched_sku"] or it["description"]).lower()
                        if key not in merged:
                            merged[key] = it
                        else:
                            merged[key]["quantity"] = merged[key]["quantity"] + it["quantity"]
                            merged[key]["amount"] = round(merged[key]["quantity"] * merged[key]["rate"], 2)
                    line_items = list(merged.values())
            except Exception:
                pass

        if not line_items:
            return jsonify({
                "ok": False,
                "error": "No catalogue items detected. Upload a PO/quote that contains item names from your Catalogue, or add items manually."
            }), 400

        return jsonify({"ok": True, "line_items": line_items})
    finally:
        # Clean up temp file
        try:
            os.remove(saved_path)
        except Exception:
            pass


if __name__ == "__main__":
    app.run(debug=True)
