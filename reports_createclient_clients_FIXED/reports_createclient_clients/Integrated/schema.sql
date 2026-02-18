PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'employee' CHECK (
    role IN ('admin', 'employee')
  ),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  client_name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  address TEXT,
  city TEXT,
  state TEXT,
  postal_code TEXT,
  country TEXT DEFAULT 'USA',
  company_type TEXT,
  industry TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  description TEXT NOT NULL,
  details TEXT,
  category TEXT,
  rate DECIMAL(10, 2) NOT NULL,
  is_active BOOLEAN DEFAULT 1,
  estimated_hours INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Updated: Only 4 statuses to match your CSS
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  client_id INTEGER,
  
  invoice_number TEXT NOT NULL UNIQUE,
  client_name TEXT NOT NULL,
  email TEXT NOT NULL,
  
  -- Status tracking
  status TEXT NOT NULL CHECK (
    status IN ('delivered', 'opened', 'pending', 'failed')
  ) DEFAULT 'pending',
  
  -- Failed reason (only for failed status)
  failed_reason TEXT,
  
  -- Approval tracking
  approval_status TEXT DEFAULT 'pending' CHECK (
    approval_status IN ('pending', 'approved', 'rejected', 'on-hold')
  ),
  approval_date TEXT,
  approved_by INTEGER,
  approval_reason TEXT,
  
  -- Dates for timeline tracking
  sent_date TEXT NOT NULL,
  delivered_date TEXT,
  failed_date TEXT,
  opened_date TEXT,
  resent_date TEXT,
  
  -- Financials
  subtotal DECIMAL(10, 2) DEFAULT 0.00,
  tax DECIMAL(10, 2) DEFAULT 0.00,
  total DECIMAL(10, 2) DEFAULT 0.00,
  
  -- Notes
  notes TEXT,
  
  -- Metadata
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
  FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS invoice_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL,
  service_id INTEGER,
  service_code TEXT NOT NULL,
  description TEXT NOT NULL,
  details TEXT,
  category TEXT,
  quantity INTEGER NOT NULL DEFAULT 1,
  rate DECIMAL(10, 2) NOT NULL,
  total DECIMAL(10, 2) NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
  FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL
);



-- Indexes
-- Ensures invoice numbers are unique for fast lookup and integrity
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_number
ON invoices(invoice_number);

-- Speeds up filtering invoices by status (e.g. pending, approved)
CREATE INDEX IF NOT EXISTS idx_invoices_status
ON invoices(status);

-- Optimizes queries that sort/filter invoices by sent date
CREATE INDEX IF NOT EXISTS idx_invoices_sent_date
ON invoices(sent_date);

-- Improves joins and lookups by client
CREATE INDEX IF NOT EXISTS idx_invoices_client
ON invoices(client_id);

-- Speeds up retrieval of line items for a given invoice
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice
ON invoice_items(invoice_id);

-- Enforces unique client email per user (ignores NULL emails)
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_user_email
ON clients(user_id, email)
WHERE email IS NOT NULL;

-- Ensures service codes are unique per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_services_user_code
ON services(user_id, code);

-- Application Settings Table
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  setting_key TEXT NOT NULL,
  setting_value TEXT,
  setting_type TEXT DEFAULT 'text' CHECK (
    setting_type IN ('text', 'boolean', 'number', 'json', 'password')
  ),
  description TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE(user_id, setting_key)
);

-- Index for fast settings lookup
CREATE INDEX IF NOT EXISTS idx_settings_user_key
ON settings(user_id, setting_key);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  category TEXT NOT NULL,
  price REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_products_category
ON products(category);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_number TEXT,
  client_name TEXT,
  action TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  created_by TEXT DEFAULT 'System',
  timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_invoice
ON audit_logs(invoice_number);

CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
ON audit_logs(timestamp);
