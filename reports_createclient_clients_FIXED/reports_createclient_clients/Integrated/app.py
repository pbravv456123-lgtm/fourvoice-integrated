import re
import sqlite3
import statistics
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify, send_file
from database import init_db, query_all, query_one, execute, get_conn
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import hmac
import socket
import ipaddress
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
# Set UTF-8 encoding for console output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
from flask_mail import Mail, Message
from dotenv import load_dotenv
from pdf_generator import generate_invoice_pdf
import hashlib
import base64
import traceback
from groq import Groq
import time

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = "dev-key-change-later" # Session encryption key

# Singapore timezone (UTC+8)
SINGAPORE_TZ = timezone(timedelta(hours=8))

def get_singapore_time():
    """Get current time in Singapore timezone"""
    return datetime.now(SINGAPORE_TZ).strftime('%Y-%m-%d %H:%M:%S')


def format_date_ddmmyyyy(date_value):
    """Convert common date values to dd/mm/yyyy for prompts and UI summaries."""
    if not date_value:
        return 'Not provided'

    value = str(date_value).strip()
    if not value:
        return 'Not provided'

    date_part = value.split(' ')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(date_part, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return date_part


def parse_invoice_date(date_value):
    """Parse invoice date values that may come as yyyy-mm-dd or dd/mm/yyyy."""
    if not date_value:
        return None

    value = str(date_value).strip()
    if not value:
        return None

    date_part = value.split(' ')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(date_part, fmt)
        except ValueError:
            continue
    return None


def is_future_date_false_positive(message_text):
    """True when AI feedback incorrectly flags future dates as an error."""
    text = str(message_text or '').strip().lower()
    if 'future' not in text:
        return False
    return 'invoice date' in text or 'due date' in text or 'date is in the future' in text


def is_due_before_false_positive(message_text, invoice_date_value, due_date_value):
    """True when message claims due date is before invoice date but parsed values are valid order."""
    text = str(message_text or '').strip().lower()
    if not text:
        return False

    mentions_due_before_invoice = (
        'due date' in text and 'invoice date' in text and (
            'before' in text or 'precedes' in text or 'earlier' in text
        )
    )
    if not mentions_due_before_invoice:
        return False

    parsed_invoice_date = parse_invoice_date(invoice_date_value)
    parsed_due_date = parse_invoice_date(due_date_value)
    if not parsed_invoice_date or not parsed_due_date:
        return False

    return parsed_due_date >= parsed_invoice_date


def parse_payment_terms_days(payment_terms_value, default_days=30):
    """Extract day count from terms such as 'Net 30'; fallback to default when unavailable."""
    terms_text = str(payment_terms_value or '').strip().lower()
    match = re.search(r'net\s*(\d+)', terms_text)
    if match:
        try:
            return max(0, int(match.group(1)))
        except ValueError:
            return default_days
    return default_days


def is_due_terms_false_positive(message_text, invoice_date_value, due_date_value, payment_terms_value='Net 30'):
    """True when AI claims due date violates payment terms but parsed dates satisfy required day gap."""
    text = str(message_text or '').strip().lower()
    if not text:
        return False

    parsed_invoice_date = parse_invoice_date(invoice_date_value)
    parsed_due_date = parse_invoice_date(due_date_value)
    if not parsed_invoice_date or not parsed_due_date:
        return False

    required_days = parse_payment_terms_days(payment_terms_value, default_days=30)
    actual_days = (parsed_due_date.date() - parsed_invoice_date.date()).days

    terms_claim_tokens = (
        'less than',
        'fewer than',
        'at least',
        'payment terms',
        'net ',
        'expected due date',
        'not meet',
        'does not meet'
    )
    if not any(token in text for token in terms_claim_tokens):
        return False

    if 'due date' not in text or 'invoice date' not in text:
        return False

    # If AI claims term mismatch while actual day difference satisfies required days, treat as false positive.
    return actual_days >= required_days

# Email Configuration (TurboSMTP)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'pro.eu.turbo-smtp.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))  # Default to 587 (non-SSL)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
# IMPORTANT: MAIL_DEFAULT_SENDER must be a valid email address, not the username!
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'no-reply@fourvoice.com')
app.config['MAIL_REPLY_TO'] = os.environ.get('MAIL_REPLY_TO', app.config['MAIL_DEFAULT_SENDER'])
app.config['APP_BASE_URL'] = os.environ.get('APP_BASE_URL', 'http://localhost:5000').rstrip('/')
app.config['APP_ENV'] = (os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or 'development').strip().lower()
app.config['EMAIL_STRICT_PRODUCTION_CHECKS'] = app.config['APP_ENV'] == 'production'

# Suppress email sending in test mode
app.config['MAIL_SUPPRESS_SEND'] = os.environ.get('TESTING', 'False').lower() == 'true'

mail = Mail(app)

