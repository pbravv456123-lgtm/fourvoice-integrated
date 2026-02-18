import re
import sqlite3
import statistics
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session, jsonify
from db import init_db, query_all, query_one, execute
from thefuzz import process, fuzz

app = Flask(__name__)
app.secret_key = "dev-key-change-later"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{6,20}$")

init_db()

# Ensure user_id=1 exists
existing = query_one("SELECT id FROM users WHERE id = 1;")
if existing is None:
    execute(
        "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?);",
        (1, "Default User", "default@example.com", "x"),
    )

def validate_client_fields(client_name: str, email: str, phone: str, address: str):
    errors = []
    client_name = (client_name or "").strip()
    email = (email or "").strip()
    phone = (phone or "").strip()
    address = (address or "").strip()

    if not client_name:
        errors.append("Client name is required.")
    elif len(client_name) > 80:
        errors.append("Client name must be 80 characters or less.")

    if email:
        if len(email) > 120:
            errors.append("Email must be 120 characters or less.")
        elif not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")

    if phone:
        if not PHONE_RE.match(phone):
            errors.append("Phone can only include numbers and symbols like + ( ) - and spaces.")
        elif len(phone) > 20:
            errors.append("Phone must be 20 characters or less.")

    if address and len(address) > 200:
        errors.append("Address must be 200 characters or less.")

    return errors, client_name, email, phone, address

@app.get("/")
def home():
    return render_template("home.html", title="Dashboard")

# --- CLIENT ROUTES ---

@app.get("/clients")
def clients_list():
    clients = query_all("SELECT * FROM clients WHERE user_id = ? ORDER BY id DESC;", (1,))
    return render_template("clients_list.html", title="Clients", clients=clients)

@app.route("/clients/new", methods=["GET", "POST"])
def clients_create():
    if request.method == "POST":
        errors, client_name, email, phone, address = validate_client_fields(
            request.form.get("client_name"), request.form.get("email"), 
            request.form.get("phone"), request.form.get("address")
        )
        if errors:
            for e in errors: flash(e, "danger")
            return render_template("clients_form.html", title="Add client", form={"client_name": client_name, "email": email, "phone": phone, "address": address}, mode="create")
        try:
            execute("INSERT INTO clients (user_id, client_name, email, phone, address) VALUES (?, ?, ?, ?, ?);", (1, client_name, email or None, phone or None, address or None))
        except sqlite3.IntegrityError:
            flash("A client with this email already exists.", "danger")
            return render_template("clients_form.html", title="Add client", form={"client_name": client_name, "email": email, "phone": phone, "address": address}, mode="create")
        flash("Client added successfully.", "success")
        return redirect(url_for("clients_list"))
    return render_template("clients_form.html", title="Add client", form={"client_name": "", "email": "", "phone": "", "address": ""}, mode="create")

@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def clients_edit(client_id: int):
    client = query_one("SELECT * FROM clients WHERE id = ? AND user_id = ?;", (client_id, 1))
    if client is None: abort(404)
    if request.method == "POST":
        errors, client_name, email, phone, address = validate_client_fields(
            request.form.get("client_name"), request.form.get("email"), 
            request.form.get("phone"), request.form.get("address")
        )
        if errors:
            for e in errors: flash(e, "danger")
            return render_template("clients_form.html", title="Edit client", form={"client_name": client_name, "email": email, "phone": phone, "address": address}, mode="edit", client_id=client_id)
        execute("UPDATE clients SET client_name = ?, email = ?, phone = ?, address = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?;", (client_name, email or None, phone or None, address or None, client_id, 1))
        flash("Client updated successfully.", "success")
        return redirect(url_for("clients_list"))
    return render_template("clients_form.html", title="Edit client", form={"client_name": client["client_name"], "email": client["email"] or "", "phone": client["phone"] or "", "address": client["address"] or ""}, mode="edit", client_id=client_id)

