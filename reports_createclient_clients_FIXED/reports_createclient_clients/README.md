# FourVoice (Clients + Create Invoice + Navbar) — Flask + SQLite

## Run locally

### 1) Create venv + install
```bash
cd fourvoice
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2) Run
```bash
python app.py
```

Open:
- Clients: http://127.0.0.1:5000/clients
- Create Invoice: http://127.0.0.1:5000/create-invoice

Database file:
- `app.db` (auto-created)

## What’s included
- Sidebar/navbar shared via `templates/base.html`
- Clients page (cards + search + add/edit/delete + invoice history modal)
- Create Invoice page (saved client picker OR one-off client, line items, GST, draft save)
- API endpoints under `/api/*` (clients + invoices)