# Check if email is properly configured
EMAIL_CONFIGURED = bool(app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD'])
if EMAIL_CONFIGURED:
    print("\n[OK] Email configuration loaded successfully:")
    print(f"   Server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
    print(f"   Username: {app.config['MAIL_USERNAME']}")
    print(f"   TLS Enabled: {app.config['MAIL_USE_TLS']}")
    print(f"   Suppress Send: {app.config['MAIL_SUPPRESS_SEND']}")
    if app.config['MAIL_SUPPRESS_SEND']:
        print("   [WARNING] TESTING mode enabled - emails will NOT be sent (MAIL_SUPPRESS_SEND=True)")
    print()
else:
    print("\n[WARNING] Email configuration not set. Set environment variables to enable email sending:")
    print("   MAIL_USERNAME - Your TurboSMTP Consumer Key")
    print("   MAIL_PASSWORD - Your TurboSMTP Consumer Secret")
    print("   MAIL_SERVER   - pro.eu.turbo-smtp.com")
    print("   MAIL_PORT     - 587 (non-SSL) or 465 (SSL)")
    print("   See TurboSMTP documentation for instructions.\n")

# Groq Configuration
groq_client = None
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', None)
print(f"[DEBUG] GROQ_API_KEY from environment: {bool(GROQ_API_KEY)}")
print(f"[DEBUG] GROQ_API_KEY value: {GROQ_API_KEY[:20] if GROQ_API_KEY else 'NOT SET'}")
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        openai_client = groq_client  # Keep openai_client variable for compatibility
        print("[OK] Groq API configured successfully")
    except Exception as e:
        print(f"[WARNING] Failed to initialize Groq: {e}")
        import traceback as tb
        tb.print_exc()
        groq_client = None
        openai_client = None
else:
    openai_client = None
    print("\n[WARNING] Groq API key not set. AI features will be disabled.")
    print("   Set GROQ_API_KEY environment variable to enable AI validation.\n")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$") #[^@\s]+ -> allows one or more characters that are NOT @ or whitespace

PHONE_COUNTRY_RULES = {
    'SG': {'name': 'Singapore', 'dial_code': '65', 'valid_lengths': {8}, 'starts_with': {'6', '8', '9'}},
    'MY': {'name': 'Malaysia', 'dial_code': '60', 'valid_lengths': {9, 10}},
    'ID': {'name': 'Indonesia', 'dial_code': '62', 'valid_lengths': {9, 10, 11, 12}},
    'TH': {'name': 'Thailand', 'dial_code': '66', 'valid_lengths': {8, 9}},
    'PH': {'name': 'Philippines', 'dial_code': '63', 'valid_lengths': {10}},
    'VN': {'name': 'Vietnam', 'dial_code': '84', 'valid_lengths': {9, 10}},
    'CN': {'name': 'China', 'dial_code': '86', 'valid_lengths': {11}},
    'HK': {'name': 'Hong Kong', 'dial_code': '852', 'valid_lengths': {8}},
    'TW': {'name': 'Taiwan', 'dial_code': '886', 'valid_lengths': {9}},
    'JP': {'name': 'Japan', 'dial_code': '81', 'valid_lengths': {10}},
    'KR': {'name': 'South Korea', 'dial_code': '82', 'valid_lengths': {9, 10}},
    'IN': {'name': 'India', 'dial_code': '91', 'valid_lengths': {10}},
    'PK': {'name': 'Pakistan', 'dial_code': '92', 'valid_lengths': {10}},
    'AE': {'name': 'United Arab Emirates', 'dial_code': '971', 'valid_lengths': {9}},
    'SA': {'name': 'Saudi Arabia', 'dial_code': '966', 'valid_lengths': {9}},
    'TR': {'name': 'Turkey', 'dial_code': '90', 'valid_lengths': {10}},
    'RU': {'name': 'Russia', 'dial_code': '7', 'valid_lengths': {10}},
    'GB': {'name': 'United Kingdom', 'dial_code': '44', 'valid_lengths': {10}},
    'IE': {'name': 'Ireland', 'dial_code': '353', 'valid_lengths': {9}},
    'FR': {'name': 'France', 'dial_code': '33', 'valid_lengths': {9}},
    'DE': {'name': 'Germany', 'dial_code': '49', 'valid_lengths': {10, 11}},
    'ES': {'name': 'Spain', 'dial_code': '34', 'valid_lengths': {9}},
    'IT': {'name': 'Italy', 'dial_code': '39', 'valid_lengths': {9, 10}},
    'NL': {'name': 'Netherlands', 'dial_code': '31', 'valid_lengths': {9}},
    'BE': {'name': 'Belgium', 'dial_code': '32', 'valid_lengths': {9}},
    'CH': {'name': 'Switzerland', 'dial_code': '41', 'valid_lengths': {9}},
    'SE': {'name': 'Sweden', 'dial_code': '46', 'valid_lengths': {9}},
    'NO': {'name': 'Norway', 'dial_code': '47', 'valid_lengths': {8}},
    'DK': {'name': 'Denmark', 'dial_code': '45', 'valid_lengths': {8}},
    'FI': {'name': 'Finland', 'dial_code': '358', 'valid_lengths': {9, 10}},
    'PL': {'name': 'Poland', 'dial_code': '48', 'valid_lengths': {9}},
    'PT': {'name': 'Portugal', 'dial_code': '351', 'valid_lengths': {9}},
    'AU': {'name': 'Australia', 'dial_code': '61', 'valid_lengths': {9}},
    'NZ': {'name': 'New Zealand', 'dial_code': '64', 'valid_lengths': {8, 9}},
    'US': {'name': 'United States', 'dial_code': '1', 'valid_lengths': {10}},
    'CA': {'name': 'Canada', 'dial_code': '1', 'valid_lengths': {10}},
    'MX': {'name': 'Mexico', 'dial_code': '52', 'valid_lengths': {10}},
    'BR': {'name': 'Brazil', 'dial_code': '55', 'valid_lengths': {10, 11}},
    'AR': {'name': 'Argentina', 'dial_code': '54', 'valid_lengths': {10}},
    'CL': {'name': 'Chile', 'dial_code': '56', 'valid_lengths': {9}},
    'ZA': {'name': 'South Africa', 'dial_code': '27', 'valid_lengths': {9}},
    'EG': {'name': 'Egypt', 'dial_code': '20', 'valid_lengths': {10}},
    'NG': {'name': 'Nigeria', 'dial_code': '234', 'valid_lengths': {10}},
}

PHONE_DIAL_TO_ISO = {}
for country_iso, phone_rule in PHONE_COUNTRY_RULES.items():
    PHONE_DIAL_TO_ISO.setdefault(phone_rule['dial_code'], country_iso)


def normalize_phone_digits(phone_value):
    return re.sub(r'\D', '', str(phone_value or ''))


def normalize_issue_key(message_text):
    normalized = re.sub(r'[^a-z0-9\s]', ' ', str(message_text or '').lower())
    return re.sub(r'\s+', ' ', normalized).strip()


def resolve_phone_country(country_value):
    raw_value = str(country_value or '').strip()
    if not raw_value:
        return None

    iso_code = raw_value.upper()
    if iso_code in PHONE_COUNTRY_RULES:
        return iso_code

    raw_lower = raw_value.lower()
    for country_iso, phone_rule in PHONE_COUNTRY_RULES.items():
        if raw_lower == phone_rule['name'].lower():
            return country_iso

    paren_match = re.search(r'\(\+\s*(\d{1,4})\)', raw_value)
    if paren_match:
        dial_code = paren_match.group(1)
        if dial_code in PHONE_DIAL_TO_ISO:
            return PHONE_DIAL_TO_ISO[dial_code]

    digits = normalize_phone_digits(raw_value)
    if digits in PHONE_DIAL_TO_ISO:
        return PHONE_DIAL_TO_ISO[digits]

    return None


def validate_phone_number(country_value=None, phone_number_value=None, phone_value=None, default_country='SG'):
    country_iso = resolve_phone_country(country_value)
    number_digits = normalize_phone_digits(phone_number_value)
    raw_phone = str(phone_value or '').strip()

    if not country_iso and not number_digits and not raw_phone:
        return True, '', None

    if not country_iso and raw_phone.startswith('+'):
        raw_digits = normalize_phone_digits(raw_phone)
        for dial_code in sorted(PHONE_DIAL_TO_ISO.keys(), key=len, reverse=True):
            if raw_digits.startswith(dial_code):
                country_iso = PHONE_DIAL_TO_ISO[dial_code]
                number_digits = raw_digits[len(dial_code):]
                break

    if not country_iso and number_digits:
        country_iso = default_country

    if not country_iso:
        return False, '', 'Please select a valid country code.'

    phone_rule = PHONE_COUNTRY_RULES.get(country_iso)
    if not phone_rule:
        return False, '', 'Selected country is not supported for phone validation.'

    if not number_digits and raw_phone:
        number_digits = normalize_phone_digits(raw_phone)

    if not number_digits:
        return False, '', f"Enter a phone number for {phone_rule['name']}."

    if not number_digits.isdigit():
        return False, '', 'Phone number must contain digits only.'

    valid_lengths = phone_rule['valid_lengths']
    if len(number_digits) not in valid_lengths:
        allowed_lengths = ', '.join(str(v) for v in sorted(valid_lengths))
        return (
            False,
            '',
            f"Invalid phone length for {phone_rule['name']} (+{phone_rule['dial_code']}). "
            f"Expected {allowed_lengths} digits."
        )

    required_start_digits = phone_rule.get('starts_with')
    if required_start_digits and number_digits[0] not in required_start_digits:
        starts_text = ', '.join(sorted(required_start_digits))
        return (
            False,
            '',
            f"Invalid phone for {phone_rule['name']} (+{phone_rule['dial_code']}). "
            f"Number must start with {starts_text}."
        )

    return True, f"+{phone_rule['dial_code']} {number_digits}", None

# Email tracking 1x1 transparent PNG pixel (base64 encoded)
TRACKING_PIXEL = base64.b64decode(
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)

def generate_tracking_token(invoice_id):
    """Generate a secure tracking token for an invoice"""
    # Use invoice_id and app secret key to create a signature
    token_data = f"{invoice_id}:{app.secret_key}"
    token = hashlib.sha256(token_data.encode()).hexdigest()[:16]
    return token

def generate_verification_token(invoice_id):
    """Generate a secure verification token for client to mark invoice as read"""
    # Use invoice_id, app secret key, and 'verification' prefix
    token_data = f"verification:{invoice_id}:{app.secret_key}"
    token = hashlib.sha256(token_data.encode()).hexdigest()[:16]
    return token


def normalize_invoice_number(invoice_number, invoice_id=None):
    """Return a safe invoice number fallback for display/validation paths."""
    normalized = (invoice_number or "").strip()
    if normalized:
        return normalized
    if invoice_id is not None:
        return f"INV-AUTO-{invoice_id:05d}"
    return "INV-AUTO"

init_db()

def initialize_database():
    db_file = 'app.db' 
    
    if not os.path.exists(db_file): # Database file does not exist
        print("Creating new database...")
        init_db() # Initialize database schema
        create_default_user()
        return True
    
    try:
        conn = get_conn() # Connect to existing database
        cursor = conn.cursor() # Create cursor for executing queries
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone() is None:
            print("Database exists but no tables found. Initializing...")
            init_db()
            create_default_user()
        else:
            cursor.execute("SELECT id FROM users WHERE id = 1")
            if cursor.fetchone() is None:
                create_default_user()
            print("Database already initialized")
            
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if os.path.exists(db_file):
            os.remove(db_file)
        init_db()
        create_default_user()
        return True

def create_default_user(): #Lets someone log in immediately after installing or initializing the application without creating a new account first.
    """Create default user if it doesn't exist"""
    try:
        execute(
            "INSERT OR IGNORE INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?);",
            (1, "Default User", "default@example.com", "x"),
        )
        print("Default user created")
    except:
        print("Default user already exists")


def seed_catalogue_products():
    product_count_row = query_one("SELECT COUNT(*) AS c FROM products")
    product_count = int(product_count_row['c'] if product_count_row else 0)
    if product_count > 0:
        return

    seed_products = [
        ('WEB-001', 'Web Development Service', 'Full-stack web development', 'Services', 150.0),
        ('DES-001', 'UI/UX Design', 'Interface and experience design', 'Services', 120.0),
        ('SEO-001', 'SEO Optimization', 'Search engine optimization service', 'Services', 300.0),
        ('CNT-001', 'Content Writing', 'Professional content writing', 'Services', 80.0),
        ('CON-001', 'Consulting Hour', 'Business consulting services', 'Consulting', 200.0),
        ('MNT-001', 'Monthly Maintenance', 'Website maintenance package', 'Packages', 500.0),
        ('MKT-001', 'Marketing Kit', 'Complete marketing materials', 'Products', 350.0),
    ]

    for sku, name, description, category, price in seed_products:
        execute(
            """
            INSERT OR IGNORE INTO products (sku, name, description, category, price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, name, description, category, price),
        )


def seed_audit_logs():
    audit_count_row = query_one("SELECT COUNT(*) AS c FROM audit_logs")
    audit_count = int(audit_count_row['c'] if audit_count_row else 0)
    if audit_count > 0:
        return

    sample_logs = [
        ('INV-2026-001', 'Tech Solutions Pte Ltd', 'Invoice Created', 9200.0, 'pending', 'System', '2026-01-22 09:30:00'),
        ('INV-2026-001', 'Tech Solutions Pte Ltd', 'Submitted for Approval', 9200.0, 'pending', 'Sarah Chen', '2026-01-22 10:45:00'),
        ('INV-2026-001', 'Tech Solutions Pte Ltd', 'Approved', 9200.0, 'approved', 'Daniel Wong', '2026-01-22 14:30:00'),
        ('INV-2026-001', 'Tech Solutions Pte Ltd', 'Sent to Client', 9200.0, 'delivered', 'System', '2026-01-22 14:45:00'),
        ('INV-2026-001', 'Tech Solutions Pte Ltd', 'Viewed by Client', 9200.0, 'opened', 'Client Portal', '2026-01-23 09:15:00'),
        ('INV-2026-002', 'Future Ventures Ltd', 'Invoice Created', 25000.0, 'pending', 'System', '2026-01-23 11:00:00'),
    ]

    for invoice_number, client_name, action, amount, status, created_by, timestamp in sample_logs:
        execute(
            """
            INSERT INTO audit_logs (invoice_number, client_name, action, amount, status, created_by, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (invoice_number, client_name, action, amount, status, created_by, timestamp),
        )


def ensure_merged_seed_data():
    seed_catalogue_products()
    seed_audit_logs()


def ensure_integrated_tables():
    execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_invoice_meta (
            invoice_id INTEGER PRIMARY KEY,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'SGD',
            gst_rate REAL NOT NULL DEFAULT 9.0,
            bill_to_phone TEXT,
            bill_to_address TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        )
        """
    )

initialize_database()
ensure_merged_seed_data()
ensure_integrated_tables()

ROLE_ADMIN = 'admin'
ROLE_EMPLOYEE = 'employee'


def get_current_user_id():
    """Temporary user resolver until auth credentials flow is integrated."""
    return 1


def get_current_user_role():
    """Resolve role from DB, with optional dev override for integration testing."""
    role_override = (os.environ.get('DEV_USER_ROLE_OVERRIDE') or '').strip().lower()
    if role_override in (ROLE_ADMIN, ROLE_EMPLOYEE):
        return role_override

    try:
        user = query_one("SELECT role FROM users WHERE id = ?", (get_current_user_id(),))
    except Exception:
        user = None

    if user:
        db_role = ''
        try:
            db_role = str(user['role'] or '').strip().lower()
        except Exception:
            db_role = ''

        if db_role in (ROLE_ADMIN, ROLE_EMPLOYEE):
            return db_role

    return ROLE_EMPLOYEE


def is_current_user_admin():
    return get_current_user_role() == ROLE_ADMIN


def get_current_user_profile():
    """Return basic user profile details for current user UI context."""
    default_role = get_current_user_role()
    fallback_name = 'Admin User' if default_role == ROLE_ADMIN else 'Employee'
    fallback_email = 'admin@example.com' if default_role == ROLE_ADMIN else 'employee@example.com'

    try:
        user = query_one(
            "SELECT name, email FROM users WHERE id = ?",
            (get_current_user_id(),)
        )
    except Exception:
        user = None

    if not user:
        return {
            'name': fallback_name,
            'email': fallback_email
        }

    try:
        name = (user['name'] or '').strip()
    except Exception:
        name = ''

    try:
        email = (user['email'] or '').strip()
    except Exception:
        email = ''

    return {
        'name': name or fallback_name,
        'email': email or fallback_email
    }


def build_effective_invoice_status_sql(alias=''):
        """Return SQL expression for delivery status normalized from timeline columns."""
        prefix = f"{alias}." if alias else ''
        return f"""
        CASE
            WHEN {prefix}opened_date IS NOT NULL AND TRIM({prefix}opened_date) NOT IN ('', 'null', 'None') THEN 'opened'
            WHEN COALESCE({prefix}status, 'pending') = 'opened' THEN 'opened'
            ELSE COALESCE({prefix}status, 'pending')
        END
        """.strip()


@app.context_processor
def inject_user_permissions():
    role = get_current_user_role()
    is_admin = role == ROLE_ADMIN
    profile = get_current_user_profile()

    pending_approvals_count = 0
    try:
        pending_row = query_one(
            """
            SELECT COUNT(*) AS c
            FROM invoices
            WHERE user_id = ? AND approval_status = 'pending'
            """,
            (get_current_user_id(),),
        )
        if pending_row:
            pending_approvals_count = int(pending_row['c'] or 0)
    except Exception:
        pending_approvals_count = 0

    return {
        'current_user_role': role,
        'can_manage_settings': is_admin,
        'can_manage_approvals_actions': is_admin,
        'current_user_name': profile['name'],
        'current_user_email': profile['email'],
        'pending_approvals_count': pending_approvals_count
    }

# ===== EMAIL HELPER FUNCTIONS =====
def get_email_deliverability_warning(sender_email, base_url):
    """Return a short warning when config is likely to cause spam placement."""
    if not app.config.get('EMAIL_STRICT_PRODUCTION_CHECKS', False):
        return ''

    warnings = []

    sender = (sender_email or '').strip().lower()
    free_domains = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'live.com'}
    if '@' in sender:
        sender_domain = sender.split('@', 1)[1]
        if sender_domain in free_domains:
            warnings.append('Sender uses a free mailbox domain. Use a verified business domain with SPF/DKIM/DMARC.')

    url_value = (base_url or '').strip().lower()
    if 'localhost' in url_value or '127.0.0.1' in url_value:
        warnings.append('APP_BASE_URL is local-only. Use a public HTTPS URL in production emails.')

    return ' '.join(warnings)


def _is_free_mailbox_sender(sender_email):
    sender = (sender_email or '').strip().lower()
    free_domains = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'live.com'}
    if '@' not in sender:
        return False
    sender_domain = sender.split('@', 1)[1]
    return sender_domain in free_domains


def _is_public_https_base_url(base_url):
    candidate = (base_url or '').strip()
    if not candidate:
        return False

    try:
        parsed = urlparse(candidate)
    except Exception:
        return False

    if parsed.scheme.lower() != 'https':
        return False

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname or hostname == 'localhost' or hostname.endswith('.local'):
        return False

    try:
        parsed_ip = ipaddress.ip_address(hostname)
        if (
            parsed_ip.is_private
            or parsed_ip.is_loopback
            or parsed_ip.is_link_local
            or parsed_ip.is_reserved
            or parsed_ip.is_multicast
        ):
            return False
    except ValueError:
        # Not an IP literal: allow normal public DNS hostnames.
        pass

    return True


def get_email_production_config_error(sender_email, base_url):
    """Return strict config error for production email sends; empty string when valid."""
    if not app.config.get('EMAIL_STRICT_PRODUCTION_CHECKS', False):
        return ''

    errors = []
    if _is_free_mailbox_sender(sender_email):
        errors.append('Sender uses a free mailbox domain. Use a verified business domain with SPF/DKIM/DMARC.')
    if not _is_public_https_base_url(base_url):
        errors.append('APP_BASE_URL is local-only. Use a public HTTPS URL in production emails.')
    return ' '.join(errors)


def send_invoice_email(recipient_email, invoice_data):
    """
    Send invoice to client via email with PDF attachment
    
    Args:
        recipient_email (str): Email address to send to
        invoice_data (dict): Invoice data containing details
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Check if email is configured
        if not EMAIL_CONFIGURED:
            return False, "Email configuration not set. Please set MAIL_USERNAME and MAIL_PASSWORD environment variables. See EMAIL_SETUP.md for instructions."
        
        if not recipient_email or not invoice_data:
            return False, "Missing recipient email or invoice data"
        
        invoice_number = invoice_data.get('invoice_number', 'INV-Unknown')
        client_name = invoice_data.get('client_name', 'Valued Client')
        total = invoice_data.get('total', '0.00')
        sent_date = invoice_data.get('sent_date', '')
        invoice_id = invoice_data.get('invoice_id', None)
        
        # Generate view token for client to click and view invoice
        view_token = ""
        if invoice_id:
            view_token = generate_verification_token(invoice_id)

        app_base_url = app.config.get('APP_BASE_URL', 'http://localhost:5000').rstrip('/')
        view_link = f"{app_base_url}/view-invoice/{invoice_id}/{view_token}" if invoice_id and view_token else app_base_url
        
        deliverability_warning = get_email_deliverability_warning(app.config['MAIL_DEFAULT_SENDER'], app_base_url)
        production_config_error = get_email_production_config_error(app.config['MAIL_DEFAULT_SENDER'], app_base_url)
        if production_config_error:
            return False, production_config_error, deliverability_warning

        # Create professional HTML email body (similar to the template shown)
        html_body = f"""
        <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: #f8f9fa; }}
                    .header {{ background-color: #ffffff; padding: 30px 20px; border-bottom: 1px solid #ecf0f1; }}
                    .header-content {{ display: flex; justify-content: space-between; align-items: center; }}
                    .company-name {{ font-size: 28px; font-weight: bold; color: #2c3e50; }}
                    .invoice-badge {{ font-size: 24px; font-weight: bold; color: #e74c3c; }}
                    .content {{ background-color: #ffffff; padding: 30px 20px; }}
                    .greeting {{ font-size: 14px; color: #2c3e50; margin-bottom: 15px; }}
                    .thank-you {{ font-size: 14px; color: #555; line-height: 1.6; margin-bottom: 20px; }}
                    .invoice-details {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                    .detail-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #ecf0f1; }}
                    .detail-row:last-child {{ border-bottom: none; }}
                    .detail-label {{ font-weight: bold; color: #34495e; }}
                    .detail-value {{ color: #2c3e50; }}
                    .section-title {{ font-size: 14px; font-weight: bold; color: #2c3e50; margin-top: 20px; margin-bottom: 10px; }}
                    .support-section {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                    .support-item {{ margin-bottom: 10px; font-size: 13px; color: #555; }}
                    .footer {{ background-color: #34495e; color: #ecf0f1; padding: 20px; text-align: center; font-size: 12px; }}
                    .footer-link {{ color: #3498db; text-decoration: none; }}
                    .cta-button {{ background-color: #e74c3c; color: white; padding: 10px 20px; border-radius: 5px; display: inline-block; text-decoration: none; margin: 15px 0; }}
                    a {{ color: #3498db; text-decoration: none; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="header-content">
                            <div class="company-name">FourVoice</div>
                            <div class="invoice-badge">INVOICE</div>
                        </div>
                    </div>
                    
                    <div class="content">
                        <div class="greeting">Dear {client_name},</div>
                        
                        <div class="thank-you">
                            Thank you for your business! Your invoice has been generated and is ready for review. 
                            Please click the button below to view your complete invoice details.
                        </div>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <p>
                                <a href="{view_link}" 
                                   style="display: inline-block; background-color: #3498db; color: white; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;">
                                    View Invoice
                                </a>
                            </p>
                            <p style="font-size: 11px; color: #999; margin-top: 10px;">Click the button above to view, review, and download your invoice.</p>
                        </div>
                        
                        <div class="section-title">Support Information</div>
                        <div class="support-section">
                            <div class="support-item">
                                <strong>Questions about your invoice?</strong><br>
                                Please contact our support team at <a href="mailto:support@fourvoice.com">support@fourvoice.com</a>
                            </div>
                            <div class="support-item">
                                <strong>Need technical support?</strong><br>
                                Visit our support portal or reply to this email with details.
                            </div>
                        </div>
                        
                        <div style="margin-top: 30px; font-size: 12px; color: #888; border-top: 1px solid #ecf0f1; padding-top: 15px;">
                            <p>Thank you for your business!</p>
                            <p><strong>FourVoice Team</strong></p>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p style="margin: 0;">© 2026 FourVoice. All rights reserved.</p>
                        <p style="margin: 5px 0; font-size: 11px;">This is an automated message. Please do not reply to this email.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        
        text_body = (
            f"Dear {client_name},\n\n"
            f"Your invoice {invoice_number} is ready for review.\n"
            f"View invoice: {view_link}\n\n"
            "If you need help, contact support@fourvoice.com.\n\n"
            "FourVoice Team"
        )

        # Create email message without PDF attachment
        subject = f"Invoice {invoice_number} from FourVoice"
        msg = Message(
            subject=subject,
            recipients=[recipient_email],
            sender=("FourVoice Invoices", app.config['MAIL_DEFAULT_SENDER']),
            reply_to=app.config.get('MAIL_REPLY_TO') or app.config['MAIL_DEFAULT_SENDER'],
            body=text_body,
            html=html_body
        )
        msg.extra_headers = {
            'X-Auto-Response-Suppress': 'All',
            'Auto-Submitted': 'auto-generated'
        }
        
        print(f"\n{'='*60}")
        print(f"[EMAIL] Attempting to send email...")
        print(f"  Recipient: {recipient_email}")
        print(f"  Username: {app.config['MAIL_USERNAME']}")
        print(f"  Server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
        print(f"  TLS: {app.config['MAIL_USE_TLS']}")
        print(f"  Suppress Send: {app.config['MAIL_SUPPRESS_SEND']}")
        print(f"{'='*60}")
        
        mail.send(msg)
        
        print(f"[EMAIL] ✓ mail.send() completed without exception")
        print(f"✓ Email sent successfully to {recipient_email} for invoice {invoice_number}\n")
        return True, f"Email sent successfully to {recipient_email}", deliverability_warning
        
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        print(f"\n[EMAIL] ✗ Exception caught: {error_msg}")
        print(f"[EMAIL] Traceback:\n{traceback.format_exc()}\n")
        return False, error_msg, ''


@app.get("/debug/email-config")
def debug_email_config():
    """Debug endpoint to check email configuration"""
    return jsonify({
        'email_configured': EMAIL_CONFIGURED,
        'mail_server': app.config['MAIL_SERVER'],
        'mail_port': app.config['MAIL_PORT'],
        'mail_use_tls': app.config['MAIL_USE_TLS'],
        'mail_username': app.config['MAIL_USERNAME'],
        'mail_suppress_send': app.config['MAIL_SUPPRESS_SEND'],
        'testing_env_var': os.environ.get('TESTING', 'Not set'),
        'message': 'Email configuration check'
    })


@app.get("/debug/test-email")
def test_email():
    """Test email sending"""
    try:
        if not EMAIL_CONFIGURED:
            return jsonify({'success': False, 'error': 'Email not configured'}), 400
        
        test_msg = Message(
            subject='Test Email from FourVoice',
            recipients=['queksiqi@gmail.com'],
            body='This is a test email to verify SMTP configuration is working.',
            html='<html><body><h1>Test Email</h1><p>This is a test email to verify SMTP configuration is working.</p></body></html>'
        )
        
        print("Attempting to send test email...")
        print(f"  Server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
        print(f"  Username: {app.config['MAIL_USERNAME']}")
        print(f"  TLS: {app.config['MAIL_USE_TLS']}")
        print(f"  Suppress Send: {app.config['MAIL_SUPPRESS_SEND']}")
        
        mail.send(test_msg)
        
        return jsonify({'success': True, 'message': 'Test email sent successfully'})
    except Exception as e:
        error_msg = f"Failed to send test email: {str(e)}\n{traceback.format_exc()}"
        print(f"✗ {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500


@app.get("/")
def home():
    return render_template("home.html", title="Dashboard")

@app.get("/clients")
def clients_list():
    return render_template("legacy/clients.html", page="clients")

@app.route("/clients/new", methods=["GET", "POST"])
def clients_create():
    if request.method == "POST":
        raw_client_name = request.form.get("client_name")
        raw_email = request.form.get("email")
        raw_phone = request.form.get("phone")
        raw_address = request.form.get("address")

        errors, client_name, email, phone, address = validate_client_fields(
            raw_client_name, raw_email, raw_phone, raw_address
        )

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "clients_form.html",
                title="Add client",
                form={"client_name": client_name, "email": email, "phone": phone, "address": address},
                mode="create",
            )

        try:
            execute(
                """
                INSERT INTO clients (user_id, client_name, email, phone, address)
                VALUES (?, ?, ?, ?, ?);
                """,
                (1, client_name, email or None, phone or None, address or None),
            )
        except sqlite3.IntegrityError:
            flash("A client with this email already exists.", "danger")
            return render_template(
                "clients_form.html",
                title="Add client",
                form={"client_name": client_name, "email": email, "phone": phone, "address": address},
                mode="create",
            )

        flash("Client added successfully.", "success")
        return redirect(url_for("clients_list"))

    return render_template(
        "clients_form.html",
        title="Add client",
        form={"client_name": "", "email": "", "phone": "", "address": ""},
        mode="create",
    )

@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
def clients_edit(client_id: int):
    client = query_one(
        "SELECT * FROM clients WHERE id = ? AND user_id = ?;",
        (client_id, 1),
    )
    if client is None:
        abort(404)

    if request.method == "POST":
        raw_client_name = request.form.get("client_name")
        raw_email = request.form.get("email")
        raw_phone = request.form.get("phone")
        raw_address = request.form.get("address")

        errors, client_name, email, phone, address = validate_client_fields(
            raw_client_name, raw_email, raw_phone, raw_address
        )

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "clients_form.html",
                title="Edit client",
                form={"client_name": client_name, "email": email, "phone": phone, "address": address},
                mode="edit",
                client_id=client_id,
            )

        try:
            execute(
                """
                UPDATE clients
                SET client_name = ?, email = ?, phone = ?, address = ?, updated_at = datetime('now')
                WHERE id = ? AND user_id = ?;
                """,
                (client_name, email or None, phone or None, address or None, client_id, 1),
            )
        except sqlite3.IntegrityError:
            flash("A client with this email already exists.", "danger")
            return render_template(
                "clients_form.html",
                title="Edit client",
                form={"client_name": client_name, "email": email, "phone": phone, "address": address},
                mode="edit",
                client_id=client_id,
            )

        flash("Client updated successfully.", "success")
        return redirect(url_for("clients_list"))

    return render_template(
        "clients_form.html",
        title="Edit client",
        form={
            "client_name": client["client_name"],
            "email": client["email"] or "",
            "phone": client["phone"] or "",
            "address": client["address"] or "",
        },
        mode="edit",
        client_id=client_id,
    )

@app.post("/clients/<int:client_id>/delete")
def clients_delete(client_id: int):
    client = query_one(
        "SELECT id FROM clients WHERE id = ? AND user_id = ?;",
        (client_id, 1),
    )
    if client is None:
        abort(404)

    execute(
        "DELETE FROM clients WHERE id = ? AND user_id = ?;",
        (client_id, 1),
    )

    flash("Client deleted successfully.", "success")
    return redirect(url_for("clients_list"))


@app.get("/dashboard")
def dashboard_page():
    return redirect(url_for("home"))


@app.get("/create-invoice")
def create_invoice_page():
    return render_template("legacy/create_invoice.html", page="create_invoice")


@app.get("/invoices")
def invoices_page():
    return redirect(url_for("invoice_delivery"))


@app.get("/legacy")
def legacy_home_page():
    return redirect(url_for("legacy_clients_page"))


@app.get("/legacy/clients")
def legacy_clients_page():
    return render_template("legacy/clients.html", page="clients")


@app.get("/legacy/create-invoice")
def legacy_create_invoice_page():
    return render_template("legacy/create_invoice.html", page="create_invoice")


@app.get("/legacy/invoices")
def legacy_invoices_page():
    latest_invoice = query_one("SELECT id FROM invoices WHERE user_id = ? ORDER BY id DESC LIMIT 1", (1,))
    if latest_invoice:
        return redirect(url_for("legacy_invoice_preview_page", invoice_id=latest_invoice["id"]))
    return render_template("legacy/invoice_preview.html", page="invoices", invoice=None)


@app.get("/legacy/catalogue")
def legacy_catalogue_page():
    return render_template("legacy/catalogue.html", page="catalogue")


def _legacy_invoice_payload(invoice_id: int):
    invoice_row = query_one(
        """
        SELECT i.*, m.issue_date, m.due_date, m.currency, m.gst_rate, m.bill_to_phone, m.bill_to_address
        FROM invoices i
        LEFT JOIN legacy_invoice_meta m ON m.invoice_id = i.id
        WHERE i.id = ? AND i.user_id = ?
        """,
        (invoice_id, 1),
    )
    if not invoice_row:
        return None

    item_rows = query_all(
        """
        SELECT description, quantity, rate
        FROM invoice_items
        WHERE invoice_id = ?
        ORDER BY id ASC
        """,
        (invoice_id,),
    )

    gst_rate = float(invoice_row["gst_rate"] if invoice_row["gst_rate"] is not None else 9.0)
    subtotal = float(invoice_row["subtotal"] or 0)
    gst_amount = float(invoice_row["tax"] or 0)
    total_amount = float(invoice_row["total"] or 0)

    return {
        "id": invoice_row["id"],
        "invoice_number": invoice_row["invoice_number"],
        "issue_date": invoice_row["issue_date"] or (invoice_row["sent_date"] or ""),
        "due_date": invoice_row["due_date"] or "",
        "gst_rate": gst_rate,
        "subtotal": subtotal,
        "gst": gst_amount,
        "total": total_amount,
        "client_name": invoice_row["client_name"],
        "client_email": invoice_row["email"] or "",
        "client_address": invoice_row["bill_to_address"] or "",
        "items": [
            {
                "description": row["description"],
                "quantity": int(row["quantity"]) if float(row["quantity"]).is_integer() else float(row["quantity"]),
                "unit_price": float(row["rate"] or 0),
            }
            for row in item_rows
        ],
    }


@app.get("/legacy/invoice-preview/<int:invoice_id>")
def legacy_invoice_preview_page(invoice_id: int):
    invoice_payload = _legacy_invoice_payload(invoice_id)
    if not invoice_payload:
        abort(404)
    return render_template("legacy/invoice_preview.html", page="invoices", invoice=invoice_payload)


@app.get("/invoice-preview/<int:invoice_id>")
def invoice_preview_compat(invoice_id: int):
    return redirect(url_for("legacy_invoice_preview_page", invoice_id=invoice_id))


@app.get("/legacy/download/<int:invoice_id>")
def legacy_download_invoice_pdf(invoice_id: int):
    return redirect(url_for("download_invoice_pdf", invoice_id=invoice_id))


@app.get("/download/<int:invoice_id>")
def legacy_download_invoice_pdf_compat(invoice_id: int):
    return redirect(url_for("legacy_download_invoice_pdf", invoice_id=invoice_id))


@app.get("/legacy/submit/<int:invoice_id>")
def legacy_submit_invoice(invoice_id: int):
    existing_invoice = query_one("SELECT id FROM invoices WHERE id = ? AND user_id = ?", (invoice_id, 1))
    if not existing_invoice:
        abort(404)
    execute(
        """
        UPDATE invoices
        SET approval_status = 'pending', status = 'pending', updated_at = datetime('now')
        WHERE id = ? AND user_id = ?
        """,
        (invoice_id, 1),
    )
    return redirect(url_for("approvals"))


@app.get("/submit/<int:invoice_id>")
def legacy_submit_invoice_compat(invoice_id: int):
    return redirect(url_for("legacy_submit_invoice", invoice_id=invoice_id))


def _legacy_client_to_dict(row):
    return {
        "id": row["id"],
        "name": row["client_name"],
        "email": row["email"] or "",
        "phone": row["phone"] or "",
        "address": row["address"] or "",
        "created_at": row["created_at"],
    }


def _validate_legacy_client_payload(data):
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
    if not address:
        errors["address"] = "Address is required"
    return errors, name, email, phone, address


@app.get("/api/clients")
def api_legacy_list_clients():
    query_value = (request.args.get("q") or "").strip().lower()
    rows = query_all("SELECT * FROM clients WHERE user_id = ? ORDER BY id DESC", (1,))
    clients = [_legacy_client_to_dict(row) for row in rows]
    if query_value:
        clients = [
            client for client in clients
            if query_value in (client["name"] or "").lower()
            or query_value in (client["email"] or "").lower()
            or query_value in (client["phone"] or "").lower()
        ]
    return jsonify({"clients": clients})


@app.post("/api/clients")
def api_legacy_create_client():
    data = request.get_json(force=True, silent=True) or {}
    errors, name, email, phone, address = _validate_legacy_client_payload(data)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    try:
        new_id = execute(
            """
            INSERT INTO clients (user_id, client_name, email, phone, address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (1, name, email, phone, address),
        )
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "errors": {"email": "A client with this email already exists"}}), 400

    row = query_one("SELECT * FROM clients WHERE id = ? AND user_id = ?", (new_id, 1))
    return jsonify({"ok": True, "client": _legacy_client_to_dict(row)})


@app.put("/api/clients/<int:client_id>")
def api_legacy_update_client(client_id: int):
    data = request.get_json(force=True, silent=True) or {}
    errors, name, email, phone, address = _validate_legacy_client_payload(data)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    existing_client = query_one("SELECT id FROM clients WHERE id = ? AND user_id = ?", (client_id, 1))
    if not existing_client:
        return jsonify({"ok": False, "error": "Client not found"}), 404

    try:
        execute(
            """
            UPDATE clients
            SET client_name = ?, email = ?, phone = ?, address = ?, updated_at = datetime('now')
            WHERE id = ? AND user_id = ?
            """,
            (name, email, phone, address, client_id, 1),
        )
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "errors": {"email": "A client with this email already exists"}}), 400

    updated_row = query_one("SELECT * FROM clients WHERE id = ? AND user_id = ?", (client_id, 1))
    return jsonify({"ok": True, "client": _legacy_client_to_dict(updated_row)})


@app.delete("/api/clients/<int:client_id>")
def api_legacy_delete_client(client_id: int):
    existing_client = query_one("SELECT id FROM clients WHERE id = ? AND user_id = ?", (client_id, 1))
    if not existing_client:
        return jsonify({"ok": False, "error": "Client not found"}), 404

    execute("DELETE FROM clients WHERE id = ? AND user_id = ?", (client_id, 1))
    return jsonify({"ok": True})


@app.get("/api/catalogue-items")
def api_legacy_catalogue_items():
    rows = query_all(
        """
        SELECT id, name, sku, category, description, price AS unit_price
        FROM products
        ORDER BY id DESC
        """
    )
    return jsonify({"items": [dict(row) for row in rows]})


