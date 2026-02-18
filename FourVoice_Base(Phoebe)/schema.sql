PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,

  client_name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  address TEXT,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,

  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Prevent duplicate client emails for the same user (but allow NULL emails)
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_user_email
ON clients(user_id, email)
WHERE email IS NOT NULL;

-- 3. Products/Catalogue Table
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    price REAL NOT NULL
);

-- Clean old data and insert screenshot items
DELETE FROM products;

-- Services
INSERT INTO products (sku, name, description, category, price) VALUES 
('WEB-001', 'Web Development Service', 'Full-stack web development', 'Services', 150.00),
('DES-001', 'UI/UX Design', 'Interface and experience design', 'Services', 120.00),
('SEO-001', 'SEO Optimization', 'Search engine optimization service', 'Services', 300.00),
('CNT-001', 'Content Writing', 'Professional content writing', 'Services', 80.00),
('HST-001', 'Hosting Service', 'Cloud hosting solution', 'Services', 250.00);

-- Consulting
INSERT INTO products (sku, name, description, category, price) VALUES 
('CON-001', 'Consulting Hour', 'Business consulting services', 'Consulting', 200.00),
('STR-001', 'Strategy Session', 'Business strategy consulting', 'Consulting', 400.00);

-- Packages
INSERT INTO products (sku, name, description, category, price) VALUES 
('MNT-001', 'Monthly Maintenance', 'Website maintenance package', 'Packages', 500.00),
('SUP-001', 'Premium Support Package', '24/7 priority support', 'Packages', 800.00);

-- Products
INSERT INTO products (sku, name, description, category, price) VALUES 
('MKT-001', 'Marketing Kit', 'Complete marketing materials', 'Products', 350.00);

-- ... keep your CREATE TABLE statements exactly as they are ...

-- 4. Audit Log Table
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  amount REAL NOT NULL,
  timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

DELETE FROM audit_logs;

-- REFRESHED Sample Audit Logs to trigger all Timeline Icons
-- We use keywords that your HTML 'if' logic is looking for
INSERT INTO audit_logs (action, amount, timestamp) VALUES ('Invoice Created', 9200.00, '2026-01-22 09:30:00');
INSERT INTO audit_logs (action, amount, timestamp) VALUES ('Edited', 9200.00, '2026-01-22 10:15:00');
INSERT INTO audit_logs (action, amount, timestamp) VALUES ('Submitted for Approval', 9200.00, '2026-01-22 10:45:00');
INSERT INTO audit_logs (action, amount, timestamp) VALUES ('Approved', 9200.00, '2026-01-22 14:30:00');
INSERT INTO audit_logs (action, amount, timestamp) VALUES ('Sent to Client', 9200.00, '2026-01-22 14:45:00');
INSERT INTO audit_logs (action, amount, timestamp) VALUES ('Viewed by Client', 9200.00, '2026-01-23 09:15:00');

-- Add one outlier to test the AI Scan logic
INSERT INTO audit_logs (action, amount, timestamp) VALUES ('High Value Invoice Created', 25000.00, '2026-01-23 11:00:00');