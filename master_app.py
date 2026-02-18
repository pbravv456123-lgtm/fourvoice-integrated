import os
import io
import re
import sqlite3
import subprocess
import base64
import json
import urllib.request
import statistics
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, session, g, jsonify, send_file, abort, flash
from flask_sqlalchemy import SQLAlchemy

# Make sure you have installed: pip install flask-sqlalchemy reportlab rapidfuzz thefuzz pdfplumber

# ==========================================
# 1. APP CONFIGURATION & UNIFIED SETUP
# ==========================================
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'app.db')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'fourvoice_master_secret_key' 

db = SQLAlchemy(app)

# ==========================================
# 2. DATABASE MODELS & RAW SQL HELPERS
# ==========================================

# SUYASHA'S SQLALCHEMY MODEL
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(100))
    selection = db.Column(db.String(50))
    business_type = db.Column(db.String(50))
    country = db.Column(db.String(50))
    currency = db.Column(db.String(10))
    company_join_code = db.Column(db.String(50))

# SIQI & PHOEBE'S RAW SQLITE CONNECTION
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_exc):
    db_conn = g.pop("db", None)
    if db_conn is not None:
        db_conn.close()

def query_all(query, args=()):
    cur = get_db().execute(query, args)
    return cur.fetchall()

def query_one(query, args=()):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return rv[0] if rv else None

def execute_db(query, args=()):
    db_conn = get_db()
    cur = db_conn.cursor()
    cur.execute(query, args)
    db_conn.commit()
    return cur

def init_db():
    db_conn = get_db()
    db_conn.executescript("""
        PRAGMA foreign_keys = ON;
        
        -- Phoebe's Client Table (Modified to link with Suyasha's User)
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- Phoebe's Products Table
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, sku TEXT, description TEXT, category TEXT, price REAL
        );

        -- Phoebe's Audit Table
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT, amount REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Siqi's Invoice Tables
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NULL,
            bill_to_name TEXT NOT NULL,
            bill_to_email TEXT, bill_to_phone TEXT, bill_to_address TEXT,
            invoice_number TEXT NOT NULL UNIQUE,
            currency TEXT NOT NULL DEFAULT 'SGD',
            issue_date TEXT NOT NULL, due_date TEXT NOT NULL, notes TEXT,
            gst_rate REAL NOT NULL DEFAULT 9.0, subtotal REAL NOT NULL DEFAULT 0.0,
            gst_amount REAL NOT NULL DEFAULT 0.0, total_amount REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL, description TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1, unit_price REAL NOT NULL DEFAULT 0,
            line_total REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        );
    """)
    db_conn.commit()

# INITIALIZE EVERYTHING
with app.app_context():
    db.create_all() # Builds SQLAlchemy tables
    init_db()       # Builds Raw SQLite tables