def _legacy_invoice_to_dict(row):
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "bill_to_name": row["client_name"],
        "invoice_number": row["invoice_number"],
        "currency": row["currency"] or "SGD",
        "issue_date": row["issue_date"],
        "due_date": row["due_date"],
        "subtotal": row["subtotal"],
        "gst_rate": row["gst_rate"],
        "gst_amount": row["tax"],
        "total_amount": row["total"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


@app.get("/api/invoices")
def api_legacy_list_invoices():
    client_id = request.args.get("client_id")
    bill_to_name = (request.args.get("bill_to_name") or "").strip().lower()

    rows = query_all(
        """
        SELECT i.*, m.issue_date, m.due_date, m.currency, m.gst_rate
        FROM invoices i
        LEFT JOIN legacy_invoice_meta m ON m.invoice_id = i.id
        WHERE i.user_id = ?
        ORDER BY i.id DESC
        """,
        (1,),
    )

    invoices = []
    for row in rows:
        if client_id:
            row_client_id = row["client_id"]
            name_match = bill_to_name and bill_to_name == (row["client_name"] or "").strip().lower()
            if str(row_client_id or "") != str(client_id) and not name_match:
                continue
        invoices.append(_legacy_invoice_to_dict(row))

    return jsonify({"invoices": invoices})


@app.get("/api/invoices/next-number")
def api_legacy_next_invoice_number():
    year = datetime.now().year
    rows = query_all("SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?", (f"INV-{year}-%",))
    highest = 0
    for row in rows:
        matched = re.match(rf"^INV-{year}-(\d+)$", row["invoice_number"] or "")
        if matched:
            highest = max(highest, int(matched.group(1)))
    return jsonify({"invoice_number": f"INV-{year}-{str(highest + 1).zfill(3)}"})


@app.post("/api/invoices")
def api_legacy_create_invoice():
    data = request.get_json(force=True, silent=True) or {}

    client_mode = data.get("client_mode")
    client_id = data.get("client_id")
    oneoff_name = (data.get("oneoff_name") or "").strip()
    invoice_number = (data.get("invoice_number") or "").strip()
    currency = (data.get("currency") or "SGD").strip() or "SGD"
    issue_date = (data.get("issue_date") or "").strip()
    due_date = (data.get("due_date") or "").strip()
    notes = (data.get("notes") or "").strip()

    try:
        gst_rate = float(data.get("gst_rate") or 9.0)
    except (TypeError, ValueError):
        gst_rate = 9.0

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
    elif not oneoff_name:
        errors["client"] = "Please enter a one-off client name"

    incoming_items = data.get("items") or []
    valid_items = []
    for item in incoming_items:
        description = (item.get("description") or "").strip()
        if not description:
            continue
        try:
            quantity = float(item.get("quantity") or 0)
            unit_price = float(item.get("unit_price") or 0)
        except (TypeError, ValueError):
            continue
        quantity = quantity if quantity > 0 else 1.0
        line_total = quantity * unit_price
        valid_items.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    if not valid_items:
        errors["items"] = "Add at least one line item"

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    linked_client_id = None
    bill_to_name = ""
    bill_to_email = ""
    bill_to_phone = ""
    bill_to_address = ""

    if client_mode == "saved":
        client_row = query_one("SELECT * FROM clients WHERE id = ? AND user_id = ?", (client_id, 1))
        if not client_row:
            return jsonify({"ok": False, "errors": {"client": "Selected client not found"}}), 400
        linked_client_id = client_row["id"]
        bill_to_name = client_row["client_name"]
        bill_to_email = client_row["email"] or ""
        bill_to_phone = client_row["phone"] or ""
        bill_to_address = client_row["address"] or ""
    else:
        bill_to_name = oneoff_name

    subtotal = sum(line["line_total"] for line in valid_items)
    tax = subtotal * (gst_rate / 100.0)
    total = subtotal + tax

    try:
        invoice_id = execute(
            """
            INSERT INTO invoices (
                user_id, client_id, invoice_number, client_name, email,
                status, sent_date, subtotal, tax, total, notes,
                approval_status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, 'pending', datetime('now'))
            """,
            (1, linked_client_id, invoice_number, bill_to_name, bill_to_email, issue_date, subtotal, tax, total, notes),
        )
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "errors": {"invoice_number": "Invoice number already exists"}}), 400

    for line in valid_items:
        execute(
            """
            INSERT INTO invoice_items (invoice_id, service_code, description, quantity, rate, total)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (invoice_id, "LEGACY", line["description"], line["quantity"], line["unit_price"], line["line_total"]),
        )

    execute(
        """
        INSERT OR REPLACE INTO legacy_invoice_meta (
            invoice_id, issue_date, due_date, currency, gst_rate, bill_to_phone, bill_to_address
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (invoice_id, issue_date, due_date, currency, gst_rate, bill_to_phone, bill_to_address),
    )

    created_invoice = query_one(
        """
        SELECT i.*, m.issue_date, m.due_date, m.currency, m.gst_rate
        FROM invoices i
        LEFT JOIN legacy_invoice_meta m ON m.invoice_id = i.id
        WHERE i.id = ? AND i.user_id = ?
        """,
        (invoice_id, 1),
    )
    return jsonify({"ok": True, "invoice": _legacy_invoice_to_dict(created_invoice)})


@app.get('/catalogue')
def catalogue():
    products = query_all(
        """
        SELECT id, sku, name, description, category, price
        FROM products
        ORDER BY category ASC, name ASC
        """
    )
    return render_template('catalogue.html', title='Catalogue', products=products)


@app.get('/search_catalogue')
def search_catalogue():
    query = (request.args.get('query') or '').strip()
    like = f"%{query}%"
    results = query_all(
        """
        SELECT id, sku, name, description, category, price
        FROM products
        WHERE sku LIKE ? OR name LIKE ? OR description LIKE ? OR category LIKE ?
        ORDER BY category ASC, name ASC
        """,
        (like, like, like, like),
    )
    return jsonify({'results': [dict(row) for row in results]})


@app.post('/catalogue/add')
def add_product():
    name = (request.form.get('name') or '').strip()
    sku = (request.form.get('sku') or '').strip().upper()
    description = (request.form.get('description') or '').strip()
    category = (request.form.get('category') or '').strip() or 'Services'
    price_value = (request.form.get('price') or '').strip()

    if not name or not sku or not price_value:
        flash('Name, SKU, and price are required.', 'danger')
        return redirect(url_for('catalogue'))

    try:
        price = float(price_value)
    except ValueError:
        flash('Price must be a valid number.', 'danger')
        return redirect(url_for('catalogue'))

    try:
        execute(
            """
            INSERT INTO products (sku, name, description, category, price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku, name, description or None, category, price),
        )
        flash('Catalogue item added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash('SKU already exists. Use a unique SKU.', 'danger')

    return redirect(url_for('catalogue'))


@app.post('/catalogue/edit')
def edit_product():
    product_id = request.form.get('id')
    name = (request.form.get('name') or '').strip()
    sku = (request.form.get('sku') or '').strip().upper()
    description = (request.form.get('description') or '').strip()
    category = (request.form.get('category') or '').strip() or 'Services'
    price_value = (request.form.get('price') or '').strip()

    if not product_id or not name or not sku or not price_value:
        flash('All fields except description are required.', 'danger')
        return redirect(url_for('catalogue'))

    try:
        price = float(price_value)
    except ValueError:
        flash('Price must be a valid number.', 'danger')
        return redirect(url_for('catalogue'))

    try:
        execute(
            """
            UPDATE products
            SET sku = ?, name = ?, description = ?, category = ?, price = ?
            WHERE id = ?
            """,
            (sku, name, description or None, category, price, product_id),
        )
        flash('Catalogue item updated successfully.', 'success')
    except sqlite3.IntegrityError:
        flash('SKU already exists. Use a unique SKU.', 'danger')

    return redirect(url_for('catalogue'))


@app.post('/catalogue/delete/<int:id>')
def delete_product(id):
    execute("DELETE FROM products WHERE id = ?", (id,))
    flash('Catalogue item deleted.', 'success')
    return redirect(url_for('catalogue'))


@app.get('/audit-log')
def audit_log():
    raw_logs = query_all(
        """
        SELECT id, invoice_number, client_name, action, amount, status, created_by, timestamp
        FROM audit_logs
        ORDER BY timestamp ASC, id ASC
        """
    )

    invoices = {}
    for log in raw_logs:
        invoice_number = log['invoice_number'] or f"INV-AUTO-{log['id']:04d}"
        if invoice_number not in invoices:
            invoices[invoice_number] = {
                'client': log['client_name'] or 'Unknown Client',
                'amount': float(log['amount'] or 0),
                'status': log['status'] or 'pending',
                'logs': [],
            }
        invoices[invoice_number]['logs'].append(log)
        invoices[invoice_number]['amount'] = max(invoices[invoice_number]['amount'], float(log['amount'] or 0))

    anomaly_ids = request.args.getlist('anomaly')
    anomalies = {int(item) for item in anomaly_ids if str(item).isdigit()}

    return render_template('audit_log.html', title='Audit Log', invoices=invoices, anomalies=anomalies)


@app.get('/auditlog/scan')
def audit_scan():
    logs = query_all("SELECT id, amount FROM audit_logs")
    amounts = [float(log['amount']) for log in logs if float(log['amount'] or 0) > 0]

    anomaly_ids = []
    if len(amounts) >= 2:
        avg = statistics.mean(amounts)
        stdev = statistics.stdev(amounts)
        threshold = avg + (2 * stdev)
        anomaly_ids = [str(log['id']) for log in logs if float(log['amount'] or 0) > threshold]

    flash('AI scan completed. Unusual entries are highlighted.', 'warning')
    return redirect(url_for('audit_log', anomaly=anomaly_ids))


@app.get('/manage-users')
def manage_users_page():
    users = query_all(
        """
        SELECT id, name, email, role, created_at
        FROM users
        ORDER BY id ASC
        """
    )
    return render_template('manage_users.html', title='Manage Users', users=users)


@app.get('/my-company')
def my_company_page():
    profile = get_current_user_profile()
    company = {
        'name': 'FourVoice Pte Ltd',
        'email': profile['email'],
        'contact': profile['name'],
        'timezone': 'Asia/Singapore (UTC+8)',
    }
    return render_template('my_company.html', title='My Company', company=company)

# ============================================================================
# INVOICE DELIVERY ROUTES
# ============================================================================
# Purpose: Handle invoice delivery tracking, filtering, and resend operations
# Features:
#   - View all sent invoices
#   - Filter by delivery status (delivered, opened, pending, failed)
#   - Search by invoice number, client name, or email
#   - View detailed invoice information
#   - Resend invoices to clients
# ============================================================================

@app.get("/invoice-delivery")
def invoice_delivery():
    """
    Render the main invoice delivery dashboard page.
    
    Query Parameters:
        status (str): Filter invoices by status ('all', 'delivered', 'opened', 'pending', 'failed')
        q (str): Search query: searches for invoice number, client name, or email
    
    Returns:
        HTML template with invoice list and status counts
    """
    status = request.args.get("status", "all")  # Get status filter from URL
    q = (request.args.get("q") or "").lower()  # Get search query from URL

    effective_status_sql = build_effective_invoice_status_sql()

    # Build SQL query dynamically based on filters
    sql = f"SELECT *, {effective_status_sql} AS effective_status FROM invoices WHERE user_id = 1 AND approval_status = 'approved'"  # Only show approved invoices
    params = []  # Parameters for SQL query (prevents SQL injection), replace the ? placeholders in the query

    # Add status filter if not showing all
    if status != "all":
        sql += f" AND {effective_status_sql} = ?"
        params.append(status)

    # Add search filter if search term provided
    if q:
        sql += """
        AND (
          LOWER(invoice_number) LIKE ?
          OR LOWER(client_name) LIKE ?
          OR LOWER(email) LIKE ?
        )
        """
        like = f"%{q}%"  # SQL LIKE pattern for partial matching
        params.extend([like, like, like])  # Apply to all searchable fields

    sql += " ORDER BY sent_date DESC"  # Show newest invoices first

    invoices = query_all(sql, tuple(params))  # Execute query and fetch all results

    # Calculate status counts for dashboard cards
    counts = query_one(f"""
            SELECT
                COUNT(*) total,
                SUM(CASE WHEN {effective_status_sql} = 'delivered' THEN 1 ELSE 0 END) delivered,
                SUM(CASE WHEN {effective_status_sql} = 'opened' THEN 1 ELSE 0 END) opened,
                SUM(CASE WHEN {effective_status_sql} = 'pending' THEN 1 ELSE 0 END) pending,
                SUM(CASE WHEN {effective_status_sql} = 'failed' THEN 1 ELSE 0 END) failed
            FROM invoices
            WHERE user_id = 1 AND approval_status = 'approved'
        """)

    return render_template(
        "invoice_delivery.html",
        invoices=invoices,
        counts=counts,
        active_status=status,
        query=q,
        title="Invoice Delivery"
    )

@app.get("/invoice-delivery/filter")
def filter_invoices():
    """
    API endpoint to filter invoices by status, search query, and date range.
    Returns JSON data for AJAX requests from the frontend.
    
    Query Parameters:
        status (str): Filter by invoice status
        q (str): Search term
        date_from (str): Start date (YYYY-MM-DD format)
        date_to (str): End date (YYYY-MM-DD format)
    
    Returns:
        JSON: {
            'invoices': [array of invoice objects],
            'counts': {status counts object}
        }
    """
    status = request.args.get("status", "all") # Get 'status' from URL query parameters; default to "all" if not provided
    q = (request.args.get("q") or "").lower()  # Search query
    date_from = request.args.get("date_from", "").strip()  # Start date
    date_to = request.args.get("date_to", "").strip()  # End date
    effective_status_sql = build_effective_invoice_status_sql()

    # Build dynamic SQL query
    sql = f"SELECT *, {effective_status_sql} AS effective_status FROM invoices WHERE user_id = 1 AND approval_status = 'approved'"
    params = []  # SQL parameters

    if status != "all":
        sql += f" AND {effective_status_sql} = ?" # Add a filter to the SQL query for the selected status
        params.append(status)

    if q:
        sql += """
        AND (
          LOWER(invoice_number) LIKE ?
          OR LOWER(client_name) LIKE ?
          OR LOWER(email) LIKE ?
        )
        """
        like = f"%{q}%" # Add % wildcards for partial matching
        params.extend([like, like, like]) # Add the search pattern for all three fields to the query parameters

    # Add date range filtering
    if date_from:
        sql += " AND DATE(sent_date) >= ?"
        params.append(date_from)
    
    if date_to:
        sql += " AND DATE(sent_date) <= ?"
        params.append(date_to)

    sql += " ORDER BY sent_date DESC"
    invoices = query_all(sql, tuple(params))  # Fetch filtered invoices

    # Get counts for each status - only approved invoices
    counts_sql = f"""
      SELECT
        COUNT(*) total,
                SUM(CASE WHEN {effective_status_sql} = 'delivered' THEN 1 ELSE 0 END) delivered,
                SUM(CASE WHEN {effective_status_sql} = 'opened' THEN 1 ELSE 0 END) opened,
                SUM(CASE WHEN {effective_status_sql} = 'pending' THEN 1 ELSE 0 END) pending,
                SUM(CASE WHEN {effective_status_sql} = 'failed' THEN 1 ELSE 0 END) failed
      FROM invoices
      WHERE user_id = 1 AND approval_status = 'approved'
    """
    counts_params = []
    
    # Apply date filters to status counts as well
    if date_from:
        counts_sql += " AND DATE(sent_date) >= ?"
        counts_params.append(date_from)
    
    if date_to:
        counts_sql += " AND DATE(sent_date) <= ?"
        counts_params.append(date_to)
    
    counts = query_one(counts_sql, tuple(counts_params) if counts_params else ())


    # Convert each invoice row from the database into a JSON for front end
    return {
        "invoices": [
            {
                "id": i["id"], # Include the invoice ID so the frontend can identify each invoice
                "invoice_number": i["invoice_number"],
                "client_name": i["client_name"],
                "email": i["email"],
                "sent_date": i["sent_date"],
                "delivered_date": i["delivered_date"],
                "failed_date": i["failed_date"],
                "opened_date": i["opened_date"],
                "status": i["effective_status"]
            }
            for i in invoices
        ],
        "counts": dict(counts) if counts else {}  # Convert Row to dict
    }

@app.get("/invoice-delivery/<int:invoice_id>")
def invoice_detail(invoice_id): # 'invoice_id' comes from URL and converted into int
    """
    Get detailed information for a single invoice.
    Used by the invoice detail modal on the frontend.
    
    Args:
        invoice_id (int): The ID of the invoice to retrieve
    
    Returns:
        JSON: Complete invoice data including line items, client info, and calculated totals
    
    Raises:
        404: If invoice not found or doesn't belong to current user
    """

    # Get invoice with client details via LEFT JOIN:
    # Fetch a single invoice along with client details for the current user
    # - i.*: all invoice fields
    # - c.phone, c.address, etc.: client contact info
    # - LEFT JOIN ensures the invoice is returned even if the client record is missing
    # - WHERE i.id = ? AND i.user_id = ?: filter by invoice ID and current user
    invoice = query_one("""
        SELECT i.*, c.phone, c.address, c.city, c.state, c.postal_code, c.country
        FROM invoices i
        LEFT JOIN clients c ON i.client_id = c.id
        WHERE i.id = ? AND i.user_id = ?
    """, (invoice_id, 1))  # Fetch invoice for current user only

    if invoice is None:
        abort(404)  # Return 404 if invoice not found
    
    # Convert Row to dict for mutability
    invoice = dict(invoice)
    
    # ENFORCE DATA CONSISTENCY: If invoice has opened_date, status must be 'opened'
    if invoice['opened_date'] and invoice['opened_date'] not in ['null', 'None']:
        invoice['status'] = 'opened'
    
    # Get line items from invoice_items table
    # - description, quantity, rate, total: details of each invoice item
    # - WHERE invoice_id = ?: only get items belonging to this invoice
    # - ORDER BY id: make items displayed in the same order consistently
    items = query_all("""
        SELECT description, quantity, rate, total 
        FROM invoice_items 
        WHERE invoice_id = ?
        ORDER BY id
    """, (invoice_id,))  # Ordered by ID for consistent display
    
    # Build business location string from client address fields
    # - Collect non-empty parts of the address (address, city, state, postal code, country)
    # - Join them with commas to form a single string
    # - If all fields are empty, use a default message
    business_location_parts = []
    if invoice['address']:
        business_location_parts.append(invoice['address'])
    if invoice['city']:
        business_location_parts.append(invoice['city'])
    if invoice['state']:
        business_location_parts.append(invoice['state'])
    if invoice['postal_code']:
        business_location_parts.append(invoice['postal_code'])
    if invoice['country']:
        business_location_parts.append(invoice['country'])
    
    business_location = ', '.join(business_location_parts) if business_location_parts else 'No address provided'
    



    # Format dates properly
    def format_datetime(date_str):
        if not date_str:
            return None
        try:
            formats = [ # Helper function to format date/time strings consistently, tries multiple formats
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
                '%d/%m/%Y %H:%M:%S',
                '%d/%m/%Y'
            ]
            
            for fmt in formats: # Try each format, return on first success, else return original string
                try:
                    dt = datetime.strptime(date_str, fmt)
                    # Add default time if not present
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    continue
            
            return date_str
        except:
            return date_str
        


    
    # Parse sent date for due date calculation
    sent_date_str = invoice['sent_date'] if invoice['sent_date'] else None # Get sent_date string from invoice record

    # Default issue date and due date values, returned if parsing fails
    issue_date = None
    due_date = None
    
    if sent_date_str: # If sent_date exists, parse and calculate issue and due dates, otherwise keep as None
        try:
            # Handle both date and datetime formats
            date_part = sent_date_str.split()[0] if ' ' in sent_date_str else sent_date_str
            sent_date = datetime.strptime(date_part, '%Y-%m-%d')
            issue_date = sent_date.strftime('%Y-%m-%d')
            due_date = (sent_date + timedelta(days=30)).strftime('%Y-%m-%d')
        except Exception as e:
            print(f"Error parsing sent_date: {sent_date_str}, Error: {e}")
            issue_date = None
            due_date = None
    
    # Format items for frontend - IMPORTANT: Include quantity
    formatted_items = [] # List to hold formatted invoice items
    calculated_subtotal = 0.0 # To calculate subtotal from items if needed
    
    for item in items: # Process each invoice item
        try:
            quantity = int(item['quantity']) if item['quantity'] else 1
            rate = float(item['rate']) if item['rate'] else 0.0
            total = float(item['total']) if item['total'] else 0.0
        except (ValueError, TypeError): # Handle invalid data
            quantity = 1
            rate = 0.0
            total = 0.0
        
        calculated_subtotal += total # Sum up totals for subtotal calculation
        
        formatted_items.append({
            "description": item['description'] or "Service", # Default description if missing
            "qty": quantity,
            "rate": f"${rate:.2f}",
            "amount": f"${total:.2f}"
        })
    
    # Calculate amounts - use calculated values if database values are 0
    try:
        db_total = float(invoice['total']) if invoice['total'] else 0.0 # Get total from database
        db_subtotal = float(invoice['subtotal']) if invoice['subtotal'] else 0.0 # Get subtotal from database
        db_tax = float(invoice['tax']) if invoice['tax'] else 0.0 # Get tax from database
    except (ValueError, TypeError): # Handle invalid data
        db_total = 0.0
        db_subtotal = 0.0
        db_tax = 0.0
    
    # If database values are 0 but we have items, calculate from items
    if db_subtotal == 0.0 and calculated_subtotal > 0.0:
        subtotal_amount = calculated_subtotal # Use calculated subtotal
        tax_amount = subtotal_amount * 0.09  # 9% GST
        total_amount = subtotal_amount + tax_amount
    else:
        subtotal_amount = db_subtotal # Use database subtotal
        tax_amount = db_tax
        total_amount = db_total
    
    # Build final response data structure for frontend (Single invoice details)
    webhook_status = evaluate_webhook_configuration(
        get_setting('webhook_url', ''),
        get_setting('webhook_enabled', False)
    )

    response_data = {
        "id": invoice['id'],
        "invoice_number": normalize_invoice_number(invoice['invoice_number'], invoice['id']),
        "client_name": invoice['client_name'],
        "email": invoice['email'],
        "address": business_location,
        "status": invoice['status'],
        "sent_date": format_datetime(invoice['sent_date']) if invoice['sent_date'] else None,
        "delivered_date": format_datetime(invoice['delivered_date']) if invoice['delivered_date'] else None,
        "failed_date": format_datetime(invoice['failed_date']) if invoice['failed_date'] else None,
        "resent_date": format_datetime(invoice['resent_date']) if invoice['resent_date'] else None,
        "opened_date": format_datetime(invoice['opened_date']) if invoice['opened_date'] else None,
        "issue_date": issue_date,
        "due_date": due_date,
        "subtotal": f"${subtotal_amount:,.2f}",
        "tax": f"${tax_amount:,.2f}",
        "total": f"${total_amount:,.2f}",
        "items": formatted_items,
        "notes": invoice['notes'] if invoice['notes'] else "",
        "gst_rate": 0.09,  # Add GST rate for frontend
           "webhook_enabled": webhook_status['enabled'],
           "webhook_status": webhook_status
    }
    
    return response_data

# Resend invoice email to client
@app.post("/invoice-delivery/<int:invoice_id>/resend") 
def resend_invoice_email(invoice_id):

    """
    Resend invoice email to client.
    Sends the invoice to the client's email address with PDF attachment.
    
    Args:
        invoice_id (int): ID of the invoice to resend
    
    Returns:
        JSON: {
            'success': True/False,
            'message': Success or error message,
            'email': Recipient email address
        }
    """
    try:
        # Fetch full invoice details
        invoice = query_one("""
            SELECT i.id, i.invoice_number, i.client_name, i.email, i.status, i.total,
                   i.sent_date, i.subtotal, i.tax, i.notes, i.client_id,
                   i.failed_date, i.delivered_date,
                   c.address, c.city, c.state, c.postal_code, c.country
            FROM invoices i
            LEFT JOIN clients c ON i.client_id = c.id
            WHERE i.id = ? AND i.user_id = ?
        """, (invoice_id, 1))  # Current user only
        
        if not invoice: # Invoice not found or doesn't belong to user
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404
        
        # Verify email exists before attempting resend
        if not invoice['email']: # No email to send to
            return jsonify({'success': False, 'error': 'No email address found for this invoice'}), 400
        
        # Get line items
        items = query_all("""
            SELECT description, quantity, rate, total 
            FROM invoice_items 
            WHERE invoice_id = ?
            ORDER BY id
        """, (invoice_id,))
        
        # Format items
        formatted_items = []
        for item in items:
            try:
                quantity = int(item['quantity']) if item['quantity'] else 1
                rate = float(item['rate']) if item['rate'] else 0.0
                total = float(item['total']) if item['total'] else 0.0
            except (ValueError, TypeError):
                quantity = 1
                rate = 0.0
                total = 0.0
            
            formatted_items.append({
                "description": item['description'] or "Service",
                "qty": quantity,
                "rate": f"${rate:.2f}",
                "amount": f"${total:.2f}"
            })
        
        # Build business location
        business_location_parts = []
        if invoice['address']:
            business_location_parts.append(invoice['address'])
        if invoice['city']:
            business_location_parts.append(invoice['city'])
        if invoice['state']:
            business_location_parts.append(invoice['state'])
        if invoice['postal_code']:
            business_location_parts.append(invoice['postal_code'])
        if invoice['country']:
            business_location_parts.append(invoice['country'])
        
        business_location = ', '.join(business_location_parts) if business_location_parts else 'No address provided'
        
        # Calculate due date
        due_date = 'N/A'
        if invoice['sent_date']:
            try:
                date_part = invoice['sent_date'].split()[0] if ' ' in invoice['sent_date'] else invoice['sent_date']
                sent_obj = datetime.strptime(date_part, '%Y-%m-%d')
                due_date = (sent_obj + timedelta(days=30)).strftime('%Y-%m-%d')
            except:
                pass
        
        # Prepare full invoice data for email
        invoice_data = {
            'invoice_id': invoice_id,
            'invoice_number': invoice['invoice_number'],
            'client_name': invoice['client_name'],
            'email': invoice['email'],
            'address': business_location,
            'sent_date': invoice['sent_date'][:10] if invoice['sent_date'] else 'N/A',  # YYYY-MM-DD only
            'due_date': due_date,
            'subtotal': f"${float(invoice['subtotal'] or 0):,.2f}",
            'tax': f"${float(invoice['tax'] or 0):,.2f}",
            'total': f"${float(invoice['total'] or 0):,.2f}",
            'items': formatted_items,
            'notes': invoice['notes'] or '',
            'sender_email': app.config['MAIL_DEFAULT_SENDER'],
            'sender_phone': '+65 9123 4567'
        }
        
        # Send the invoice email with PDF attachment
        email_success, email_message, deliverability_warning = send_invoice_email(invoice['email'], invoice_data)
        
        if not email_success:
            return jsonify({'success': False, 'error': email_message}), 500
        
        # Track resend in resent_date column to preserve complete timeline history
        # KEEP failed_date (don't clear) to preserve original failure in timeline
        # CLEAR delivered_date if it was storing a second failure (not actual delivery)
        singapore_time = get_singapore_time()
        
        # Check if delivered_date is being used as second failure
        current_failed = invoice['failed_date'] is not None
        current_delivered = invoice['delivered_date'] is not None
        is_second_failure = current_failed and current_delivered and invoice['status'] not in ('delivered', 'opened')
        
        if is_second_failure:
            # Clear the second failure when resending
            execute("""
                UPDATE invoices
                SET status = 'pending',
                    failed_reason = NULL,
                    delivered_date = NULL,
                    resent_date = ?,
                    updated_at = ?
                WHERE id = ?
            """, (singapore_time, singapore_time, invoice_id,))
        else:
            # Normal resend, don't touch delivered_date
            execute("""
                UPDATE invoices
                SET status = 'pending',
                    failed_reason = NULL,
                    resent_date = ?,
                    updated_at = ?
                WHERE id = ?
            """, (singapore_time, singapore_time, invoice_id,))
        
        print(f"Invoice {invoice['invoice_number']} resent to {invoice['email']}")
        
        return jsonify({
            'success': True,
            'message': f'Invoice sent to {invoice["email"]}',
            'email': invoice['email'],
            'deliverability_warning': deliverability_warning
        })
        
    except Exception as e: # Catch-all for unexpected errors
        print(f"Error resending invoice {invoice_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'Failed to resend invoice'}), 500


# Download invoice as PDF
@app.route("/invoice-delivery/<int:invoice_id>/download-pdf", methods=['GET'])
def download_invoice_pdf(invoice_id):
    """
    Download invoice as PDF file
    
    Args:
        invoice_id (int): ID of the invoice to download
    
    Returns:
        PDF file for download or 404 error
    """
    try:
        # Fetch invoice with client details
        invoice = query_one("""
            SELECT i.*, c.phone, c.address, c.city, c.state, c.postal_code, c.country
            FROM invoices i
            LEFT JOIN clients c ON i.client_id = c.id
            WHERE i.id = ? AND i.user_id = ?
        """, (invoice_id, 1))
        
        if not invoice:
            abort(404)
        
        # Get line items
        items = query_all("""
            SELECT description, quantity, rate, total 
            FROM invoice_items 
            WHERE invoice_id = ?
            ORDER BY id
        """, (invoice_id,))
        
        # Format items for PDF
        formatted_items = []
        for item in items:
            try:
                quantity = int(item['quantity']) if item['quantity'] else 1
                rate = float(item['rate']) if item['rate'] else 0.0
                total = float(item['total']) if item['total'] else 0.0
            except (ValueError, TypeError):
                quantity = 1
                rate = 0.0
                total = 0.0

            formatted_items.append({
                "description": item['description'] or "Service",
                "qty": quantity,
                "rate": f"${rate:.2f}",
                "amount": f"${total:.2f}"
            })

        # Calculate amounts
        try:
            db_total = float(invoice['total']) if invoice['total'] else 0.0
            db_subtotal = float(invoice['subtotal']) if invoice['subtotal'] else 0.0
            db_tax = float(invoice['tax']) if invoice['tax'] else 0.0
        except (ValueError, TypeError):
            db_total = 0.0
            db_subtotal = 0.0
            db_tax = 0.0

        # Parse sent_date - handle both date and datetime formats
        sent_date_str = 'N/A'
        due_date_str = 'N/A'

        if invoice['sent_date']:
            try:
                date_part = invoice['sent_date'].split()[0] if ' ' in str(invoice['sent_date']) else str(invoice['sent_date'])
                sent_date_obj = datetime.strptime(date_part, '%Y-%m-%d')
                sent_date_str = str(invoice['sent_date'])
                due_date_str = (sent_date_obj + timedelta(days=30)).strftime('%Y-%m-%d')
            except Exception as date_err:
                print(f"Date parsing error: {date_err}")
                sent_date_str = str(invoice['sent_date'])

        # Build business location string
        business_location_parts = []
        if invoice['address']:
            business_location_parts.append(invoice['address'])
        if invoice['city']:
            business_location_parts.append(invoice['city'])
        if invoice['state']:
            business_location_parts.append(invoice['state'])
        if invoice['postal_code']:
            business_location_parts.append(invoice['postal_code'])
        if invoice['country']:
            business_location_parts.append(invoice['country'])

        business_location = ', '.join(business_location_parts) if business_location_parts else 'No address provided'

        # Build invoice data for PDF generation
        invoice_data = {
            "invoice_number": invoice['invoice_number'],
            "client_name": invoice['client_name'],
            "email": invoice['email'],
            "address": business_location,
            "sent_date": sent_date_str,
            "due_date": due_date_str,
            "subtotal": f"${db_subtotal:,.2f}",
            "tax": f"${db_tax:,.2f}",
            "total": f"${db_total:,.2f}",
            "items": formatted_items,
            "notes": invoice['notes'] if invoice['notes'] else "",
            "sender_email": app.config['MAIL_DEFAULT_SENDER'],
            "sender_phone": "+65 9123 4567"
        }

        # Generate PDF
        pdf_buffer = generate_invoice_pdf(invoice_data)

        # Reset buffer position to start before sending
        pdf_buffer.seek(0)

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{invoice['invoice_number']}.pdf"
        )
        
    except Exception as e:
        print(f"Error downloading invoice PDF {invoice_id}: {e}")
        import traceback
        traceback.print_exc()
        abort(500)


@app.get("/invoice-delivery/<int:invoice_id>/preview")
def preview_invoice(invoice_id):
    """Employee preview of client invoice view without changing opened status."""
    try:
        invoice = query_one(
            "SELECT i.*, c.address FROM invoices i LEFT JOIN clients c ON i.client_id = c.id WHERE i.id = ? AND i.user_id = ?",
            (invoice_id, 1)
        )

        if not invoice:
            abort(404)

        items = query_all(
            "SELECT description, quantity, rate, total FROM invoice_items WHERE invoice_id = ? ORDER BY id",
            (invoice_id,)
        )

        token = generate_verification_token(invoice_id)
        html_response = build_invoice_html(
            invoice,
            items,
            invoice_id,
            token,
            show_opened_notice=False
        )
        return html_response

    except Exception as e:
        print(f"Error rendering invoice preview {invoice_id}: {e}")
        traceback.print_exc()
        abort(500)


# Email tracking pixel endpoint
@app.route("/email-tracking/<int:invoice_id>/<token>", methods=['GET'])
def track_email_open(invoice_id, token):
    """
    Track email opens via pixel beacon
    
    Args:
        invoice_id (int): The ID of the invoice to track
        token (str): Security token to verify the request
    
    Returns:
        1x1 transparent PNG pixel image
    """
    try:
        # Verify the token is correct
        expected_token = generate_tracking_token(invoice_id)
        if token != expected_token:
            print(f"Invalid tracking token for invoice {invoice_id}")
            abort(403)  # Forbidden
        
        # Fetch the invoice to verify it exists and belongs to current user
        invoice = query_one(
            "SELECT id, opened_date FROM invoices WHERE id = ? AND user_id = ?",
            (invoice_id, 1)
        )
        
        if not invoice:
            print(f"Invoice {invoice_id} not found")
            abort(404)
        
        # Only update opened_date if it hasn't been set yet (first open)
        if not invoice['opened_date']:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            execute(
                """
                UPDATE invoices
                SET opened_date = ?, status = 'opened', failed_reason = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (current_time, invoice_id)
            )
            print(f"✓ Email opened tracked for invoice {invoice_id} at {current_time}")
        
        # Get client IP for logging (optional, for analytics)
        client_ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')
        print(f"  Client IP: {client_ip}, User Agent: {user_agent}")
        
        # Return 1x1 transparent PNG pixel
        response = app.make_response(TRACKING_PIXEL)
        response.headers['Content-Type'] = 'image/png'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        return response
        
    except Exception as e:
        print(f"Error tracking email open: {e}")
        # Return pixel anyway to not break email rendering
        response = app.make_response(TRACKING_PIXEL)
        response.headers['Content-Type'] = 'image/png'
        return response


# Manual mark as opened (for testing email tracking)
@app.post("/invoice-delivery/<int:invoice_id>/mark-opened")
def mark_invoice_as_opened(invoice_id):
    """
    Manually mark an invoice as opened (for testing).
    Used to test email tracking functionality without needing real email opens.
    
    Args:
        invoice_id (int): ID of the invoice to mark as opened
    
    Returns:
        JSON: Success/failure response
    """
    try:
        # Fetch the invoice
        invoice = query_one(
            "SELECT id, opened_date FROM invoices WHERE id = ? AND user_id = ?",
            (invoice_id, 1)
        )
        
        if not invoice:
            return jsonify({
                'success': False,
                'message': 'Invoice not found'
            }), 404
        
        # Only update if not already marked as opened
        if not invoice['opened_date']:
            singapore_time = get_singapore_time()
            execute(
                """
                UPDATE invoices
                SET opened_date = ?, status = 'opened', failed_reason = NULL, updated_at = ?
                WHERE id = ?
                """,
                (singapore_time, singapore_time, invoice_id)
            )
            print(f"✓ Invoice {invoice_id} manually marked as opened at {singapore_time}")
        
        return jsonify({
            'success': True,
            'message': 'Invoice marked as opened'
        })
        
    except Exception as e:
        print(f"Error marking invoice as opened: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


# Manual Admin Actions for Delivery Status
@app.post("/invoice-delivery/<int:invoice_id>/mark-delivered")
def mark_invoice_as_delivered(invoice_id):
    """
    Manually mark invoice as delivered (admin action).
    Used when admin verifies delivery in TurboSMTP dashboard.
    
    Args:
        invoice_id (int): ID of the invoice to mark as delivered
    
    Returns:
        JSON: Success/failure response
    """
    try:
        invoice = query_one(
            "SELECT id, status FROM invoices WHERE id = ? AND user_id = ?",
            (invoice_id, 1)
        )
        
        if not invoice:
            return jsonify({'success': False, 'message': 'Invoice not found'}), 404
        
        # Mark as delivered while preserving all date history for complete timeline
        singapore_time = get_singapore_time()
        execute("""
            UPDATE invoices
            SET status = 'delivered',
                delivered_date = ?,
                failed_reason = NULL,
                updated_at = ?
            WHERE id = ?
        """, (singapore_time, singapore_time, invoice_id,))
        
        print(f"✓ Invoice {invoice_id} manually marked as delivered")
        
        return jsonify({
            'success': True,
            'message': 'Invoice marked as delivered'
        })
        
    except Exception as e:
        print(f"Error marking invoice as delivered: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.post("/invoice-delivery/<int:invoice_id>/mark-failed")
def mark_invoice_as_failed(invoice_id):
    """
    Manually mark invoice as failed (admin action).
    Used when admin verifies bounce/rejection in TurboSMTP dashboard.
    
    Args:
        invoice_id (int): ID of the invoice to mark as failed
    
    Returns:
        JSON: Success/failure response
    """
    try:
        invoice = query_one(
            "SELECT id, status, failed_date FROM invoices WHERE id = ? AND user_id = ?",
            (invoice_id, 1)
        )
        
        if not invoice:
            return jsonify({'success': False, 'message': 'Invoice not found'}), 404
        
        # Get full invoice data to check for resent_date
        full_invoice = query_one(
            "SELECT id, status, failed_date, resent_date, delivered_date FROM invoices WHERE id = ?",
            (invoice_id,)
        )
        
        singapore_time = get_singapore_time()
        
        # Mark as failed logic:
        # - If already failed: Just update reason
        # - If was resent (resent_date exists) and already has failed_date:
        #   Store this NEW failure in delivered_date (to track 2nd failure)
        # - Otherwise: Set failed_date normally
        
        if full_invoice['status'] == 'failed':
            # Already failed, just update the reason without changing dates
            execute("""
                UPDATE invoices
                SET failed_reason = 'Delivery failed - verify email address',
                    updated_at = ?
                WHERE id = ?
            """, (singapore_time, invoice_id,))
        elif full_invoice['resent_date'] and full_invoice['failed_date']:
            # Was resent and already failed before - track this 2nd failure in delivered_date
            execute("""
                UPDATE invoices
                SET status = 'failed',
                    failed_reason = 'Delivery failed - verify email address',
                    delivered_date = ?,
                    updated_at = ?
                WHERE id = ?
            """, (singapore_time, singapore_time, invoice_id,))
        else:
            # First failure or no resend - normal failed_date tracking
            execute("""
                UPDATE invoices
                SET status = 'failed',
                    failed_reason = 'Delivery failed - verify email address',
                    failed_date = ?,
                    updated_at = ?
                WHERE id = ?
            """, (singapore_time, singapore_time, invoice_id,))
        
        print(f"✓ Invoice {invoice_id} manually marked as failed")
        
        return jsonify({
            'success': True,
            'message': 'Invoice marked as failed'
        })
        
    except Exception as e:
        print(f"Error marking invoice as failed: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.post("/invoice-delivery/<int:invoice_id>/mark-pending")
def mark_invoice_as_pending(invoice_id):
    """
    Manually mark invoice as pending (admin action).
    Used when admin needs to reset invoice status to pending (e.g., after false positive).
    
    Args:
        invoice_id (int): ID of the invoice to mark as pending
    
    Returns:
        JSON: Success/failure response
    """
    try:
        invoice = query_one(
            "SELECT id, status FROM invoices WHERE id = ? AND user_id = ?",
            (invoice_id, 1)
        )
        
        if not invoice:
            return jsonify({'success': False, 'message': 'Invoice not found'}), 404
        
        # Reset to pending (clears all status dates except sent_date and resent_date)
        singapore_time = get_singapore_time()
        execute("""
            UPDATE invoices
            SET status = 'pending',
                failed_reason = NULL,
                delivered_date = NULL,
                updated_at = ?
            WHERE id = ?
        """, (singapore_time, invoice_id,))
        
        print(f"✓ Invoice {invoice_id} manually marked as pending")
        
        return jsonify({
            'success': True,
            'message': 'Invoice status reset to pending'
        })
        
    except Exception as e:
        print(f"Error marking invoice as pending: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# TurboSMTP Webhook Endpoint (for future use)
@app.post("/webhooks/turbosmtp")
def turbosmtp_webhook():
    """
    Webhook endpoint to receive TurboSMTP delivery events.
    
    When TurboSMTP webhooks are enabled, this receives event notifications:
    - PROCESSED: Email accepted by TurboSMTP
    - DELIVERED: Email successfully delivered to recipient's mailbox
    - OPENED: Recipient opened the email
    - BOUNCED: Email bounced (hard/soft)
    - COMPLAINT: Recipient marked as spam
    - UNSUBSCRIBED: Recipient unsubscribed
    
    Webhook must be configured in TurboSMTP dashboard:
    https://app.serversmtp.com/en/dashboard/webhooks
    
    Expected payload format:
    {
        "event": "DELIVERED",
        "mid": "message_id",
        "email": "recipient@example.com",
        "timestamp": 1234567890,
        ...
    }
    
    Returns:
        JSON: Acknowledgment response
    """
    try:
        if not is_turbosmtp_webhook_request(request):
            print("[Webhook] Rejected non-TurboSMTP webhook source")
            return jsonify({'success': False, 'error': 'Unauthorized webhook source'}), 403

        # Check if webhooks are enabled in settings
        webhook_enabled = get_setting('webhook_enabled', False)
        if not webhook_enabled:
            print("[Webhook] Webhooks disabled in settings - ignoring event")
            return jsonify({'success': True, 'message': 'Webhooks disabled'}), 200
        
        # Parse webhook payload
        if not request.is_json:
            print("[Webhook] Invalid content type - expecting JSON")
            return jsonify({'success': False, 'error': 'Invalid content type'}), 400
        
        payload = request.get_json()
        print(f"[Webhook] Received TurboSMTP event: {json.dumps(payload, indent=2)}")
        
        # Extract event details
        event_type = payload.get('event')
        message_id = payload.get('mid')  # TurboSMTP message ID
        recipient_email = payload.get('email')
        timestamp = payload.get('timestamp')
        
        if not event_type or not recipient_email:
            print("[Webhook] Missing required fields: event and email")
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Find invoice by recipient email (most recent pending/delivered invoice)
        invoice = query_one("""
            SELECT id, invoice_number, status, email
            FROM invoices
            WHERE email = ? AND user_id = ?
            ORDER BY sent_date DESC
            LIMIT 1
        """, (recipient_email, 1))
        
        if not invoice:
            print(f"[Webhook] No invoice found for email: {recipient_email}")
            # Return success anyway to prevent webhook retries
            return jsonify({'success': True, 'message': 'No matching invoice'}), 200
        
        invoice_id = invoice['id']
        current_status = invoice['status']
        
        # Process event based on type
        if event_type == 'DELIVERED':
            # Only update if still pending (don't downgrade from opened)
            if current_status == 'pending':
                execute("""
                    UPDATE invoices
                    SET status = 'delivered',
                        failed_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (invoice_id,))
                print(f"✓ Invoice {invoice['invoice_number']} marked as delivered via webhook")
        
        elif event_type == 'OPENED':
            # Mark as opened (webhook open tracking, in addition to pixel tracking)
            if not query_one("SELECT opened_date FROM invoices WHERE id = ? AND opened_date IS NOT NULL", (invoice_id,)):
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                execute("""
                    UPDATE invoices
                    SET opened_date = ?,
                        status = 'opened',
                        failed_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (current_time, invoice_id))
                print(f"✓ Invoice {invoice['invoice_number']} marked as opened via webhook")
        
        elif event_type in ['BOUNCED', 'COMPLAINT']:
            # Mark as failed
            reason = 'Email bounced' if event_type == 'BOUNCED' else 'Marked as spam'
            execute("""
                UPDATE invoices
                SET status = 'pending',
                    failed_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (reason, invoice_id))
            print(f"✓ Invoice {invoice['invoice_number']} marked as failed: {reason}")
        
        elif event_type == 'PROCESSED':
            # Email accepted by TurboSMTP but not yet delivered
            # Keep as pending with queued note
            print(f"Invoice {invoice['invoice_number']} processed by TurboSMTP (queued)")
        
        # Return success to acknowledge webhook
        return jsonify({
            'success': True,
            'message': f'Event {event_type} processed for invoice {invoice["invoice_number"]}'
        }), 200
        
    except Exception as e:
        print(f"[Webhook] Error processing TurboSMTP webhook: {e}")
        traceback.print_exc()
        # Return 200 anyway to prevent webhook retries
        return jsonify({'success': True, 'error': 'Internal error'}), 200


# Debug endpoint to check what link gets generated
@app.get("/debug/view-invoice-link/<int:invoice_id>")
def debug_view_invoice_link(invoice_id):
    """
    Debug endpoint - shows what link would be generated for an invoice
    Helps verify the token generation is working
    """
    try:
        token = generate_verification_token(invoice_id)
        link = f"http://localhost:5000/view-invoice/{invoice_id}/{token}"
        
        return jsonify({
            'invoice_id': invoice_id,
            'token': token,
            'full_link': link,
            'message': 'This is the link that should appear in the email'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Debug endpoint to check invoice status in database
@app.get("/debug/invoice-status/<int:invoice_id>")
def debug_invoice_status(invoice_id):
    """
    Debug endpoint - shows the actual status and opened_date in the database
    Used to diagnose status update issues
    """
    try:
        invoice = query_one(
            "SELECT id, invoice_number, status, opened_date, created_at, updated_at FROM invoices WHERE id = ?",
            (invoice_id,)
        )
        
        if not invoice:
            return jsonify({'error': 'Invoice not found'}), 404
        
        return jsonify({
            'invoice_id': invoice['id'],
            'invoice_number': invoice['invoice_number'],
            'status': invoice['status'],
            'opened_date': invoice['opened_date'],
            'created_at': invoice['created_at'],
            'updated_at': invoice['updated_at'],
            'message': 'Current database status for this invoice'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Debug endpoint to see any incoming requests
@app.route("/view-invoice/", defaults={'path': ''})
@app.route("/view-invoice/<path:path>", methods=['GET'])
def debug_view_invoice(path):
    """Debug endpoint to capture all requests to view-invoice"""
    print(f"\n{'='*60}")
    print(f"[DEBUG] Request received to /view-invoice/{path}")
    print(f"  Full URL: {request.url}")
    print(f"  Full Path: {request.full_path}")
    print(f"  Args: {request.args}")
    print(f"  Path segments: {path}")
    print(f"{'='*60}\n")
    
    # Try to extract invoice_id and token from path
    parts = path.strip('/').split('/')
    if len(parts) >= 2:
        try:
            invoice_id = int(parts[0])
            token = parts[1]
            print(f"  Extracted: invoice_id={invoice_id}, token={token}")
            # Redirect to actual endpoint
            return redirect(f'/view-invoice/{invoice_id}/{token}', code=307)
        except:
            pass
    
    return jsonify({'error': 'Invalid URL format'}), 400


def build_invoice_html(
    invoice,
    items,
    invoice_id,
    token=None,
    sender_email='emp@gmail.com',
    sender_phone='+65 9123 4567',
    show_opened_notice=True
):
    """Build the HTML used for public invoice view and PDF output."""
    if token is None:
        token = generate_verification_token(invoice_id)

    # Build invoice items HTML
    items_html = ""
    for item in items:
        try:
            qty = int(item['quantity']) if item['quantity'] else 1
            rate = float(item['rate']) if item['rate'] else 0.0
            amt = float(item['total']) if item['total'] else 0.0
        except (ValueError, TypeError):
            qty = 1
            rate = 0.0
            amt = 0.0

        items_html += f"""
        <tr>
            <td style=\"padding: 10px; border-bottom: 1px solid #ecf0f1; text-align: left;\">{item['description']}</td>
            <td style=\"padding: 10px; border-bottom: 1px solid #ecf0f1; text-align: center;\">{qty}</td>
            <td style=\"padding: 10px; border-bottom: 1px solid #ecf0f1; text-align: right;\">${rate:.2f}</td>
            <td style=\"padding: 10px; border-bottom: 1px solid #ecf0f1; text-align: right; font-weight: bold;\">${amt:.2f}</td>
        </tr>
        """

    # Format amounts
    try:
        subtotal = float(invoice['subtotal']) if invoice['subtotal'] else 0.0
        tax = float(invoice['tax']) if invoice['tax'] else 0.0
        total = float(invoice['total']) if invoice['total'] else 0.0
    except (ValueError, TypeError):
        subtotal = 0.0
        tax = 0.0
        total = 0.0

    # Get sent date for display
    sent_date_display = invoice['sent_date'] if invoice['sent_date'] else 'N/A'
    due_date_obj = None
    if invoice['sent_date']:
        try:
            date_part = invoice['sent_date'].split()[0] if ' ' in invoice['sent_date'] else invoice['sent_date']
            sent_dt = datetime.strptime(date_part, '%Y-%m-%d')
            due_date_obj = (sent_dt + timedelta(days=30)).strftime('%Y-%m-%d')
        except Exception:
            due_date_obj = None

    due_date_display = due_date_obj if due_date_obj else 'N/A'

    notes_html = ""
    if invoice['notes']:
        notes_html = (
            f"<div class=\"notes\"><div class=\"section-heading\">Notes:</div>"
            f"<div class=\"notes-text\">{invoice['notes']}</div></div>"
        )

    opened_notice_html = ""
    if show_opened_notice:
        opened_notice_html = """
            <div class=\"success-message\">
                ✓ Your invoice has been recorded as opened. Thank you for reviewing it!
            </div>
        """

    html_response = f"""
    <html>
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
        <title>Invoice {invoice['invoice_number']}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.5;
                color: #333;
            }}
            .page {{
                width: 8.5in;
                height: 11in;
                margin: 20px auto;
                padding: 0.5in;
                background: white;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 30px;
            }}
            .company-name {{
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
            }}
            .sender-info {{
                font-size: 12px;
                color: #2c3e50;
                margin-top: 6px;
            }}
            .invoice-title {{
                font-size: 20px;
                font-weight: bold;
                color: #e74c3c;
            }}
            .invoice-details {{
                display: flex;
                gap: 40px;
                margin-bottom: 30px;
            }}
            .detail-item {{
                flex: 1;
            }}
            .detail-label {{
                font-weight: bold;
                font-size: 11px;
                color: #34495e;
                margin-bottom: 2px;
            }}
            .detail-value {{
                font-size: 12px;
                color: #2c3e50;
            }}
            .section-heading {{
                font-weight: bold;
                font-size: 11px;
                color: #2c3e50;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .bill-to {{
                margin-bottom: 30px;
            }}
            .bill-to-name {{
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 3px;
            }}
            .bill-to-email {{
                font-size: 12px;
                color: #2c3e50;
                margin-bottom: 3px;
            }}
            .bill-to-address {{
                font-size: 12px;
                color: #2c3e50;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
            }}
            th {{
                background-color: #ecf0f1;
                padding: 10px;
                text-align: left;
                font-size: 11px;
                font-weight: bold;
                color: #2c3e50;
                border: 1px solid #bdc3c7;
            }}
            td {{
                padding: 10px;
                font-size: 11px;
                color: #2c3e50;
                border: 1px solid #bdc3c7;
            }}
            .qty-col {{ text-align: center; }}
            .rate-col {{ text-align: right; }}
            .amount-col {{ text-align: right; }}
            .totals {{
                margin-bottom: 30px;
                display: flex;
                justify-content: flex-end;
            }}
            .totals-box {{
                width: 250px;
            }}
            .total-row {{
                display: flex;
                justify-content: space-between;
                padding: 6px 0;
                font-size: 12px;
                border-bottom: 1px solid #ecf0f1;
            }}
            .total-row.final {{ 
                font-weight: bold;
                font-size: 13px;
                border-bottom: 2px solid #2c3e50;
                padding: 8px 0;
            }}
            .notes {{
                margin-bottom: 30px;
            }}
            .notes-text {{
                font-size: 11px;
                color: #2c3e50;
                line-height: 1.4;
            }}
            .footer {{
                text-align: center;
                font-size: 9px;
                color: #95a5a6;
                border-top: 1px solid #ecf0f1;
                padding-top: 20px;
                margin-top: 30px;
            }}
            .action-buttons {{
                text-align: center;
                margin: 20px 0;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 5px;
            }}
            .btn {{
                display: inline-block;
                margin: 0 10px;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }}
            .btn-download {{
                background-color: #27ae60;
                color: white;
            }}
            .btn-print {{
                background-color: #3498db;
                color: white;
            }}
            .success-message {{
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                color: #155724;
                padding: 12px;
                border-radius: 5px;
                margin-bottom: 20px;
                font-size: 12px;
                text-align: center;
            }}
            @media print {{
                body {{ margin: 0; padding: 0; }}
                .page {{ margin: 0; box-shadow: none; }}
                .action-buttons {{ display: none; }}
                .success-message {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class=\"page\">
            {opened_notice_html}
            
            <div class=\"header\">
                <div>
                    <div class=\"company-name\">FourVoice</div>
                    <div class=\"sender-info\">Sender Email: {sender_email}</div>
                    <div class=\"sender-info\">Sender Phone: {sender_phone}</div>
                </div>
                <div class=\"invoice-title\">INVOICE</div>
            </div>
            
            <div class=\"invoice-details\">
                <div class=\"detail-item\">
                    <div class=\"detail-label\">Invoice #:</div>
                    <div class=\"detail-value\">{invoice['invoice_number']}</div>
                </div>
                <div class=\"detail-item\">
                    <div class=\"detail-label\">Invoice Date:</div>
                    <div class=\"detail-value\">{sent_date_display}</div>
                </div>
                <div class=\"detail-item\">
                    <div class=\"detail-label\">Due Date:</div>
                    <div class=\"detail-value\">{due_date_display}</div>
                </div>
            </div>
            
            <div class=\"bill-to\">
                <div class=\"section-heading\">Bill To:</div>
                <div class=\"bill-to-name\">{invoice['client_name']}</div>
                <div class=\"bill-to-email\">{invoice['email']}</div>
                <div class=\"bill-to-address\">{invoice['address'] if invoice['address'] else ''}</div>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Description</th>
                        <th class=\"qty-col\">Qty</th>
                        <th class=\"rate-col\">Rate</th>
                        <th class=\"amount-col\">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    {items_html}
                </tbody>
            </table>
            
            <div class=\"totals\">
                <div class=\"totals-box\">
                    <div class=\"total-row\">
                        <span>Subtotal:</span>
                        <span>${subtotal:,.2f}</span>
                    </div>
                    <div class=\"total-row\">
                        <span>Tax (9% GST):</span>
                        <span>${tax:,.2f}</span>
                    </div>
                    <div class=\"total-row final\">
                        <span>Total:</span>
                        <span>${total:,.2f}</span>
                    </div>
                </div>
            </div>
            
            {notes_html}
            
            <div class=\"footer\">
                <p>Thank you for your business!</p>
                <p>FourVoice - Professional Invoice Management</p>
                <p>This invoice was automatically generated.</p>
            </div>
        </div>
        
        <div class=\"action-buttons\">
            <a href=\"/view-invoice/{invoice_id}/{token}/download\" class=\"btn btn-download\">⬇ Download PDF</a>
            <a href=\"javascript:window.print()\" class=\"btn btn-print\">🖨 Print Invoice</a>
        </div>
    </body>
    </html>
    """

    return html_response


# Public invoice view endpoint (click-tracked by TurboSMTP)
@app.route("/view-invoice/<int:invoice_id>/<token>", methods=['GET'])
def view_invoice_public(invoice_id, token):
    """
    Public endpoint for clients to view their invoice.
    This link is clicked by the client from the email, which TurboSMTP will track.
    When clicked, it marks the invoice as opened and displays the invoice details.
    
    Args:
        invoice_id (int): ID of the invoice
        token (str): Security token to verify the request
    
    Returns:
        HTML page with invoice details or error message
    """
    try:
        print(f"\n{'='*60}")
        print(f"[VIEW-INVOICE] Endpoint called")
        print(f"  Invoice ID: {invoice_id} (type: {type(invoice_id)})")
        print(f"  Token: {token}")
        
        # Verify the token is correct
        expected_token = generate_verification_token(invoice_id)
        print(f"  Expected Token: {expected_token}")
        print(f"  Token Match: {token == expected_token}")
        
        if token != expected_token:
            print(f"  ❌ Token mismatch!")
            print(f"{'='*60}\n")
            return """
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Invoice Verification</title>
                <style>
                    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
                    .container { max-width: 600px; margin: 50px auto; background: white; padding: 40px; border-radius: 8px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                    .error { color: #e74c3c; }
                    .icon { font-size: 60px; margin-bottom: 20px; }
                    h1 { color: #2c3e50; margin-top: 0; }
                    p { color: #7f8c8d; line-height: 1.6; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">❌</div>
                    <h1 class="error">Invalid Verification Link</h1>
                    <p>This link is invalid or has expired. Please contact support if you need assistance.</p>
                </div>
            </body>
            </html>
            """, 403
        
        # Fetch the invoice
        print(f"  ✓ Token verified, fetching invoice...")
        invoice = query_one(
            "SELECT i.*, c.address FROM invoices i LEFT JOIN clients c ON i.client_id = c.id WHERE i.id = ?",
            (invoice_id,)
        )
        # Mark as opened if first view
        if invoice and not invoice['opened_date']:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            execute(
                """
                UPDATE invoices
                SET opened_date = ?, status = 'opened', failed_reason = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (current_time, invoice_id)
            )

        # Get line items
        items = query_all(
            "SELECT description, quantity, rate, total FROM invoice_items WHERE invoice_id = ? ORDER BY id",
            (invoice_id,)
        )

        html_response = build_invoice_html(invoice, items, invoice_id, token)

        print(f"  ✓ Invoice HTML page generated successfully")
        print(f"{'='*60}\n")
        return html_response
        
    except Exception as e:
        print(f"  ❌ Error viewing invoice: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
        print(f"{'='*60}\n")
        return """
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Error</title>
            <style>
                body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 50px auto; background: white; padding: 40px; border-radius: 8px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .error { color: #e74c3c; }
                .icon { font-size: 60px; margin-bottom: 20px; }
                h1 { color: #2c3e50; margin-top: 0; }
                p { color: #7f8c8d; line-height: 1.6; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">❌</div>
                <h1 class="error">Error Processing Request</h1>
                <p>There was an error processing your request. Please try again or contact support.</p>
            </div>
        </body>
        </html>
        """, 500


# Download PDF from public invoice view
@app.route("/view-invoice/<int:invoice_id>/<token>/download", methods=['GET'])
def download_invoice_public(invoice_id, token):
    """
    Public endpoint for clients to download their invoice PDF.
    Uses the same token-based security as the view endpoint.
    
    Args:
        invoice_id (int): ID of the invoice
        token (str): Security token to verify the request
    
    Returns:
        PDF file or error response
    """
    try:
        print(f"\n{'='*60}")
        print(f"[DOWNLOAD-PDF] Request received")
        print(f"  Invoice ID: {invoice_id}")
        print(f"  Token: {token}")
        
        # Verify the token is correct
        expected_token = generate_verification_token(invoice_id)
        if token != expected_token:
            print(f"  ❌ Token mismatch!")
            print(f"{'='*60}\n")
            abort(403)
        
        # Fetch the invoice
        print(f"  ✓ Token verified, fetching invoice...")
        invoice = query_one(
            "SELECT i.*, c.address FROM invoices i LEFT JOIN clients c ON i.client_id = c.id WHERE i.id = ?",
            (invoice_id,)
        )
        
        if not invoice:
            print(f"  ❌ Invoice not found!")
            print(f"{'='*60}\n")
            abort(404)
        
        print(f"  ✓ Invoice found: {invoice['invoice_number']}")
        
        # Get line items
        items = query_all(
            "SELECT description, quantity, rate, total FROM invoice_items WHERE invoice_id = ? ORDER BY id",
            (invoice_id,)
        )
        
        # Format items for PDF generation
        formatted_items = []
        for item in items:
            try:
                quantity = int(item['quantity']) if item['quantity'] else 1
                rate = float(item['rate']) if item['rate'] else 0.0
                total = float(item['total']) if item['total'] else 0.0
            except (ValueError, TypeError):
                quantity = 1
                rate = 0.0
                total = 0.0

            formatted_items.append({
                "description": item['description'] or "Service",
                "qty": quantity,
                "rate": f"${rate:.2f}",
                "amount": f"${total:.2f}"
            })

        # Prepare invoice data for PDF generation
        invoice_data = {
            'invoice_id': invoice_id,
            'invoice_number': invoice['invoice_number'],
            'client_name': invoice['client_name'],
            'email': invoice['email'],
            'address': invoice['address'] or 'N/A',
            'sent_date': str(invoice['sent_date']) if invoice['sent_date'] else 'N/A',
            'due_date': None,
            'subtotal': f"${float(invoice['subtotal'] or 0):,.2f}",
            'tax': f"${float(invoice['tax'] or 0):,.2f}",
            'total': f"${float(invoice['total'] or 0):,.2f}",
            'notes': invoice['notes'] or '',
            'items': formatted_items,
            'sender_email': app.config['MAIL_DEFAULT_SENDER'],
            'sender_phone': '+65 9123 4567'
        }

        if invoice['sent_date']:
            try:
                date_part = invoice['sent_date'].split()[0] if ' ' in invoice['sent_date'] else invoice['sent_date']
                sent_dt = datetime.strptime(date_part, '%Y-%m-%d')
                invoice_data['due_date'] = (sent_dt + timedelta(days=30)).strftime('%Y-%m-%d')
            except Exception:
                invoice_data['due_date'] = 'N/A'
        else:
            invoice_data['due_date'] = 'N/A'

        # Generate PDF
        print(f"  → Generating PDF...")
        pdf_buffer = generate_invoice_pdf(invoice_data)

        # Create response
        response = send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{invoice['invoice_number']}.pdf"
        )
        
        print(f"  ✓ PDF generated and returned successfully")
        print(f"{'='*60}\n")
        return response
        
    except Exception as e:
        print(f"  ❌ Error downloading PDF: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
        print(f"{'='*60}\n")
        abort(500)


# Client invoice verification endpoint (public - no auth required)
@app.route("/invoice-verification/<int:invoice_id>/<token>", methods=['GET'])
def verify_invoice_read(invoice_id, token):
    """
    Client verification link - when client clicks "I have read this invoice" in email
    This marks the invoice as opened and shows a confirmation page.
    
    Args:
        invoice_id (int): ID of the invoice
        token (str): Security token to verify the request
    
    Returns:
        HTML page with success or error message
    """
    try:
        # Verify the token is correct
        expected_token = generate_verification_token(invoice_id)
        if token != expected_token:
            return """
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Invoice Verification</title>
                <style>
                    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
                    .container { max-width: 600px; margin: 50px auto; background: white; padding: 40px; border-radius: 8px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                    .error { color: #e74c3c; }
                    .icon { font-size: 60px; margin-bottom: 20px; }
                    h1 { color: #2c3e50; margin-top: 0; }
                    p { color: #7f8c8d; line-height: 1.6; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">❌</div>
                    <h1 class="error">Invalid Verification Link</h1>
                    <p>This link is invalid or has expired. Please contact support if you need assistance.</p>
                </div>
            </body>
            </html>
            """, 403
        
        # Fetch the invoice - no user_id check needed for client verification
        invoice = query_one(
            "SELECT id, opened_date, invoice_number FROM invoices WHERE id = ?",
            (invoice_id,)
        )
        
        if not invoice:
            return """
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Invoice Verification</title>
                <style>
                    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
                    .container { max-width: 600px; margin: 50px auto; background: white; padding: 40px; border-radius: 8px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                    .error { color: #e74c3c; }
                    .icon { font-size: 60px; margin-bottom: 20px; }
                    h1 { color: #2c3e50; margin-top: 0; }
                    p { color: #7f8c8d; line-height: 1.6; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">❌</div>
                    <h1 class="error">Invoice Not Found</h1>
                    <p>The invoice could not be found. Please contact support if you need assistance.</p>
                </div>
            </body>
            </html>
            """, 404
        
        # Update opened_date if not already set
        if not invoice['opened_date']:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            execute(
                "UPDATE invoices SET opened_date = ?, status = 'opened', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (current_time, invoice_id)
            )
            print(f"✓ Invoice {invoice['invoice_number']} marked as read by client")
        
        # Return success page
        invoice_num = invoice['invoice_number'] or 'Unknown'
        print(f"✓ Invoice {invoice_num} marked as read by client at {datetime.now()}")
        
        success_html = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Invoice Verification</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 50px auto; background: white; padding: 40px; border-radius: 8px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .success {{ color: #27ae60; }}
                .icon {{ font-size: 60px; margin-bottom: 20px; }}
                h1 {{ color: #2c3e50; margin-top: 0; }}
                p {{ color: #7f8c8d; line-height: 1.6; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #95a5a6; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">✓</div>
                <h1 class="success">Thank You!</h1>
                <p>We've recorded that you've received and reviewed invoice <strong>{invoice_num}</strong>.</p>
                <p>Your confirmation has been sent to our team.</p>
                <div class="footer">
                    <p>You can now close this page.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return success_html
        
    except Exception as e:
        print(f"Error verifying invoice: {e}")
        traceback.print_exc()
        return """
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Invoice Verification</title>
            <style>
                body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 50px auto; background: white; padding: 40px; border-radius: 8px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .error { color: #e74c3c; }
                .icon { font-size: 60px; margin-bottom: 20px; }
                h1 { color: #2c3e50; margin-top: 0; }
                p { color: #7f8c8d; line-height: 1.6; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">❌</div>
                <h1 class="error">Error Processing Request</h1>
                <p>There was an error processing your request. Please try again or contact support.</p>
            </div>
        </body>
        </html>
        """, 500


@app.get("/api/services") # Get all available services
def get_services():
    """Get all available services"""
    # Get active services for user_id = 1
    services = query_all("""
        SELECT id, code, description, details, category, rate 
        FROM services 
        WHERE user_id = 1 AND is_active = 1
        ORDER BY category, code
    """)
    return {"services": services}



# Create invoice with GST 9%
@app.post("/api/invoices/create")
def create_invoice():
    """Create a new invoice dynamically with GST 9%"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['client_id', 'client_name', 'email', 'items'] # 'items' is a list of services with quantity
    for field in required_fields: # Check for presence of required fields in the request data
        if field not in data:
            return {"success": False, "error": f"Missing field: {field}"}, 400 # Return error if any required field is missing
    
    # Calculate totals
    subtotal = 0
    invoice_items = []
    
    for item in data['items']: # Iterate over each item in the invoice
        if 'service_id' not in item or 'quantity' not in item: # Validate item fields
            return {"success": False, "error": "Invalid item data"}, 400 # Ensure each item has service_id and quantity
        
        # Get service details from database
        service = query_one("""
            SELECT code, description, details, category, rate 
            FROM services WHERE id = ? AND user_id = 1
        """, (item['service_id'],))
        
        # Validate service exists
        if not service:
            return {"success": False, "error": f"Service not found: {item['service_id']}"}, 400
        
        # Calculate total for this item
        quantity = int(item['quantity'])  # Get quantity
        rate = float(service['rate'])     # Get rate
        total = rate * quantity           # Multiply rate × quantity
        subtotal += total
        
        # Prepare invoice item entry for database insertion
        invoice_items.append({
            'service_id': item['service_id'],
            'service_code': service['code'],
            'description': service['description'],
            'details': service['details'], # Store details
            'category': service['category'], # Store category
            'quantity': quantity,        # Store quantity
            'rate': rate,
            'total': total               # Store calculated total
        })
    
    # Calculate tax and total with GST 9%
    gst_rate = 0.09  # 9% GST
    tax = subtotal * gst_rate
    total_amount = subtotal + tax
    
    # Generate invoice number (Format: INV-YYYY-XXX)
    last_invoice = query_one("""
        SELECT invoice_number FROM invoices 
        WHERE user_id = 1 
        ORDER BY id DESC LIMIT 1
    """)
    
    if last_invoice: # If there is a previous invoice, increment the sequence number
        last_num = int(last_invoice['invoice_number'].split('-')[-1])
        new_seq = last_num + 1
    else:
        new_seq = 1 # Start from 1 if no previous invoices
    
    invoice_number = f"INV-{datetime.now().year}-{new_seq:03d}" # Format invoice number with leading zeros
    
    # Create invoice record in database
    with get_conn() as conn:
        cursor = conn.cursor()
        
        # Insert invoice record into invoices table
        cursor.execute("""
            INSERT INTO invoices 
            (user_id, invoice_number, client_id, client_name, email, 
             sent_date, status, failed_reason, subtotal, tax, total, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            1, invoice_number, data['client_id'], data['client_name'], 
            data['email'], datetime.now().strftime('%Y-%m-%d'),  # Set sent_date to today
            'pending', None, subtotal, tax, total_amount, 
            data.get('notes', '')
        ))
        
        invoice_id = cursor.lastrowid # Get the ID of the newly created invoice
        
        # Insert invoice items into invoice_items table
        for item in invoice_items:
            cursor.execute("""
                INSERT INTO invoice_items 
                (invoice_id, service_id, service_code, description, details, category, quantity, rate, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                invoice_id, item['service_id'], item['service_code'],
                item['description'], item['details'], item['category'],
                item['quantity'], item['rate'], item['total']
            ))
        
        conn.commit() # Commit transaction to save changes
    
    return { # Return success response with invoice details
        "success": True,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "message": "Invoice created successfully"
    }

# ============================================================================
# Debug endpoint to see what data is being returned for an invoice
@app.get("/debug/invoice-response/<int:invoice_id>")
def debug_invoice_response(invoice_id):
    """Debug endpoint to see what data is being returned"""
    invoice = query_one("""
        SELECT i.*, c.phone, c.address, c.city, c.state, c.postal_code, c.country
        FROM invoices i
        LEFT JOIN clients c ON i.client_id = c.id
        WHERE i.id = ? AND i.user_id = ?
    """, (invoice_id, 1))
    
    if invoice is None:
        return {"error": "Invoice not found"}
    
    # Return raw invoice data along with flags for failed reason and status
    return {
        "invoice_data": dict(invoice),
        "has_failed_reason": 'failed_reason' in invoice,
        "failed_reason_value": invoice['failed_reason'] if 'failed_reason' in invoice else None,
        "status": invoice['status'] if 'status' in invoice else None
    }

# ============================================================================
# CLIENT VALIDATION FUNCTION
# Purpose: Validate client fields for creation and editing
def validate_client_fields(client_name: str, email: str, phone: str, address: str):
    errors = []

    # Trim whitespace from inputs and handle None values
    client_name = (client_name or "").strip()
    email = (email or "").strip()
    phone = (phone or "").strip()
    address = (address or "").strip()

    # Validate client name
    if not client_name:
        errors.append("Client name is required.")
    elif len(client_name) > 80:
        errors.append("Client name must be 80 characters or less.")

    # Validate email if provided
    if email:
        if len(email) > 120:
            errors.append("Email must be 120 characters or less.")
        elif not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")

    # Validate phone if provided
    if phone:
        valid_phone, normalized_phone, phone_error = validate_phone_number(phone_value=phone)
        if not valid_phone:
            errors.append(phone_error)
        else:
            phone = normalized_phone

    # Validate address if provided
    if address and len(address) > 200:
        errors.append("Address must be 200 characters or less.")

    return errors, client_name, email, phone, address

# ============================================================================
# INVOICE APPROVALS ROUTES
# ============================================================================
# Purpose: Handle invoice approval workflow for managers/administrators
# Features:
#   - View all invoices pending approval
#   - Filter by approval status (pending, approved, rejected, on-hold)
#   - Approve/reject invoices with reasons
#   - Put invoices on hold
#   - Re-edit rejected invoices inline
#   - Resubmit edited invoices for approval
# ============================================================================

# Render the invoice approvals dashboard page
@app.get("/approvals")
def approvals():
    """
    Render the invoice approvals dashboard page.
    Shows all invoices requiring approval action.
    
    Returns:
        HTML template with empty shell (data loaded via AJAX)
    """
    
    # Render approvals.html template
    return render_template("approvals.html", title="Invoice Approvals")

@app.get("/api/approvals") # Fetch all invoices with approval status
def get_approvals():
    """
    API endpoint to fetch all invoices with approval status.
    Used by the approvals dashboard to display invoice list.
    
    Returns:
        JSON: {
            'success': True/False,
            'invoices': [array of invoice objects with approval metadata]
        }
    
    Invoice objects include:
        - id, invoice_number, client_name
        - submitted_by (employee name)
        - submitted_date, due_date
        - amount (formatted currency)
        - approval_status (pending/approved/rejected/on-hold)
        - approval_date, approval_reason, notes
    """
    try:
        # Query invoices with client details - using sent_date as submitted date
        # Sort by status priority (pending first) then by date
        query = """
            SELECT 
                i.id,
                i.invoice_number,
                i.total,
                i.subtotal,
                i.tax,
                i.sent_date as submitted_date,
                i.opened_date as due_date,
                CASE
                    WHEN i.sent_date IS NULL OR TRIM(i.sent_date) = '' THEN 'Net 30'
                    WHEN i.opened_date IS NULL OR TRIM(i.opened_date) = '' THEN 'Net 30'
                    WHEN CAST(ROUND(julianday(date(i.opened_date)) - julianday(date(i.sent_date))) AS INTEGER) <= 0 THEN 'Due on Receipt'
                    WHEN CAST(ROUND(julianday(date(i.opened_date)) - julianday(date(i.sent_date))) AS INTEGER) = 15 THEN 'Net 15'
                    WHEN CAST(ROUND(julianday(date(i.opened_date)) - julianday(date(i.sent_date))) AS INTEGER) = 30 THEN 'Net 30'
                    WHEN CAST(ROUND(julianday(date(i.opened_date)) - julianday(date(i.sent_date))) AS INTEGER) = 45 THEN 'Net 45'
                    ELSE 'Net 30'
                END as payment_terms,
                i.approval_status,
                i.approval_date,
                i.approval_reason,
                i.approved_by,
                i.notes,
                i.client_name,
                i.email,
                c.phone,
                c.address
            FROM invoices i
            LEFT JOIN clients c ON i.client_id = c.id
            WHERE i.user_id = ? AND i.email != 'queksiqi@gmail.com'
            ORDER BY 
                CASE i.approval_status
                    WHEN 'pending' THEN 1
                    WHEN 'on-hold' THEN 2
                    WHEN 'approved' THEN 3
                    WHEN 'rejected' THEN 4
                END,
                i.created_at DESC
        """
        
        invoices = query_all(query, (1,))  # Fetch for current user
        
        # Format invoice data for frontend consumption
        formatted_invoices = []
        for inv in invoices:
            # Fetch line items for this invoice
            items = query_all("""
                SELECT description, quantity, rate, total
                FROM invoice_items
                WHERE invoice_id = ?
            """, (inv['id'],))
            # Calculate due date (30 days from sent date)
            from datetime import datetime, timedelta
            formatted_submitted_date = None
            due_date = None
            
            try:
                # Handle both date and datetime formats
                date_str = inv['submitted_date']
                if date_str:
                    # Extract just the date part if it's a datetime string
                    date_part = date_str.split()[0] if ' ' in date_str else date_str
                    sent_date = datetime.strptime(date_part, '%Y-%m-%d')
                    # Keep dates in ISO format (YYYY-MM-DD) for consistent frontend formatting
                    formatted_submitted_date = sent_date.strftime('%Y-%m-%d')
                
                # Use the stored due_date if available, otherwise calculate it
                due_date_value = inv['due_date']
                if due_date_value and isinstance(due_date_value, str) and due_date_value.strip():
                    due_date_part = due_date_value.split()[0] if ' ' in due_date_value else due_date_value
                    due_date = datetime.strptime(due_date_part, '%Y-%m-%d').strftime('%Y-%m-%d')
                else:
                    # Fallback: calculate 30 days from submitted date
                    if inv['submitted_date']:
                        date_part = inv['submitted_date'].split()[0] if ' ' in inv['submitted_date'] else inv['submitted_date']
                        sent_date = datetime.strptime(date_part, '%Y-%m-%d')
                        due_date = (sent_date + timedelta(days=30)).strftime('%Y-%m-%d')
            except Exception as e:
                print(f"Error calculating due date for invoice {inv['id']}: {e}, submitted_date: {inv['submitted_date']}, due_date: {inv['due_date']}")
                due_date = None
            
            formatted_invoices.append({ # Build formatted invoice object for each invoice
                'id': inv['id'],
                'invoice_number': inv['invoice_number'] or f"INV-{inv['id']:05d}",
                'client_name': inv['client_name'],
                'email': inv['email'] or 'No email provided',
                'phone': inv['phone'] or 'No phone provided',
                'address': inv['address'] or 'No address provided',
                'submitted_by': 'Admin User',  # No employee table, use default
                'submitted_date': formatted_submitted_date,
                'due_date': due_date,
                'payment_terms': inv['payment_terms'] or 'Net 30',
                'amount': f"${float(inv['total'] or 0):,.2f}",
                'subtotal': float(inv['subtotal'] or 0),
                'tax': float(inv['tax'] or 0),
                'total': float(inv['total'] or 0),
                'approval_status': inv['approval_status'] or 'pending',
                'approval_date': inv['approval_date'],
                'approval_reason': inv['approval_reason'],
                'notes': inv['notes'] or 'No service details available',
                'items': [dict(item) for item in items]
            })
        
        return jsonify({ # Return success response with formatted invoices array
            'success': True,
            'invoices': formatted_invoices
        })
        
    except Exception as e: # Catch-all for unexpected errors
        print(f"Error fetching approvals: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to fetch approvals: {str(e)}'
        }), 500 # Internal Server Error on failure


# ============================================================================
# Handle approval actions: approve, reject, hold, acknowledge, resend
@app.post("/api/approvals/action") # Perform approval actions on invoices
def approval_action():
    """
    Handle approval actions: approve, reject, hold, acknowledge, resend
    Commercial-ready with proper validation and audit trail
    """
    try: # Parse JSON request data for invoice ID, action, and reason
        data = request.get_json()
        invoice_id = data.get('invoice_id')
        action = data.get('action')
        reason = data.get('reason')
        
        # Validate input fields are present
        if not invoice_id or not action:
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400 # Bad Request on missing fields

        if not is_current_user_admin() and action not in ('acknowledge', 'resend'):
            return jsonify({
                'success': False,
                'error': 'Employees can only acknowledge rejected invoices or resend on-hold invoices.'
            }), 403
        
        # Verify invoice exists and belongs to current user
        invoice = query_one(
            "SELECT * FROM invoices WHERE id = ? AND user_id = ?",
            (invoice_id, 1) # Current user only
        )
        
        if not invoice: # Invoice not found or doesn't belong to user
            return jsonify({
                'success': False,
                'error': 'Invoice not found'
            }), 404 # Not Found on missing invoice

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Current timestamp for approval_date field
        
        # Handle different actions
        if action == 'approve': # Approve the invoice
            execute( # Update invoice record to approved status
                """UPDATE invoices 
                   SET approval_status = 'approved',
                       status = 'pending',
                       approval_date = ?,
                       approved_by = ?,
                       approval_reason = NULL
                   WHERE id = ?""", 
                (current_time, 1, invoice_id) # Assuming user ID 1 is the approver
            )
            message = 'Invoice approved successfully'
            
        # Reject the invoice with reason
        elif action == 'reject': # Reject the invoice
            execute(
                """UPDATE invoices 
                   SET approval_status = 'rejected',
                       approval_date = ?,
                       approved_by = ?,
                       approval_reason = ?
                   WHERE id = ?""", # Update invoice record to rejected status with reason
                (current_time, 1, reason or 'No reason provided', invoice_id) # Assuming user ID 1 is the rejector
            )
            message = 'Invoice rejected'
            
        elif action == 'hold': # Put the invoice on hold with reason
            execute(
                """UPDATE invoices 
                   SET approval_status = 'on-hold',
                       approval_date = ?,
                       approved_by = ?,
                       approval_reason = ?
                   WHERE id = ?""",
                (current_time, 1, reason or 'On hold', invoice_id)
            )
            message = 'Invoice put on hold'
            
        elif action == 'acknowledge': # Acknowledge the invoice and place on hold
            # Mark as acknowledged and place on hold
            execute(
                """UPDATE invoices 
                   SET approval_status = 'on-hold',
                       approval_date = ?,
                       approved_by = ?,
                       approval_reason = 'Acknowledged - awaiting resolution'
                   WHERE id = ?""",
                (current_time, 1, invoice_id)
            )
            message = 'Invoice acknowledged and placed on hold'
            
        elif action == 'resend': # Resend the invoice for approval after edits
            # Change status back to pending for resubmission
            execute(
                """UPDATE invoices 
                   SET approval_status = 'pending',
                       approval_date = NULL,
                       approved_by = NULL,
                       approval_reason = NULL
                   WHERE id = ?""",
                (invoice_id,)
            )
            message = 'Invoice resubmitted for approval'
            
        else: # Invalid action provided
            return jsonify({
                'success': False,
                'error': 'Invalid action'
            }), 400 # Bad Request on invalid action
        
        return jsonify({ # Return success response with action message
            'success': True,
            'message': message
        })
        
    except Exception as e: # Catch-all for unexpected errors
        print(f"Error performing approval action: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to perform action'
        }), 500 # Internal Server Error on failure

# Edit Invoice Routes
@app.route("/invoices/edit/<int:invoice_id>") # Render invoice edit page
def edit_invoice(invoice_id):
    """Render invoice edit page"""
    try:
        # Fetch invoice details for editing
        invoice_data = query_one("""
            SELECT 
                i.id,
                i.invoice_number,
                i.client_name,
                i.email,
                c.phone,
                i.notes,
                i.subtotal,
                i.tax,
                i.total,
                i.sent_date as invoice_date,
                i.approval_reason,
                'Net 30' as payment_terms
            FROM invoices i
            LEFT JOIN clients c ON i.client_id = c.id
            WHERE i.id = ?
        """, (invoice_id,))
        
        if not invoice_data: # Invoice not found
            flash("Invoice not found", "error") # Flash error message to user
            return redirect(url_for("approvals")) # Redirect to approvals page
        
        # Convert sqlite3.Row to dict to allow item assignment
        invoice_dict = {
            'id': invoice_data['id'],
            'invoice_number': normalize_invoice_number(invoice_data['invoice_number'], invoice_data['id']),
            'client_name': invoice_data['client_name'],
            'email': invoice_data['email'],
            'phone': invoice_data['phone'],
            'notes': invoice_data['notes'],
            'subtotal': invoice_data['subtotal'],
            'tax': invoice_data['tax'],
            'total': invoice_data['total'],
            'invoice_date': invoice_data['invoice_date'],
            'approval_reason': invoice_data['approval_reason'],
            'payment_terms': invoice_data['payment_terms']
        }
        invoice_data = invoice_dict
    
        line_items = [ # Fallback single item if no detailed items exist
            {
                'description': invoice_data['notes'] or 'Service',
                'quantity': 1,
                'rate': float(invoice_data['subtotal']),
                'amount': float(invoice_data['subtotal'])
            }
        ]
        
        invoice_data['line_items'] = line_items # Attach items to invoice data for rendering
        
        # Format dates for display (editable date fields)
        if invoice_data['invoice_date']:
            invoice_data['invoice_date'] = invoice_data['invoice_date'].split(' ')[0] # Keep only date part (YYYY-MM-DD)
        
        # Calculate due_date (30 days from invoice_date)
        from datetime import datetime, timedelta
        try:
            inv_date = datetime.strptime(invoice_data['invoice_date'], '%Y-%m-%d')
            invoice_data['due_date'] = (inv_date + timedelta(days=30)).strftime('%Y-%m-%d')
        except:
            invoice_data['due_date'] = None
        
        # Extract rejection title, description, and category
        rejection_title = '' # Default empty title and description
        rejection_description = ''
        rejection_category = 'non-editable'  # Default to non-editable
        if invoice_data['approval_reason']: # If there is an approval reason, parse it
            reason = invoice_data['approval_reason']
            
            # Extract category if present (format: "reason | category")
            if ' | ' in reason:
                reason_text, category = reason.rsplit(' | ', 1)
                rejection_category = category.strip()
                reason = reason_text.strip()
            
            # Extract title and display text from reason
            if ':' in reason: # Split by colon for title and description
                rejection_title, rejection_description = reason.split(':', 1)
                rejection_description = rejection_description.strip() # Trim whitespace
            elif '.' in reason: # Split by first period for title and description
                parts = reason.split('.', 1)
                rejection_title = parts[0]
                rejection_description = parts[1].strip() if len(parts) > 1 else '' # Trim whitespace
            else:
                rejection_title = 'Rejection Notice' # Default title if no delimiter found
                rejection_description = reason # Use entire reason as description
            
            # Clean up the title/description to remove category tags
            rejection_title = rejection_title.replace('[EDITABLE]', '').replace('[NOT_EDITABLE]', '').strip()
            rejection_description = rejection_description.replace('[EDITABLE]', '').replace('[NOT_EDITABLE]', '').strip()
        
        return render_template( # Render edit_invoice.html template with invoice data
            "edit_invoice.html",
            invoice=invoice_data,
            rejection_title=rejection_title,
            rejection_description=rejection_description
        )
        
    except Exception as e: # Catch-all for unexpected errors
        print(f"Error loading invoice for edit: {e}")
        flash("Failed to load invoice", "error") # Flash error message to user
        return redirect(url_for("approvals")) # Redirect to approvals page

@app.route("/api/invoices/<int:invoice_id>/edit-data") # Get invoice data for editing (returns JSON)
def get_invoice_edit_data(invoice_id):
    """Get invoice data for editing (returns JSON for inline editing)"""
    try: # Fetch invoice details for editing
        invoice_data = query_one("""
            SELECT 
                i.id,
                i.invoice_number,
                i.client_name,
                i.email,
                c.phone,
                i.notes,
                i.subtotal,
                i.tax,
                i.total,
                i.sent_date as invoice_date,
                i.approval_status,
                i.approval_reason,
                'Net 30' as payment_terms
            FROM invoices i
            LEFT JOIN clients c ON i.client_id = c.id
            WHERE i.id = ?
        """, (invoice_id,))
        
        if not invoice_data: # Invoice not found
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404
        
        # Convert Row object to dict if needed
        invoice_dict = dict(invoice_data) if invoice_data else {}
        invoice_dict['invoice_number'] = normalize_invoice_number(invoice_dict.get('invoice_number'), invoice_id)
        
        # Format dates
        if invoice_dict.get('invoice_date'): # Format invoice date
            invoice_dict['invoice_date'] = str(invoice_dict['invoice_date']).split(' ')[0] # Keep only date part
        
        # Calculate due_date (30 days from invoice_date)
        from datetime import datetime, timedelta
        try:
            inv_date = datetime.strptime(invoice_dict['invoice_date'], '%Y-%m-%d')
            invoice_dict['due_date'] = (inv_date + timedelta(days=30)).strftime('%Y-%m-%d')
        except:
            invoice_dict['due_date'] = None
        
        # Fetch actual line items from invoice_items table
        line_items = query_all("""
            SELECT description, quantity, rate, total as amount
            FROM invoice_items
            WHERE invoice_id = ?
            ORDER BY id
        """, (invoice_id,))
        
        items = [] # Prepare items list for response
        if line_items: # If detailed line items exist, use them
            for item in line_items: # Process each line item
                items.append({ # Build item dict for response
                    'description': item['description'], # Use 'description' field from query
                    'quantity': int(item['quantity']), # Use 'quantity' field from query
                    'rate': float(item['rate']), # Use 'rate' field from query
                    'amount': float(item['amount']) # Use 'amount' field from query
                })
        else:
            # Fallback if no items found
            items = [{ # Single item fallback
                'description': invoice_dict.get('notes') or 'Service', # Use notes or default
                'quantity': 1, # Default quantity of 1
                'rate': float(invoice_dict.get('subtotal', 0)), # Use subtotal as rate
                'amount': float(invoice_dict.get('subtotal', 0)) # Use subtotal as amount
            }]
        
        # Extract rejection title, description, and category
        rejection_title = '' # Default empty title and description
        rejection_description = ''
        rejection_category = 'non-editable'  # Default to non-editable
        if invoice_dict.get('approval_reason'):
            reason = invoice_dict['approval_reason']
            
            # Extract category if present (format: "reason | category")
            if ' | ' in reason:
                reason_text, category = reason.rsplit(' | ', 1)
                rejection_category = category.strip()
                reason = reason_text.strip()
            
            # Extract title and display text from reason
            if ':' in reason: # Split by colon for title and description
                rejection_title, rejection_description = reason.split(':', 1) 
                rejection_description = rejection_description.strip() # Trim whitespace
            elif '.' in reason: # Split by first period for title and description
                parts = reason.split('.', 1)
                rejection_title = parts[0] # First part as title
                rejection_description = parts[1].strip() if len(parts) > 1 else '' # Trim whitespace
            else:
                rejection_title = 'Rejection Notice'
                rejection_description = reason
            
            # Clean up tags
            rejection_title = rejection_title.replace('[EDITABLE]', '').replace('[NOT_EDITABLE]', '').strip()
            rejection_description = rejection_description.replace('[EDITABLE]', '').replace('[NOT_EDITABLE]', '').strip()
        
        return jsonify({ # Return success response with invoice data and items for editing
            'success': True,
            'invoice': invoice_dict, # Invoice details as dict
            'items': items, # Line items array for editing
            'rejection_title': rejection_title, # Trimmed title
            'rejection_description': rejection_description, # Trimmed description
            'rejection_category': rejection_category # Category for smart button display
        })
        
    except Exception as e: # Catch-all for unexpected errors
        import traceback # Import traceback for detailed error logging
        print(f"Error getting invoice edit data: {e}")
        print(traceback.format_exc()) # Print full traceback for debugging
        return jsonify({'success': False, 'error': str(e)}), 500 # Internal Server Error on failure
        
# ============================================================================
# POST route to resubmit edited invoice for approval
@app.route("/api/invoices/<int:invoice_id>/resubmit", methods=["POST"])
def resubmit_invoice(invoice_id):
    """Resubmit edited invoice for approval"""
    try: # Parse JSON request data
        data = request.json
        
        # Add debug logging
        print(f"Received resubmit data: {data}")
        
        # Validate phone number (if provided)
        phone = (data.get('phone') or '').strip()
        phone_country = (data.get('phone_country') or '').strip()
        phone_number = (data.get('phone_number') or '').strip()

        if phone or phone_country or phone_number:
            is_valid_phone, normalized_phone, phone_error = validate_phone_number(
                country_value=phone_country,
                phone_number_value=phone_number,
                phone_value=phone,
            )
            if not is_valid_phone:
                return jsonify({
                    'success': False,
                    'error': phone_error
                }), 400
            phone = normalized_phone
        
        # =========================================================================
        # Validate dates
        from datetime import datetime, timedelta
        
        try:
            invoice_date = datetime.strptime(data['invoice_date'], '%Y-%m-%d') # Parse invoice date from string
            due_date = datetime.strptime(data['due_date'], '%Y-%m-%d') # Parse due date from string
            print(f"Parsed dates - Invoice: {invoice_date}, Due: {due_date}")
        except ValueError as e: # Handle invalid date format
            print(f"Date parsing error: {e}")
            return jsonify({ # Return error if date format is invalid
                'success': False,
                'error': f'Invalid date format. Please use YYYY-MM-DD format. Error: {str(e)}'
            }), 400 # Bad Request status code on validation failure
        
        invoice_date_only = invoice_date.date()
        due_date_only = due_date.date()
        
        # Check if due date is not before invoice date
        if due_date_only < invoice_date_only: # Due date must be after or on invoice date
            return jsonify({
                'success': False,
                'error': 'Due date cannot be earlier than invoice date'
            }), 400
        
        # Check if due date is not too far in the future (more than 1 year from invoice date)
        if due_date_only > (invoice_date_only + timedelta(days=365)):
            print(f"Due date validation failed: {due_date_only} > {invoice_date_only + timedelta(days=365)}")
            return jsonify({
                'success': False,
                'error': 'Due date cannot be more than 1 year after invoice date'
            }), 400
        
        # Calculate totals from items in the request data
        subtotal = sum(item['amount'] for item in data.get('items', [])) # Sum of all item amounts for subtotal
        tax = subtotal * 0.09  # 9% GST
        total = subtotal + tax
        
        # Use the notes from the form data
        notes = data.get('notes', '') # Get notes or default to empty string

        # Get the client_id from the invoice to update client's phone
        invoice_info = query_one("SELECT client_id FROM invoices WHERE id = ?", (invoice_id,))
        
        # Update client's phone number if provided and client exists
        if phone and invoice_info and invoice_info['client_id']:
            execute("""
                UPDATE clients
                SET phone = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (phone, invoice_info['client_id']))

        # Update invoice record in the database (including sent_date for submitted date)
        # Convert invoice_date to proper format with timestamp for database storage
        sent_date_with_time = f"{data['invoice_date']} 08:00:00"
        due_date_with_time = f"{data['due_date']} 08:00:00"
        execute("""
            UPDATE invoices
            SET 
                client_name = ?,
                email = ?,
                notes = ?,
                subtotal = ?,
                tax = ?,
                total = ?,
                sent_date = ?,
                opened_date = ?,
                approval_status = 'pending',
                approval_reason = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            data['company_name'],
            data['email'],
            notes,
            subtotal,
            tax,
            total,
            sent_date_with_time,
            due_date_with_time,
            invoice_id
        ))
        
        # Clear existing line items for the invoice before inserting updated ones
        execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
        
        # Insert updated line items into invoice_items table (add items)
        for item in data.get('items', []):
            execute("""
                INSERT INTO invoice_items 
                (invoice_id, service_id, service_code, description, details, category, quantity, rate, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                invoice_id,
                None,  # service_id
                '',    # service_code
                item['description'],
                '',    # details
                'Service',  # category
                item['quantity'],
                item['rate'],
                item['amount']
            ))
        
        # Return success response for resubmission of invoice for approval
        return jsonify({
            'success': True,
            'message': 'Invoice resubmitted successfully'
        })
    
    except Exception as e:
        print(f"Error resubmitting invoice: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to resubmit invoice'
        }), 500


# =========================================================================
# AI-POWERED FEATURES
# =========================================================================

@app.route("/api/ai/validate-invoice", methods=["POST"])
def ai_validate_invoice():
    """AI-powered invoice validation - provides feedback on potential issues"""
    print(f"\n{'='*60}")
    print(f"[AI-VALIDATE] Starting invoice validation")
    
    if not openai_client:
        print(f"[AI-VALIDATE] [ERROR] Client not configured")
        return jsonify({
            'success': False,
            'error': 'AI features are not enabled. Please configure GEMINI_API_KEY.'
        }), 503
    
    print(f"[AI-VALIDATE] ✓ Client configured")
    
    try:
        data = request.json
        print(f"[AI-VALIDATE] Received invoice data: {json.dumps(data, default=str)[:200]}...")
        
        # Build invoice summary for AI analysis
        invoice_summary = {
            'company_name': data.get('company_name', ''),
            'email': data.get('email', ''),
            'phone': data.get('phone', ''),
            'invoice_number': data.get('invoice_number', ''),
            'invoice_date': data.get('invoice_date', ''),
            'due_date': data.get('due_date', ''),
            'payment_terms': data.get('payment_terms', ''),
            'items': data.get('items', []),
            'notes': data.get('notes', '')
        }
        
        # Calculate subtotal - handle both direct amounts and quantity*rate calculations
        subtotal = 0
        for item in invoice_summary['items']:
            if 'amount' in item and item['amount']:
                subtotal += item['amount']
            else:
                # Calculate from quantity * rate if amount not provided
                qty = item.get('quantity', 0)
                rate = item.get('rate', 0)
                subtotal += (qty * rate)
        tax = subtotal * 0.09
        total = subtotal + tax
        
        invoice_summary['subtotal'] = subtotal
        invoice_summary['tax'] = tax
        invoice_summary['total'] = total
        
        print(f"[AI-VALIDATE] Invoice summary built: company={invoice_summary['company_name']}, items={len(invoice_summary['items'])}, total=${total:.2f}")
        
        # Rule-based checks to ensure deterministic detection of obvious issues
        rule_issues = []
        rule_suggestions = []
        phone_invalid = False
        email = (invoice_summary.get('email') or '').strip()
        if not email:
            rule_issues.append({'message': 'Missing email address', 'severity': 'high'})
        else:
            if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
                rule_issues.append({'message': f"Invalid email format: {email}", 'severity': 'high'})

            # Suggest dotted domain variants based on email patterns (dynamic)
            try:
                local_part, domain = email.split('@', 1)
                domain = domain.lower()
                base, tld = domain.rsplit('.', 1)

                # Handle collapsed country TLDs like .comsg -> .com.sg
                if tld in ('comsg', 'edusg', 'govsg', 'orgsg', 'netsg'):
                    tld_parts = [tld[:3], tld[3:]]
                    suggested_domain = f"{base}.{'.'.join(tld_parts)}"
                    suggestion = (
                        f"Confirm email domain: {email} "
                        f"(possible variant: {local_part}@{suggested_domain})"
                    )
                    if suggestion not in rule_suggestions:
                        rule_suggestions.append(suggestion)

                def add_domain_suggestion(suggested_base):
                    suggested_domain = f"{suggested_base}.{tld}"
                    suggestion = (
                        f"Confirm email domain: {email} "
                        f"(possible variant: {local_part}@{suggested_domain})"
                    )
                    if suggestion not in rule_suggestions:
                        rule_suggestions.append(suggestion)

                common_tokens = [
                    'pte', 'ltd', 'co', 'sg', 'edu', 'ac', 'gov', 'org', 'com', 'net',
                    'nyp', 'ite', 'poly', 'uni', 'college', 'mail', 'my', 'biz', 'tech',
                    'lab', 'group', 'holdings', 'intl', 'int', 'llc', 'inc', 'plc', 'lol'
                ]
                anchor_tokens = {
                    'pte', 'ltd', 'edu', 'ac', 'gov', 'org', 'com', 'net', 'sg'
                }

                for left in common_tokens:
                    for right in common_tokens:
                        if left not in anchor_tokens and right not in anchor_tokens:
                            continue
                        suffix = left + right
                        if base.endswith(suffix) and '.' not in base:
                            prefix = base[:-len(suffix)]
                            if prefix:
                                suggested_base = f"{prefix}.{left}.{right}"
                            else:
                                suggested_base = f"{left}.{right}"
                            add_domain_suggestion(suggested_base)
            except Exception:
                pass

        if not (invoice_summary.get('company_name') or '').strip():
            rule_issues.append({'message': 'Missing company name', 'severity': 'high'})
            rule_suggestions.append('Add a company name for the client before submitting.')
        else:
            company_name = (invoice_summary.get('company_name') or '').strip()
            company_compact = re.sub(r"\s+", "", company_name)
            company_lower = company_compact.lower()
            vowels = sum(1 for ch in company_lower if ch in 'aeiou')
            vowel_ratio = vowels / max(len(company_compact), 1)
            has_long_consonant_run = re.search(r"[^aeiou\W]{4,}", company_lower) is not None
            no_spaces = ' ' not in company_name
            legal_suffixes = ['pte', 'ltd', 'inc', 'llc', 'co', 'corp', 'company', 'group', 'holdings']
            has_legal_suffix = any(suffix in company_lower for suffix in legal_suffixes)
            long_single_token = no_spaces and len(company_compact) >= 16 and not has_legal_suffix
            has_suspicious_tail = re.search(r"[a-z]{4,}$", company_lower) is not None
            if (len(company_compact) >= 6 and no_spaces and (vowel_ratio < 0.25 or has_long_consonant_run)) or (long_single_token and has_suspicious_tail):
                rule_issues.append({'message': 'Company name looks invalid or placeholder', 'severity': 'medium'})
                rule_suggestions.append('Use the full legal company name (e.g., "Assembly Line Pte Ltd").')

        phone = (invoice_summary.get('phone') or '').strip()
        phone_country = (data.get('phone_country') or '').strip()
        phone_number = (data.get('phone_number') or '').strip()
        if phone or phone_country or phone_number:
            is_valid_phone, normalized_phone, phone_error = validate_phone_number(
                country_value=phone_country,
                phone_number_value=phone_number,
                phone_value=phone,
            )
            if not is_valid_phone:
                phone_invalid = True
                rule_issues.append({'message': phone_error, 'severity': 'medium'})
                rule_suggestions.append('Use digits only and match the selected country number length.')
            else:
                invoice_summary['phone'] = normalized_phone

        invoice_number = normalize_invoice_number(invoice_summary.get('invoice_number'))
        invoice_summary['invoice_number'] = invoice_number

        if not invoice_summary.get('items'):
            rule_issues.append({'message': 'Missing line items', 'severity': 'high'})
        else:
            normalized_descriptions = []
            for item in invoice_summary['items']:
                desc = (item.get('description') or '').strip()
                if not desc:
                    rule_issues.append({'message': 'Empty line item description', 'severity': 'medium'})
                    break
                normalized_descriptions.append(re.sub(r'\s+', ' ', desc).strip().lower())

            seen_descriptions = set()
            duplicate_descriptions = set()
            for normalized_desc in normalized_descriptions:
                if normalized_desc in seen_descriptions:
                    duplicate_descriptions.add(normalized_desc)
                else:
                    seen_descriptions.add(normalized_desc)

            if duplicate_descriptions:
                duplicate_labels = sorted({d.title() for d in duplicate_descriptions})
                rule_issues.append({
                    'message': f"Duplicate line item descriptions: {', '.join(duplicate_labels)}",
                    'severity': 'high'
                })
                rule_suggestions.append('Remove or merge duplicate line item descriptions to avoid repeated billing.')

        inv_date = invoice_summary.get('invoice_date')
        due_date = invoice_summary.get('due_date')
        parsed_inv_dt = parse_invoice_date(inv_date)
        parsed_due_dt = parse_invoice_date(due_date)
        if parsed_inv_dt and parsed_due_dt:
            if parsed_due_dt < parsed_inv_dt:
                rule_issues.append({'message': 'Due date is before invoice date', 'severity': 'high'})

            # Soft AI guidance only: future-dated invoices may be intentional
            if parsed_inv_dt > datetime.now() + timedelta(days=30):
                rule_suggestions.append('Invoice date is significantly in the future. Confirm the scheduling intent before submission.')

        invoice_date_display = format_date_ddmmyyyy(invoice_summary.get('invoice_date'))
        due_date_display = format_date_ddmmyyyy(invoice_summary.get('due_date'))

        # Call Groq API
        print(f"[AI-VALIDATE] Calling Groq API (llama-3.3-70b-versatile)...")
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": f"""You are an expert invoice auditor. Analyze this invoice for ACTUAL ISSUES ONLY.

IMPORTANT: Only report REAL, DETECTABLE issues. Do NOT report generic advice like "ensure both parties agree", "verify this is correct", "ensure the rate is appropriate", or "make sure this is accurate" - these are obvious general statements, not invoice issues. Focus ONLY on problems you can objectively identify from the invoice data.

Invoice Details:
- Company: {invoice_summary['company_name']}
- Email: {invoice_summary['email']}
- Phone: {invoice_summary['phone']}
- Invoice Number: {invoice_summary['invoice_number']}
- Invoice Date: {invoice_date_display} (dd/mm/yyyy)
- Due Date: {due_date_display} (dd/mm/yyyy)
- Payment Terms: {invoice_summary['payment_terms']}

Line Items:
{json.dumps(invoice_summary['items'], indent=2)}

IMPORTANT: Line item "amount" is ALWAYS auto-calculated as (quantity × rate). Never suggest changes to the amount field.
Invoice number is system-generated and not user-editable; do NOT flag missing or inconsistent invoice number.

Totals:
- Subtotal: ${subtotal:.2f}
- Tax (9% GST): ${tax:.2f}
- Total: ${total:.2f}

Notes: {invoice_summary['notes']}

Report ONLY actual issues you can detect:
1. MISSING DATA: Fields that are empty or blank
2. FORMATTING ERRORS: Invalid email format (missing @, etc.). For phone: only flag if clearly invalid (letters, too short/long). Valid phones include: +65 8843 3727, 88433727, +65-8843-3727.
3. SPELLING ERRORS: Actual typos in descriptions (misspelled words)
4. LOGIC ERRORS: Due date before invoice date, zero amounts when items exist
5. SUSPICIOUS VALUES: Unreasonable amounts (extremely high/low compared to item descriptions)
6. MISSING SECTION: Critical sections completely absent (like line items when there should be some)

Do NOT suggest combining or reorganizing line items - that is a business decision, not a data quality issue.
Do NOT report things like "ensure the phone matches the company directory" or "verify the email is correct" - you cannot verify these from the invoice alone.
Do NOT report phone numbers with spaces as formatting errors - spaces are acceptable (e.g., +65 8843 3727 is valid).
Do NOT flag future invoice dates or future due dates as errors if the date format is valid.
Do NOT report "logic errors" if calculations are correct. Only report math errors when the computed amount does NOT match the provided amount.
Do NOT repeat the same issue in different severities or wording.

Respond with valid JSON only (no markdown):
{{
    "status": "pass|warning|critical",
    "assessment": "assessment of actual detectable issues only",
    "issues": [
        {{"description": "specific detectable issue (e.g., 'Misspelled word in description: Consuling should be Consulting')", "severity": "high|medium|low"}},
        {{"description": "another actual issue", "severity": "high|medium|low"}}
    ],
    "suggestions": ["specific fix for issue 1", "specific fix for issue 2"]
}}"""}
            ],
            temperature=0.0,
            max_tokens=1000
        )
        
        print(f"[AI-VALIDATE] ✓ API response received")
        
        # Parse AI response - handle potential markdown wrapping
        response_text = response.choices[0].message.content
        print(f"[AI-VALIDATE] Response text (first 200 chars): {response_text[:200]}...")
        
        if '```json' in response_text:
            print(f"[AI-VALIDATE] Extracting JSON from markdown (```json format)")
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            print(f"[AI-VALIDATE] Extracting JSON from markdown (``` format)")
            response_text = response_text.split('```')[1].split('```')[0].strip()
        
        print(f"[AI-VALIDATE] Parsing JSON: {response_text[:150]}...")
        ai_result = json.loads(response_text)
        
        print(f"[AI-VALIDATE] ✓ Success! Result: status={ai_result.get('status')}")
        print(f"{'='*60}\n")
        
        # Transform AI result to include required fields
        status = ai_result.get('status', 'warning')
        issues = ai_result.get('issues', [])
        
        # Transform issues - use deterministic severity normalization
        transformed_issues = []
        for issue in issues:
            # Handle both old format (string) and new format (dict with description and severity)
            if isinstance(issue, dict):
                message = issue.get('description', str(issue))
                severity = issue.get('severity', 'medium').lower()
            else:
                message = str(issue)
                severity = 'medium'  # Default if not provided
            
            # Normalize severity based on message content for stability
            message_lower = message.lower()
            if any(token in message_lower for token in ['missing', 'invalid', 'before invoice date', 'no line items']):
                severity = 'high'
            elif any(token in message_lower for token in ['notes', 'unprofessional', 'placeholder', 'typo', 'spelling']):
                severity = 'low'
            elif severity not in ['high', 'medium', 'low']:
                severity = 'medium'
            
            transformed_issues.append({
                'message': message,
                'severity': severity
            })
        
        # Filter out low-value/generic AI issues and duplicates
        normalized_rule_messages = {normalize_issue_key(i.get('message', '')) for i in rule_issues}
        has_rule_empty_line_description = any(
            'empty line item description' in normalized_message
            for normalized_message in normalized_rule_messages
        )
        has_rule_duplicate_line_descriptions = any(
            'duplicate line item descriptions' in normalized_message
            for normalized_message in normalized_rule_messages
        )
        filtered_ai_issues = []
        for issue in transformed_issues:
            msg = issue.get('message', '').strip()
            msg_lower = msg.lower()
            msg_normalized = normalize_issue_key(msg)

            # Drop duplicate issues already caught by rules
            if msg_normalized in normalized_rule_messages:
                continue

            # Drop semantic duplicates of rule-based empty line-item descriptions.
            if has_rule_empty_line_description:
                has_description_tokens = 'description' in msg_lower and ('line item' in msg_lower or 'line items' in msg_lower)
                has_missing_or_empty_tokens = any(token in msg_lower for token in ['empty', 'blank', 'missing data', 'missing'])
                if has_description_tokens and has_missing_or_empty_tokens:
                    continue

                has_placeholder_line_item_context = 'line item' in msg_lower or 'line items' in msg_lower
                has_zero_amount_tokens = 'zero amount' in msg_lower or 'zero amounts' in msg_lower
                has_zero_rate_tokens = 'zero rate' in msg_lower or 'zero rates' in msg_lower
                has_zero_quantity_tokens = 'zero quantity' in msg_lower or 'zero quantities' in msg_lower
                has_placeholder_tokens = any(token in msg_lower for token in ['placeholder', 'unnecessary'])
                has_redundant_token = 'redundant' in msg_lower
                has_qty_one_token = 'quantities of 1' in msg_lower or 'quantity of 1' in msg_lower
                has_inconsistent_token = 'inconsistent' in msg_lower or 'inconsistency' in msg_lower
                has_zero_value_logic_pattern = (has_zero_amount_tokens or has_zero_rate_tokens) and has_qty_one_token
                if has_placeholder_line_item_context and (
                    (has_zero_value_logic_pattern and (has_placeholder_tokens or has_inconsistent_token))
                    or ((has_zero_quantity_tokens and has_zero_rate_tokens and has_zero_amount_tokens) and (has_placeholder_tokens or has_redundant_token or has_inconsistent_token))
                    or ((has_zero_amount_tokens or has_zero_rate_tokens or has_qty_one_token) and has_placeholder_tokens)
                ):
                    continue

            # Drop semantic duplicates of rule-based duplicate line-item descriptions.
            if has_rule_duplicate_line_descriptions:
                has_line_item_context = 'line item' in msg_lower or 'line items' in msg_lower
                has_duplicate_tokens = any(token in msg_lower for token in ['duplicate', 'duplicat', 'identical', 'same'])
                has_entry_tokens = any(token in msg_lower for token in ['entries', 'entry', 'descriptions', 'description'])
                if has_line_item_context and has_duplicate_tokens and has_entry_tokens:
                    continue

            # Drop duplicate invalid email issues if rule already flagged it
            if 'invalid email' in msg_lower and any('invalid email format' in r for r in normalized_rule_messages):
                continue

            # Drop duplicate company-name issues if rule already flagged it
            if 'company' in msg_lower:
                if any('missing company name' in r for r in normalized_rule_messages):
                    if 'empty' in msg_lower or 'missing' in msg_lower:
                        continue
                if any('company name looks invalid or placeholder' in r for r in normalized_rule_messages):
                    continue

            # Drop generic "verification" or "matches" statements
            if 'matches the provided amount' in msg_lower or 'essential to confirm' in msg_lower:
                continue

            # Drop non-actionable positive/generic statements from AI
            if (
                'is valid' in msg_lower
                or 'no other detectable issues' in msg_lower
                or 'no detectable issues' in msg_lower
                or 'no other issues' in msg_lower
                or msg_lower.startswith('there are no')
            ):
                continue

            # Drop phone-format heuristics from AI when rule already flagged it
            if phone_invalid and 'phone' in msg_lower and ('malformed' in msg_lower or 'format' in msg_lower):
                continue

            # Drop duplicate notes professionalism warnings
            if 'notes' in msg_lower and ('unprofessional' in msg_lower or 'nonsensical' in msg_lower):
                if any('notes appear unprofessional or too short' in r for r in normalized_rule_messages):
                    continue

            # Drop invoice-number vs date heuristics (not a reliable error)
            if 'invoice number suggests' in msg_lower or 'unusual date range' in msg_lower:
                continue

            # Drop due-date year mismatch heuristics
            if 'due date is in a different year' in msg_lower:
                continue

            # Drop invoice-number year mismatch heuristics
            if 'invoice number' in msg_lower and 'previous year' in msg_lower:
                continue

            # Do not flag invoice number issues (system-generated)
            if 'invoice number' in msg_lower and ('missing' in msg_lower or 'invalid' in msg_lower or 'mismatch' in msg_lower):
                continue

            # Drop contradictory due-date/payment-terms narratives
            if (
                'expected due date' in msg_lower or
                ('due date' in msg_lower and 'payment terms' in msg_lower and 'before' in msg_lower)
            ):
                continue

            # Drop due-date-before-invoice claims when parsed dates are actually valid
            if is_due_before_false_positive(msg, inv_date, due_date):
                continue

            # Drop generic advice phrases
            if msg_lower.startswith('verify ') or msg_lower.startswith('ensure '):
                continue

            # Future dates are allowed in this workflow
            if is_future_date_false_positive(msg_lower):
                continue

            filtered_ai_issues.append(issue)

        # Merge rule-based issues and dedupe by normalized message
        seen_messages = set()
        combined_issues = []
        for issue in rule_issues + filtered_ai_issues:
            msg = issue.get('message', '').strip()
            msg_key = normalize_issue_key(msg)
            if not msg or msg_key in seen_messages:
                continue
            seen_messages.add(msg_key)
            combined_issues.append(issue)

        # Stabilize ordering so priorities do not change between refreshes
        severity_rank = {'high': 0, 'medium': 1, 'low': 2}
        combined_issues.sort(key=lambda x: (severity_rank.get(x.get('severity', 'medium'), 1), x.get('message', '').lower()))

        # Derive status deterministically from final issue set to prevent score jitter.
        if combined_issues:
            if any(i.get('severity') == 'high' for i in combined_issues):
                status = 'critical'
            else:
                status = 'warning'
        else:
            status = 'pass'

        # Calculate score based on status and number of issues
        issue_count = len(combined_issues)
        if status == 'pass':
            score = 100 if issue_count == 0 else 95
        elif status == 'warning':
            score = max(70 - (issue_count * 5), 50)
        else:  # critical
            score = max(30 - (issue_count * 3), 20)

        # Merge AI suggestions with rule-based suggestions, de-duped
        combined_suggestions = []
        seen_suggestions = set()
        for suggestion in rule_suggestions + ai_result.get('suggestions', []):
            text = str(suggestion).strip()
            key = text.lower()
            if not text or key in seen_suggestions:
                continue

            # Drop non-actionable generic/obvious suggestions.
            if (
                'no other detectable issues' in key
                or 'no detectable issues' in key
                or key.startswith('there are no')
            ):
                continue

            # Drop AI suggestions that repeat company-name guidance
            if 'company name' in key and any('company name' in s.lower() for s in rule_suggestions):
                continue

            seen_suggestions.add(key)
            combined_suggestions.append(text)

        if issue_count == 0:
            assessment_text = 'No detectable invoice-data issues found.'
        else:
            assessment_text = f'{issue_count} issue(s) detected. Review and fix before submitting.'

        validation_response = {
            'status': status,
            'assessment': assessment_text,
            'issues': combined_issues,
            'suggestions': combined_suggestions,
            'score': score,
            'ai_enabled': True
        }
        
        return jsonify({
            'success': True,
            'validation': validation_response
        })
    
    except Exception as e:
        error_str = str(e)
        print(f"\n[ERROR] Error in AI validation:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {error_str}")
        traceback.print_exc()
        
        # Check for specific error types
        if "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
            return jsonify({
                'success': False,
                'error': 'Groq API quota exceeded. Please try again later.',
                'retry_after': 86400  # 24 hours
            }), 429
        elif "429" in error_str:
            return jsonify({
                'success': False,
                'error': 'Groq API rate limit hit. Please wait a moment and try again.',
                'retry_after': 60
            }), 429
        else:
            return jsonify({
                'success': False,
                'error': f'AI validation error: {error_str[:100]}. Check server logs for details.',
                'debug_error': error_str if os.environ.get('DEBUG') else None
            }), 500


@app.route("/api/ai/detect-rejection/<int:invoice_id>", methods=["POST"])
def ai_detect_rejection(invoice_id):
    """AI-powered rejection reason detection - automatically identifies issues"""
    print(f"\n{'='*60}")
    print(f"[AI-DETECT] Starting rejection detection for invoice {invoice_id}")
    
    if not openai_client:
        print(f"[AI-DETECT] [ERROR] Client not configured")
        return jsonify({
            'success': False,
            'error': 'AI features are not enabled. Please configure GEMINI_API_KEY.'
        }), 503
    
    print(f"[AI-DETECT] ✓ Client configured")
    
    try:
        # Fetch invoice details
        invoice_data = query_one("""
            SELECT 
                i.id,
                i.invoice_number,
                i.client_name,
                i.email,
                c.phone,
                i.notes,
                i.subtotal,
                i.tax,
                i.total,
                i.sent_date as invoice_date,
                'Net 30' as payment_terms
            FROM invoices i
            LEFT JOIN clients c ON i.client_id = c.id
            WHERE i.id = ?
        """, (invoice_id,))
        
        if not invoice_data:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404
        
        # Fetch line items
        line_items = query_all("""
            SELECT description, quantity, rate, total as amount
            FROM invoice_items
            WHERE invoice_id = ?
            ORDER BY id
        """, (invoice_id,))
        
        items = []
        for item in line_items:
            items.append({
                'description': item['description'],
                'quantity': int(item['quantity']),
                'rate': float(item['rate']),
                'amount': float(item['amount'])
            })
        
        # If no line items, create from invoice totals
        if not items:
            items = [{
                'description': invoice_data['notes'] or 'Service',
                'quantity': 1,
                'rate': float(invoice_data['subtotal']),
                'amount': float(invoice_data['subtotal'])
            }]

        invoice_date_display = format_date_ddmmyyyy(invoice_data['invoice_date'])
        due_date_display = 'Not provided'
        if invoice_data['invoice_date']:
            try:
                due_date_display = (
                    datetime.strptime(str(invoice_data['invoice_date']).split()[0], '%Y-%m-%d') + timedelta(days=30)
                ).strftime('%d/%m/%Y')
            except Exception:
                due_date_display = 'Not provided'
        
        # Call Groq API
        prompt = f"""You are an expert invoice reviewer. Analyze this invoice for REAL DETECTABLE ISSUES ONLY - things you can objectively identify from the data.

IMPORTANT: ONLY reject if there are actual data problems:
- Missing critical fields (dates, company name)
- Invalid formatting (bad email, malformed phone, bad dates)
- Spelling errors in descriptions
- Logic errors (due date before invoice date, zero amounts where there should be items)

Invoice number is system-generated and not user-editable; do NOT flag missing or inconsistent invoice number.

DO NOT reject for:
- Generic concerns like "verify the email is correct" or "ensure the rate is competitive"
- Missing optional fields like billing address or company logo
- Subjective judgments about whether something is "reasonable"
- Things that require verification outside the invoice data
- Invoice dates being in the future when format is valid

Invoice Details:
- Company: {invoice_data['client_name']}
- Email: {invoice_data['email']}
- Phone: {invoice_data['phone'] or 'Not provided'}
- Invoice Number: {invoice_data['invoice_number']}
- Invoice Date: {invoice_date_display} (dd/mm/yyyy)
- Due Date: {due_date_display} (dd/mm/yyyy)
- Payment Terms: {invoice_data['payment_terms']}

Line Items:
{json.dumps(items, indent=2)}

Totals:
- Subtotal: ${float(invoice_data['subtotal']):.2f}
- Tax (9% GST): ${float(invoice_data['tax']):.2f}
- Total: ${float(invoice_data['total']):.2f}

Notes: {invoice_data['notes'] or 'None'}

Output rules:
- rejection_title MUST be specific and short (no generic labels like "Rejection Reason")
- rejection_description MUST be exactly one sentence
- suggestions MUST be an empty array

Respond with valid JSON only (no markdown):
{{
    "should_reject": true/false,
    "rejection_title": "Specific issue title or 'No Data Issues Found'",
    "rejection_description": "One-sentence reason",
    "specific_issues": ["actual problem 1", "actual problem 2"],
    "suggestions": []
}}"""

        print(f"[AI-DETECT] Calling Groq API (llama-3.3-70b-versatile)...")
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=800
        )
        
        print(f"[AI-DETECT] ✓ API response received")
        
        # Parse AI response - handle potential markdown wrapping
        response_text = response.choices[0].message.content
        print(f"[AI-DETECT] Response text (first 200 chars): {response_text[:200]}...")
        
        if '```json' in response_text:
            print(f"[AI-DETECT] Extracting JSON from markdown (```json format)")
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            print(f"[AI-DETECT] Extracting JSON from markdown (``` format)")
            response_text = response_text.split('```')[1].split('```')[0].strip()
        
        print(f"[AI-DETECT] Parsing JSON: {response_text[:150]}...")
        ai_result = json.loads(response_text)

        # Normalize AI output to business rules
        ai_result['rejection_title'] = str(ai_result.get('rejection_title') or '').strip()
        ai_result['rejection_description'] = str(ai_result.get('rejection_description') or '').strip()
        ai_result['specific_issues'] = ai_result.get('specific_issues') or []
        ai_result['suggestions'] = []

        # Remove false positives that only complain about future dates
        ai_result['specific_issues'] = [
            issue for issue in ai_result['specific_issues']
            if not is_future_date_false_positive(issue)
        ]
        ai_result['specific_issues'] = [
            issue for issue in ai_result['specific_issues']
            if not is_due_before_false_positive(issue, invoice_data['invoice_date'], due_date_display)
        ]
        ai_result['specific_issues'] = [
            issue for issue in ai_result['specific_issues']
            if not is_due_terms_false_positive(issue, invoice_data['invoice_date'], due_date_display, invoice_data['payment_terms'])
        ]
        ai_result['specific_issues'] = [
            issue for issue in ai_result['specific_issues']
            if 'invoice number' not in str(issue).strip().lower()
        ]
        if is_future_date_false_positive(ai_result['rejection_description']):
            ai_result['rejection_description'] = ''
        if is_due_before_false_positive(ai_result['rejection_description'], invoice_data['invoice_date'], due_date_display):
            ai_result['rejection_description'] = ''
        if is_due_terms_false_positive(ai_result['rejection_description'], invoice_data['invoice_date'], due_date_display, invoice_data['payment_terms']):
            ai_result['rejection_description'] = ''
        if 'invoice number' in ai_result['rejection_description'].lower():
            ai_result['rejection_description'] = ''

        if not ai_result['rejection_title'] or ai_result['rejection_title'].lower() in ('rejection reason', 'reason', 'issue'):
            if ai_result['specific_issues']:
                ai_result['rejection_title'] = str(ai_result['specific_issues'][0]).split(':')[0].strip()[:80]
            elif ai_result.get('should_reject'):
                ai_result['rejection_title'] = 'Invoice Data Issue'
            else:
                ai_result['rejection_title'] = 'No Data Issues Found'

        if not ai_result['rejection_description']:
            ai_result['rejection_description'] = (
                'Detected invoice issues requiring correction.'
                if ai_result.get('should_reject')
                else 'AI did not detect clear invoice-data issues.'
            )

        if ai_result.get('should_reject') and not ai_result['specific_issues']:
            ai_result['should_reject'] = False
            ai_result['rejection_title'] = 'No Data Issues Found'
            ai_result['rejection_description'] = 'Invoice data passed AI checks with no detectable issues.'

        # Keep only one sentence
        ai_result['rejection_description'] = re.split(r'(?<=[.!?])\s+', ai_result['rejection_description'])[0].strip()
        if ai_result['rejection_description'] and ai_result['rejection_description'][-1] not in '.!?':
            ai_result['rejection_description'] += '.'
        
        print(f"[AI-DETECT] ✓ Success! Result: should_reject={ai_result.get('should_reject')}")
        print(f"{'='*60}\n")
        
        return jsonify({
            'success': True,
            'analysis': ai_result
        })
    
    except Exception as e:
        error_str = str(e)
        print(f"\n[ERROR] Error in AI rejection detection:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {error_str}")
        traceback.print_exc()
        
        # Check for specific error types
        if "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
            return jsonify({
                'success': False,
                'error': 'Gemini API quota exceeded. Free tier has reached daily limit. Please try again later.',
                'retry_after': 86400
            }), 429
        elif "429" in error_str:
            return jsonify({
                'success': False,
                'error': 'Gemini API rate limit hit. Please wait and try again.',
                'retry_after': 60
            }), 429
        else:
            return jsonify({
                'success': False,
                'error': f'AI analysis error: {error_str[:100]}',
                'debug_error': error_str if os.environ.get('DEBUG') else None
            }), 500


        # =========================================================================
        # =========================================================================
        # =========================================================================

# ============================================================================
# SETTINGS MANAGEMENT
# ============================================================================

def _is_public_hostname(hostname):
    if not hostname:
        return False

    host = hostname.strip().lower()
    if host in ('localhost', '127.0.0.1', '::1') or host.endswith('.local'):
        return False

    try:
        ip_obj = ipaddress.ip_address(host)
        return not (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(host, None)
        if not addr_info:
            return False
        for info in addr_info:
            ip_str = info[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


def _probe_webhook_url(url):
    """Best-effort reachability check for webhook endpoint."""
    try:
        head_request = Request(url, method='HEAD')
        with urlopen(head_request, timeout=4) as response:
            status = response.getcode() or 200
            return True, status, None
    except HTTPError as e:
        if e.code in (200, 201, 202, 204, 301, 302, 307, 308, 400, 401, 403, 404, 405):
            return True, e.code, None
        return False, e.code, str(e)
    except URLError as e:
        return False, None, str(e)
    except Exception as e:
        return False, None, str(e)


def evaluate_webhook_configuration(webhook_url, webhook_enabled):
    """Validate webhook settings and return UI-friendly status."""
    url = (webhook_url or '').strip()
    enabled = bool(webhook_enabled)
    invalid_message = 'Webhook cannot be connected. Only TurboSMTP webhook URLs are allowed (must include /webhooks/turbosmtp).'
    malformed_message = 'Webhook is invalid.'
    connectable_message = 'Webhook is connectable.'

    result = {
        'enabled': enabled,
        'url': url,
        'state': 'invalid-provider',
        'valid': False,
        'requires_manual_tracking': True,
        'message': invalid_message,
        'details': None
    }

    if not url:
        result.update({'state': 'empty'})
        return result

    parsed = urlparse(url)
    path_lower = (parsed.path or '').lower()

    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return result

    if '/webhooks/turbosmtp' not in path_lower:
        looks_like_turbosmtp_attempt = (
            'turbosmtp' in path_lower
            or 'webhooks' in path_lower
            or 'turbosmtp' in (parsed.netloc or '').lower()
        )
        if looks_like_turbosmtp_attempt:
            result.update({'message': malformed_message})
        return result

    hostname = parsed.hostname
    if not _is_public_hostname(hostname):
        return result

    is_reachable, status_code, error_detail = _probe_webhook_url(url)
    if not is_reachable:
        result.update({'details': error_detail})
        return result

    result.update({
        'state': 'active' if enabled else 'configured',
        'valid': True,
        'requires_manual_tracking': not enabled,
        'message': connectable_message,
        'details': f'Endpoint reachable (HTTP {status_code}).'
    })
    return result


def is_turbosmtp_webhook_request(flask_request):
    """Allow webhook calls only from TurboSMTP-style sources."""
    user_agent = (flask_request.headers.get('User-Agent') or '').lower()
    signature = (flask_request.headers.get('X-TurboSMTP-Signature') or '').strip()
    event_header = flask_request.headers.get('X-TurboSMTP-Event')
    has_turbosmtp_fingerprint = (
        'turbosmtp' in user_agent
        or 'serversmtp' in user_agent
        or bool(event_header)
        or bool(signature)
    )

    if not has_turbosmtp_fingerprint:
        return False

    secret = (get_setting('turbosmtp_consumer_secret', '') or '').strip()
    if secret and signature:
        body = flask_request.get_data() or b''
        expected = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    return True

def get_setting(key, default=None, user_id=1):
    """Get a setting value from the database"""
    try:
        setting = query_one(
            "SELECT setting_value, setting_type FROM settings WHERE user_id = ? AND setting_key = ?",
            (user_id, key)
        )
        if setting:
            value = setting['setting_value']
            # Convert based on type
            if setting['setting_type'] == 'boolean':
                return value.lower() in ('true', '1', 'yes')
            elif setting['setting_type'] == 'number':
                return float(value) if '.' in value else int(value)
            elif setting['setting_type'] == 'json':
                return json.loads(value) if value else None
            return value
        return default
    except Exception as e:
        print(f"Error getting setting {key}: {e}")
        return default

def set_setting(key, value, setting_type='text', description=None, user_id=1):
    """Set a setting value in the database"""
    try:
        # Convert value to string for storage
        if setting_type == 'boolean':
            value_str = 'true' if value else 'false'
        elif setting_type in ('number', 'json'):
            value_str = str(value) if value is not None else None
        else:
            value_str = str(value) if value is not None else None
        
        # Upsert: insert or update
        execute("""
            INSERT INTO settings (user_id, setting_key, setting_value, setting_type, description, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id, setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                setting_type = excluded.setting_type,
                description = excluded.description,
                updated_at = datetime('now')
        """, (user_id, key, value_str, setting_type, description))
        return True
    except Exception as e:
        print(f"Error setting {key}: {e}")
        return False


@app.get('/api/settings/validate-webhook')
def validate_webhook_url_api():
    """Live validation endpoint for Settings webhook UI."""
    if not is_current_user_admin():
        return jsonify({
            'success': False,
            'error': 'Settings access is restricted to admin users.'
        }), 403

    webhook_url = (request.args.get('url') or '').strip()
    enabled = (request.args.get('enabled') or 'false').lower() == 'true'
    validation = evaluate_webhook_configuration(webhook_url, enabled)
    return jsonify(validation)

@app.route("/settings", methods=['GET', 'POST'])
def settings():
    """Settings page for webhook URL, API credentials, and app configuration"""
    if not is_current_user_admin():
        flash('Settings are available to admin users only.', 'warning')
        return redirect(url_for('home'))

    user_id = 1  # Current user
    
    if request.method == 'POST':
        try:
            # Get form data
            webhook_url = request.form.get('webhook_url', '').strip()
            requested_webhook_enabled = request.form.get('webhook_enabled') == 'on'
            turbosmtp_key = request.form.get('turbosmtp_key', '').strip()
            turbosmtp_secret = request.form.get('turbosmtp_secret', '').strip()

            validation = evaluate_webhook_configuration(webhook_url, requested_webhook_enabled)
            webhook_enabled = requested_webhook_enabled and validation['state'] == 'active'
            
            # Save settings
            set_setting('webhook_url', webhook_url, 'text', 'TurboSMTP webhook endpoint URL', user_id)
            set_setting('webhook_enabled', webhook_enabled, 'boolean', 'Enable webhook processing', user_id)
            set_setting('turbosmtp_consumer_key', turbosmtp_key, 'password', 'TurboSMTP Consumer Key', user_id)
            set_setting('turbosmtp_consumer_secret', turbosmtp_secret, 'password', 'TurboSMTP Consumer Secret', user_id)

            current_settings = {
                'webhook_url': webhook_url,
                'webhook_enabled': webhook_enabled,
                'turbosmtp_key': turbosmtp_key,
                'turbosmtp_secret': turbosmtp_secret,
            }

            return render_template(
                'settings.html',
                title='Settings',
                settings=current_settings,
                webhook_validation=validation
            )
            
        except Exception as e:
            print(f"Error saving settings: {e}")
            flash('Error saving settings', 'error')
    
    # GET: Load current settings
    current_settings = {
        'webhook_url': get_setting('webhook_url', ''),
        'webhook_enabled': get_setting('webhook_enabled', False),
        'turbosmtp_key': get_setting('turbosmtp_consumer_key', ''),
        'turbosmtp_secret': get_setting('turbosmtp_consumer_secret', ''),
    }
    webhook_validation = {
        'state': 'empty',
        'message': ''
    }
    
    return render_template(
        'settings.html',
        title='Settings',
        settings=current_settings,
        webhook_validation=webhook_validation
    )


if __name__ == "__main__":
    app.run(debug=True)