@app.post("/clients/<int:client_id>/delete")
def clients_delete(client_id: int):
    execute("DELETE FROM clients WHERE id = ? AND user_id = ?;", (client_id, 1))
    flash("Client deleted successfully.", "success")
    return redirect(url_for("clients_list"))

# --- CATALOGUE ---
def query_db(query, args=(), one=False):
    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row  # This allows us to access columns by name
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# You also need this one for your ADD/EDIT/DELETE actions
def execute(query, args=()):
    conn = sqlite3.connect('app.db')
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    conn.close()

@app.route('/catalogue')
def catalogue():
    products = query_all("SELECT * FROM products")
    return render_template('catalogue.html', title="Catalogue", products=products)

@app.route('/search_catalogue')
def search_catalogue():
    query = request.args.get('query', '')
    # Use wildcards % for fuzzy matching in SQL
    search_term = f"%{query}%"
    
    # Select ALL columns so the frontend has the data it needs
    results = query_db("""
        SELECT id, sku, name, description, category, price 
        FROM products 
        WHERE name LIKE ? OR sku LIKE ? OR description LIKE ?
        ORDER BY category, name
    """, [search_term, search_term, search_term])

    # Convert rows to a list of dictionaries for JSON
    return jsonify({"results": [dict(row) for row in results]})

@app.route('/catalogue/edit', methods=['POST'])
def edit_product():
    id = request.form.get('id')
    name = request.form.get('name')
    sku = request.form.get('sku')
    description = request.form.get('description')
    category = request.form.get('category')
    price = request.form.get('price')
    
    execute("UPDATE products SET name=?, sku=?, description=?, category=?, price=? WHERE id=?", 
            (name, sku, description, category, price, id))
    return redirect(url_for('catalogue'))

from flask import request, redirect, url_for

@app.route('/catalogue/add', methods=['POST'])
def add_product():
    # 1. Grab the info from the form
    name = request.form.get('name')
    sku = request.form.get('sku')
    description = request.form.get('description')
    category = request.form.get('category')
    price = request.form.get('price')

    # 2. Use your existing 'execute' helper function to save to app.db
    # This automatically handles the connection and the commit!
    execute("INSERT INTO products (name, sku, description, category, price) VALUES (?, ?, ?, ?, ?)", 
            (name, sku, description, category, price))

    # 3. Send the user back to the catalogue
    flash("Product added successfully!", "success")
    return redirect(url_for('catalogue'))

@app.route('/catalogue/delete/<int:id>', methods=['POST'])
def delete_product(id):
    execute("DELETE FROM products WHERE id=?", (id,))
    return redirect(url_for('catalogue'))

# --- AUDIT LOG (THE FIX) ---

@app.route('/audit-log')
def audit_log():
    # 1. Fetch the real logs from DB
    raw_logs = query_all("SELECT * FROM audit_logs ORDER BY id ASC")
    
    # 2. Group them so they appear inside ONE specific invoice dropdown
    invoices = {
        "INV-2024-094": {
            "client": "Tech Solutions Pte Ltd",
            "amount": 9200.00,
            "status": "Sent",
            "logs": raw_logs
        }
    }
    
    anomalies = session.get('anomalies', [])
    return render_template('audit_log.html', title="Audit Log", invoices=invoices, anomalies=anomalies)

@app.route('/auditlog/scan')
def audit_scan():
    logs = query_all("SELECT * FROM audit_logs")
    amounts = [log['amount'] for log in logs if log['amount'] > 0]
    
    anomalies = []
    if len(amounts) >= 2:
        avg = statistics.mean(amounts)
        stdev = statistics.stdev(amounts)
        threshold = avg + (2 * stdev)
        anomalies = [log['id'] for log in logs if log['amount'] > threshold]
    
    session['anomalies'] = anomalies
    flash("AI Scan complete. Unusual activities highlighted.", "warning")
    return redirect(url_for('audit_log'))

# --- HELPER ROUTE TO FIX DATA ---


if __name__ == '__main__':
    app.run(debug=True)