# ==========================================
# 3. AUTHENTICATION MIDDLEWARE
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('signin'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# 4. SUYASHA'S AUTH & DASHBOARD ROUTES
# ==========================================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('landing'))
    return redirect(url_for('signup'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    errors = {}
    full_name = email = ""
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not full_name: errors['full_name'] = "Name is required"
        if not email: errors['email'] = "Email is required"
            
        if not errors:
            try:
                existing_user = User.query.filter_by(email=email).first()
                if existing_user:
                    errors['email'] = "This email is already registered."
                else:
                    new_user = User(full_name=full_name, email=email, password=password)
                    db.session.add(new_user)
                    db.session.commit()
                    session['user_id'] = new_user.id
                    session['user_email'] = new_user.email
                    session['user_name'] = new_user.full_name
                    return redirect(url_for('verify_email'))
            except Exception as e:
                db.session.rollback()
                errors['db'] = "System error, please try again."

    return render_template('SIGNUP_index.html', full_name=full_name, email=email, errors=errors)

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.password == password:
            session['user_id'] = user.id
            session['user_email'] = user.email
            session['user_name'] = user.full_name
            return redirect(url_for('landing'))
        else:
            flash("Invalid credentials", "danger")

    return render_template('SIGNIN_index.html')

@app.route('/verify-email')
@login_required
def verify_email():
    return render_template('EMAIL_index.html', user_email=session.get('user_email'))

@app.route('/setup', methods=['GET', 'POST'])
@login_required
def setup():
    if request.method == 'POST':
        user = User.query.get(session['user_id'])
        if user:
            mode = request.form.get('mode') 
            if mode == 'create':
                user.selection = 'Create Company'
                user.business_type = request.form.get('business_type')
                user.country = request.form.get('country')
                user.currency = request.form.get('currency')
            else:
                user.selection = 'Join Existing Company'
                user.company_join_code = request.form.get('join_code')
            db.session.commit()
        return redirect(url_for('landing'))
    return render_template('SETUP_index.html')

@app.route('/landing')
@login_required
def landing():
    # Use Suyasha's Dashboard
    initials = "".join([n[0] for n in session.get('user_name', 'Guest').split()[:2]]).upper()
    return render_template('LANDING_index.html', user_initial=initials, user_email=session.get('user_email'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('signin'))


# ==========================================
# 5. PHOEBE'S CLIENTS, CATALOGUE & AUDIT 
# ==========================================
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{6,20}$")

def validate_client_fields(client_name, email, phone, address):
    errors = []
    client_name = (client_name or "").strip()
    if not client_name: errors.append("Client name is required.")
    if email and not EMAIL_RE.match(email): errors.append("Please enter a valid email address.")
    if phone and not PHONE_RE.match(phone): errors.append("Invalid phone format.")
    return errors, client_name, email, phone, address

@app.route("/clients")
@login_required
def clients_list():
    clients = query_all("SELECT * FROM clients WHERE user_id = ? ORDER BY id DESC;", (session['user_id'],))
    return render_template("clients_list.html", title="Clients", clients=clients)

@app.route("/clients/new", methods=["GET", "POST"])
@login_required
def clients_create():
    if request.method == "POST":
        errors, name, email, phone, addr = validate_client_fields(
            request.form.get("client_name"), request.form.get("email"), 
            request.form.get("phone"), request.form.get("address")
        )
        if errors:
            for e in errors: flash(e, "danger")
            return render_template("clients_form.html", form={"client_name": name})
        
        execute_db("INSERT INTO clients (user_id, client_name, email, phone, address) VALUES (?, ?, ?, ?, ?);", 
                   (session['user_id'], name, email, phone, addr))
        flash("Client added successfully.", "success")
        return redirect(url_for("clients_list"))
    return render_template("clients_form.html", form={"client_name": ""}, mode="create")

@app.route('/catalogue')
@login_required
def catalogue():
    products = query_all("SELECT * FROM products")
    return render_template('catalogue.html', title="Catalogue", products=products)

@app.route('/catalogue/add', methods=['POST'])
@login_required
def add_product():
    execute_db("INSERT INTO products (name, sku, description, category, price) VALUES (?, ?, ?, ?, ?)", 
            (request.form.get('name'), request.form.get('sku'), request.form.get('description'), 
             request.form.get('category'), request.form.get('price')))
    return redirect(url_for('catalogue'))

@app.route('/audit-log')
@login_required
def audit_log():
    raw_logs = query_all("SELECT * FROM audit_logs ORDER BY id ASC")
    anomalies = session.get('anomalies', [])
    return render_template('audit_log.html', title="Audit Log", anomalies=anomalies, logs=raw_logs)

@app.route('/auditlog/scan')
@login_required
def audit_scan():
    logs = query_all("SELECT * FROM audit_logs")
    amounts = [log['amount'] for log in logs if log['amount'] > 0]
    anomalies = []
    if len(amounts) >= 2:
        threshold = statistics.mean(amounts) + (2 * statistics.stdev(amounts))
        anomalies = [log['id'] for log in logs if log['amount'] > threshold]
    session['anomalies'] = anomalies
    return redirect(url_for('audit_log'))


# ==========================================
# 6. SIQI'S INVOICES & AI PO READER
# ==========================================

@app.route("/create-invoice")
@login_required
def create_invoice_page():
    return render_template("create_invoice.html", page="create_invoice")

@app.route("/invoices")
@login_required
def invoices_page():
    invoice_id = request.args.get("invoice_id")
    if invoice_id and str(invoice_id).isdigit():
        return redirect(url_for("invoice_preview_page", invoice_id=int(invoice_id)))
    inv = query_one("SELECT id FROM invoices ORDER BY id DESC LIMIT 1")
    if inv:
        return redirect(url_for("invoice_preview_page", invoice_id=inv["id"]))
    return render_template("invoice_preview.html", page="invoices", invoice=None)

@app.route("/invoice-preview/<int:invoice_id>")
@login_required
def invoice_preview_page(invoice_id):
    inv = query_one("SELECT * FROM invoices WHERE id=?", (invoice_id,))
    if not inv: abort(404)
    items = query_all("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id ASC", (invoice_id,))
    
    invoice_data = {
        "id": inv["id"], "invoice_number": inv["invoice_number"],
        "issue_date": inv["issue_date"], "due_date": inv["due_date"],
        "gst_rate": inv["gst_rate"], "subtotal": inv["subtotal"],
        "gst": inv["gst_amount"], "total": inv["total_amount"],
        "client_name": inv["bill_to_name"], "client_email": inv["bill_to_email"],
        "items": [{"description": r["description"], "quantity": r["quantity"], "unit_price": r["unit_price"]} for r in items]
    }
    return render_template("invoice_preview.html", invoice=invoice_data)

# --- SIQI'S APIs WIRED TO PHOEBE'S TABLES ---
@app.get("/api/clients")
@login_required
def api_list_clients():
    # Rewritten to read from Phoebe's table format
    rows = query_all("SELECT id, client_name as name, email, phone, address FROM clients WHERE user_id=? ORDER BY id DESC", (session['user_id'],))
    return jsonify({"clients": [dict(r) for r in rows]})

@app.get("/api/catalogue-items")
@login_required
def api_catalogue_items():
    # Rewritten to read from Phoebe's Products table
    rows = query_all("SELECT id, name, sku, category, description, price as unit_price FROM products ORDER BY id DESC")
    return jsonify({"items": [dict(r) for r in rows]})

@app.post("/api/invoices")
@login_required
def api_create_invoice():
    data = request.get_json(force=True, silent=True) or {}
    client_mode = data.get("client_mode")
    client_id = data.get("client_id")
    oneoff_name = data.get("oneoff_name", "").strip()

    valid_items = [{"description": i.get("description"), "quantity": float(i.get("quantity", 1)), 
                    "unit_price": float(i.get("unit_price", 0)), "line_total": float(i.get("quantity",1)) * float(i.get("unit_price",0))} 
                   for i in data.get("items", []) if i.get("description")]

    bill_to = {"name": "", "email": "", "phone": "", "address": ""}
    if client_mode == "saved":
        row = query_one("SELECT * FROM clients WHERE id=? AND user_id=?", (client_id, session['user_id']))
        bill_to.update({"name": row["client_name"], "email": row["email"], "phone": row["phone"], "address": row["address"]})
    else:
        bill_to["name"] = oneoff_name

    subtotal = sum(i["line_total"] for i in valid_items)
    gst_amount = subtotal * (float(data.get("gst_rate", 9)) / 100.0)
    
    cur = execute_db("""
        INSERT INTO invoices (client_id, bill_to_name, bill_to_email, bill_to_phone, bill_to_address,
            invoice_number, currency, issue_date, due_date, gst_rate, subtotal, gst_amount, total_amount) 
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (client_id if client_mode == 'saved' else None, bill_to["name"], bill_to["email"], bill_to["phone"], bill_to["address"],
          data.get("invoice_number"), data.get("currency", "SGD"), data.get("issue_date"), data.get("due_date"),
          data.get("gst_rate", 9), subtotal, gst_amount, subtotal + gst_amount))
    
    invoice_id = cur.lastrowid
    for it in valid_items:
        execute_db("INSERT INTO invoice_items (invoice_id, description, quantity, unit_price, line_total) VALUES (?,?,?,?,?)",
                   (invoice_id, it["description"], it["quantity"], it["unit_price"], it["line_total"]))
    
    return jsonify({"ok": True, "invoice_id": invoice_id})

# --- SIQI'S AI READER ---
def _get_catalogue_for_matching():
    # Pointed to Phoebe's Products table
    rows = query_all("SELECT id, name, sku, category, price as unit_price FROM products ORDER BY name")
    return [{"id": r["id"], "name": r["name"], "sku": r["sku"], "unit_price": r["unit_price"], "norm": re.sub(r"[^a-z0-9\s]+", " ", str(r["name"]).lower()).strip()} for r in rows]

@app.post("/api/po-reader")
@login_required
def po_reader_api():
    # (Siqi's original logic retained for file upload and parsing)
    f = request.files.get("file")
    if not f or not f.filename: return jsonify({"ok": False, "error": "No file"}), 400
    
    # Save temp file
    tmp_dir = os.path.join(BASE_DIR, "_uploads_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    saved_path = os.path.join(tmp_dir, f.filename)
    f.save(saved_path)

    try:
        catalogue_items = _get_catalogue_for_matching()
        # Minimal Fallback text extraction if API keys aren't set
        raw_text = ""
        if f.filename.endswith(".txt"):
            with open(saved_path, "r") as tf: raw_text = tf.read()
            
        # VERY basic regex matcher as fallback from Siqi's code
        line_items = []
        for line in raw_text.splitlines():
            for cat in catalogue_items:
                if cat["norm"] in line.lower():
                    line_items.append({
                        "description": cat["name"], "quantity": 1.0, 
                        "rate": cat["unit_price"], "amount": cat["unit_price"],
                        "matched_sku": cat["sku"], "confidence": 100
                    })
        return jsonify({"ok": True, "line_items": line_items})
    finally:
        if os.path.exists(saved_path): os.remove(saved_path)

if __name__ == "__main__":
    app.run(debug=True)
