# seed_data.py - Simple, working version
import sqlite3
from datetime import datetime, timedelta
import random
import sys
import os

# Your core services
CORE_SERVICES = [
    # Services (5 items)1
    {"code": "WEB-001", "description": "Web Development Service", "details": "Full-stack web development", "category": "Services", "rate": 150.00},
    {"code": "DES-001", "description": "UI/UX Design", "details": "Interface and experience design", "category": "Services", "rate": 120.00},
    {"code": "SEO-001", "description": "SEO Optimization", "details": "Search engine optimization service", "category": "Services", "rate": 300.00},
    {"code": "CNT-001", "description": "Content Writing", "details": "Professional content writing", "category": "Services", "rate": 80.00},
    {"code": "HST-001", "description": "Hosting Service", "details": "Cloud hosting solution", "category": "Services", "rate": 250.00},
    # Consulting (2 items)
    {"code": "CON-001", "description": "Consulting Hour", "details": "Business consulting services", "category": "Consulting", "rate": 200.00},
    {"code": "STR-001", "description": "Strategy Session", "details": "Business strategy consulting", "category": "Consulting", "rate": 400.00},
    # Packages (2 items)
    {"code": "MNT-001", "description": "Monthly Maintenance", "details": "Website maintenance package", "category": "Packages", "rate": 500.00},
    {"code": "SUP-001", "description": "Premium Support Package", "details": "24/7 priority support", "category": "Packages", "rate": 800.00},
    # Products (1 item)
    {"code": "MKT-001", "description": "Marketing Kit", "details": "Complete marketing materials", "category": "Products", "rate": 350.00}
]

# Company names
COMPANY_NAMES = [
    "TechCorp Inc", "Digital Solutions", "WebCrafters", "ByteSystems", "CloudInnovate",
    "PixelPerfect", "CodeMasters", "DevCrew", "DataDynamics", "FutureTech",
    "MarketingPros", "BrandBoost", "CreativeMinds", "AdAgency", "SocialSphere",
    "ContentCrafters", "BuzzBuilders", "GrowthGurus", "LeadLabs", "ConversionCo",
    "StrategyPartners", "BusinessConsult", "GrowthAdvisors", "ExecutiveEdge",
    "ManagementMasters", "ProfitPartners", "VisionaryGroup", "SuccessSystems",
    "GlobalRetail", "ShopOnline", "EcomExpress", "MarketPlace", "RetailHub",
    "StoreFront", "BuyDirect", "SalesCentral", "CommerceCorp", "ShopSmart",
    "ManufacturePro", "FactoryWorks", "ProductionPlus", "IndustrialTech",
    "BuildMasters", "AssemblyLine", "QualityWorks", "PrecisionParts",
    "ServiceFirst", "SupportSpecialists", "HelpDeskHeroes", "CustomerCare"
]

def init_db():
    """Initialize database with schema"""
    print("Creating/updating database schema...")
    conn = sqlite3.connect('app.db')
    
    # Read and execute schema
    with open('schema.sql', 'r') as f:
        schema = f.read()
        # Execute schema in parts to avoid errors
        for statement in schema.split(';'):
            if statement.strip():
                try:
                    conn.execute(statement.strip() + ';')
                except sqlite3.OperationalError as e:
                    # Table might already exist, that's ok
                    if "already exists" not in str(e):
                        print(f"⚠️  Schema warning: {e}")
    
    conn.commit()
    conn.close()
    print("Database schema initialized")

def ensure_user_exists():
    """Ensure user_id=1 exists"""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (id, name, email, password_hash)
            VALUES (1, 'Default User', 'admin@example.com', 'placeholder_hash')
        """)
        print("Created default user")
    
    conn.commit()
    conn.close()

def seed_services():
    """Seed core services"""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Clear existing services for user 1
    cursor.execute("DELETE FROM services WHERE user_id = 1")
    
    # Insert core services
    for service in CORE_SERVICES:
        cursor.execute("""
            INSERT INTO services (user_id, code, description, details, category, rate)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (1, service['code'], service['description'], 
              service['details'], service['category'], service['rate']))
    
    conn.commit()
    conn.close()
    print(f"Seeded {len(CORE_SERVICES)} services")

def generate_email(company_name):
    """Generate email from company name"""
    clean_name = ''.join(c for c in company_name.lower() if c.isalnum())
    return f"billing@{clean_name}.com"

def generate_phone():
    """Generate valid Singapore phone number (8 digits starting with 6, 8, or 9)"""
    # First digit must be 6, 8, or 9 for Singapore mobile/landline numbers
    first_digit = random.choice([6, 8, 9])
    # Generate remaining 7 digits
    remaining = random.randint(1000000, 9999999)
    # Format as: +65 9123 4567
    phone = f"+65 {first_digit}{remaining:07d}"
    # Insert space after 4th digit for readability
    return f"+65 {first_digit}{str(remaining)[:3]} {str(remaining)[3:7]}"

def generate_address():
    """Generate Singapore address"""
    streets = [
        "Orchard Road", "Raffles Place", "Marina Boulevard", "Shenton Way",
        "Robinson Road", "Cecil Street", "Collyer Quay", "Marina Bay",
        "Sentosa Gateway", "Jurong East Avenue", "Changi Business Park"
    ]
    return f"{random.randint(1, 999)} {random.choice(streets)}"

def seed_clients(num_clients=50):
    """Seed clients"""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Clear existing clients for user 1
    cursor.execute("DELETE FROM clients WHERE user_id = 1")
    
    # Select unique company names
    if num_clients > len(COMPANY_NAMES):
        companies = COMPANY_NAMES.copy()
        while len(companies) < num_clients:
            base = random.choice(COMPANY_NAMES)
            suffix = random.choice(["Group", "Ltd", "International", "Pte Ltd"])
            companies.append(f"{base} {suffix}")
    else:
        companies = random.sample(COMPANY_NAMES, num_clients)
    
    # Ensure all company names are unique
    companies = list(dict.fromkeys(companies))  # Remove duplicates while preserving order
    
    # Singapore business locations
    singapore_locations = [
        {"city": "Singapore", "state": "Central", "postal": "238801", "country": "Singapore"},
        {"city": "Singapore", "state": "Downtown", "postal": "018956", "country": "Singapore"},
        {"city": "Singapore", "state": "Marina Bay", "postal": "018960", "country": "Singapore"},
        {"city": "Singapore", "state": "Orchard", "postal": "238863", "country": "Singapore"},
        {"city": "Singapore", "state": "Raffles Place", "postal": "048624", "country": "Singapore"},
        {"city": "Singapore", "state": "Shenton Way", "postal": "068803", "country": "Singapore"},
        {"city": "Singapore", "state": "Changi", "postal": "486041", "country": "Singapore"},
        {"city": "Singapore", "state": "Jurong East", "postal": "609607", "country": "Singapore"},
    ]
    
    client_ids = []
    seen_emails = set()
    
    for company in companies:
        location = random.choice(singapore_locations)
        email = generate_email(company)
        
        # Ensure email is unique
        counter = 1
        original_email = email
        while email in seen_emails:
            email = f"{original_email.replace('.com', '')}{counter}.com"
            counter += 1
        
        seen_emails.add(email)
        
        cursor.execute("""
            INSERT INTO clients (user_id, client_name, email, phone, address, city, state, postal_code, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (1, company, email, generate_phone(), 
               generate_address(), location["city"], location["state"], location["postal"], location["country"]))
        client_ids.append(cursor.lastrowid)
    
    conn.commit()
    conn.close()
    print(f"✅ Created {num_clients} clients")
    return client_ids

def seed_approval_statuses():
    """
    Seed approval statuses for invoices in a commercial-ready manner.
    Distributes statuses realistically with proper dates and reasons.
    """
    print("Seeding approval statuses...")
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Get all invoices (excluding special queksiqi@gmail.com invoice which already has approval_status set)
    cursor.execute("SELECT id, created_at FROM invoices WHERE email != 'queksiqi@gmail.com' ORDER BY id")
    invoices = cursor.fetchall()
    
    if not invoices:
        print("No invoices found to update with approval statuses")
        conn.close()
        return
    
    # Define distribution: 50% pending, 35% approved, 5% rejected, 10% on-hold
    # Invoices are automatically good quality, so very few should be rejected
    num_invoices = len(invoices)
    num_pending = int(num_invoices * 0.5)
    num_approved = int(num_invoices * 0.35)
    num_rejected = int(num_invoices * 0.05)
    num_on_hold = num_invoices - num_pending - num_approved - num_rejected
    
    # Shuffle invoices for random distribution
    shuffled = list(invoices)
    random.shuffle(shuffled)
    
    # Rejection reasons - only for actual data quality issues
    # Format: (reason, category) - 'editable' means user can re-edit, 'non-editable' means user must acknowledge
    rejection_reasons = [
        ("[EDITABLE] Line Item Spelling Error: One or more line item descriptions contain spelling mistakes.", "editable"),
        ("[EDITABLE] Invalid Email Format: Recipient email format is invalid for delivery.", "editable"),
        ("[EDITABLE] Missing Company Name: Client company name is blank and must be provided.", "editable"),
        ("[NOT_EDITABLE] Compliance Hold: Client account is currently under compliance review.", "non-editable")
    ]
    
    # On-hold reasons (commercial-ready)
    on_hold_reasons = [
        "Awaiting manager approval for budget allocation",
        "Pending verification of service completion",
        "Client has requested payment schedule review",
        "Accounting cycle closed - will process next period",
        "Awaiting clarification on line item details",
        "Budget reallocation in progress",
        "End of quarter review - temporarily on hold"
    ]
    
    current_time = datetime.now()
    today = current_time.strftime('%Y-%m-%d %H:%M:%S')
    
    updated_count = 0
    
    # Assign pending status (no approval date)
    for i in range(num_pending):
        invoice_id = shuffled[i][0]
        cursor.execute("""
            UPDATE invoices 
            SET approval_status = 'pending',
                approval_date = NULL,
                approved_by = NULL,
                approval_reason = NULL
            WHERE id = ?
        """, (invoice_id,))
        updated_count += 1
    
    # Assign approved status (approved within last 7 days)
    for i in range(num_pending, num_pending + num_approved):
        invoice_id = shuffled[i][0]
        # Random approval date within last 7 days
        days_ago = random.randint(0, 7)
        approval_date = (current_time - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute("""
            UPDATE invoices 
            SET approval_status = 'approved',
                approval_date = ?,
                approved_by = 1,
                approval_reason = NULL
            WHERE id = ?
        """, (approval_date, invoice_id))
        updated_count += 1
    
    # Assign rejected status
    for i in range(num_pending + num_approved, num_pending + num_approved + num_rejected):
        invoice_id = shuffled[i][0]
        # Random rejection date within last 5 days
        days_ago = random.randint(0, 5)
        rejection_date = (current_time - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
        reason_text, reason_category = random.choice(rejection_reasons)
        # Store the category info in a way we can extract - format: "reason | category"
        reason_with_category = f"{reason_text} | {reason_category}"

        # Apply data mutations to make the rejection reason actually true
        if "Invalid Email Format" in reason_text:
            cursor.execute(
                "UPDATE invoices SET email = ? WHERE id = ?",
                ("billing@invalid-email", invoice_id)
            )
        elif "Missing Company Name" in reason_text:
            cursor.execute(
                "UPDATE invoices SET client_name = ? WHERE id = ?",
                ("", invoice_id)
            )
        elif "Line Item Spelling Error" in reason_text:
            cursor.execute(
                "SELECT id, description FROM invoice_items WHERE invoice_id = ? ORDER BY id LIMIT 1",
                (invoice_id,)
            )
            item_row = cursor.fetchone()
            if item_row:
                item_id, description = item_row
                typo_description = description.replace("Development", "Developmnt").replace("Consulting", "Consuling")
                if typo_description == description:
                    typo_description = f"{description} - Developmnt"
                cursor.execute(
                    "UPDATE invoice_items SET description = ? WHERE id = ?",
                    (typo_description, item_id)
                )
        
        cursor.execute("""
            UPDATE invoices 
            SET approval_status = 'rejected',
                approval_date = ?,
                approved_by = 1,
                approval_reason = ?
            WHERE id = ?
        """, (rejection_date, reason_with_category, invoice_id))
        updated_count += 1
    
    # Assign on-hold status
    for i in range(num_pending + num_approved + num_rejected, num_invoices):
        invoice_id = shuffled[i][0]
        # Random hold date within last 3 days
        days_ago = random.randint(0, 3)
        hold_date = (current_time - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
        reason = random.choice(on_hold_reasons)
        
        cursor.execute("""
            UPDATE invoices 
            SET approval_status = 'on-hold',
                approval_date = ?,
                approved_by = 1,
                approval_reason = ?
            WHERE id = ?
        """, (hold_date, reason, invoice_id))
        updated_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"Updated {updated_count} invoices with approval statuses:")
    print(f"   • Pending: {num_pending}")
    print(f"   • Approved: {num_approved}")
    print(f"   • Rejected: {num_rejected}")
    print(f"   • On Hold: {num_on_hold}")

def generate_invoice_number(sequence):
    """Generate invoice number"""
    year = datetime.now().year
    return f"INV-{year}-{sequence:03d}"

def seed_invoices(num_invoices=25, client_ids=None):
    """Seed invoices"""
    if not client_ids:
        print("No clients available")
        return
    
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Clear existing invoices for user 1
    cursor.execute("DELETE FROM invoice_items WHERE invoice_id IN (SELECT id FROM invoices WHERE user_id = 1)")
    cursor.execute("DELETE FROM invoices WHERE user_id = 1")
    
    # Create special client for queksiqi@gmail.com if it doesn't exist
    cursor.execute("SELECT id FROM clients WHERE email = 'queksiqi@gmail.com' AND user_id = 1")
    special_client = cursor.fetchone()
    if not special_client:
        cursor.execute("""
            INSERT INTO clients (user_id, client_name, email, phone, address, city, state, postal_code, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (1, 'QuekSiqi Test Client', 'queksiqi@gmail.com', '+65 9999 9999',
               '999 Test Street', 'Singapore', 'Test', '999999', 'Singapore'))
        special_client_id = cursor.lastrowid
    else:
        special_client_id = special_client[0]
    
    # Get all services
    cursor.execute("SELECT id, code, description, details, category, rate FROM services WHERE user_id = 1")
    services = cursor.fetchall()
    
    if not services:
        print("No services found")
        return
    
    # Get client details
    placeholders = ','.join(['?'] * len(client_ids))
    cursor.execute(f"SELECT id, client_name, email FROM clients WHERE id IN ({placeholders})", client_ids)
    clients = cursor.fetchall()
    
    invoices_created = 0
    
    for i in range(1, num_invoices + 1):
        # Pick a client
        client_id, client_name, email = random.choice(clients)
        
        # Generate invoice number
        invoice_number = generate_invoice_number(i)
        
        # Generate dates
        sent_date = (datetime.now() - timedelta(days=random.randint(1, 90))).strftime('%Y-%m-%d')
        
        # Determine status with proper timeline
        # Possible progressions: Pending → (Delivered|Failed) → Opened
        status = random.choice(['pending', 'pending', 'delivered', 'failed', 'opened'])  # More pending invoices
        
        # Initialize timeline dates
        delivered_date = None
        failed_date = None
        opened_date = None
        failed_reason = None
        
        # Build proper status progression
        if status == 'opened':
            # Opened invoices came from delivered invoices that were then opened
            delivered_date = (datetime.strptime(sent_date, '%Y-%m-%d') + 
                            timedelta(hours=random.randint(1, 48))).strftime('%Y-%m-%d %H:%M:%S')
            opened_date = (datetime.strptime(sent_date, '%Y-%m-%d') + 
                          timedelta(days=random.randint(1, 5))).strftime('%Y-%m-%d %H:%M:%S')
        elif status == 'delivered':
            # Delivered invoices have delivery date but NOT opened_date
            delivered_date = (datetime.strptime(sent_date, '%Y-%m-%d') + 
                            timedelta(hours=random.randint(1, 48))).strftime('%Y-%m-%d %H:%M:%S')
        elif status == 'failed':
            # Failed invoices have failed_date, no delivery
            failed_reasons = [
                "Email address does not exist - domain inactive",
                "Recipient mailbox full - server rejected email",
                "Email address does not exist - user unknown",
                "SMTP connection timeout - mail server unreachable",
                "Message blocked by recipient's spam filter",
                "Invalid recipient address format",
                "Recipient domain not found - DNS lookup failed"
            ]
            failed_reason = random.choice(failed_reasons)
            failed_date = (datetime.strptime(sent_date, '%Y-%m-%d') + 
                          timedelta(hours=random.randint(1, 24))).strftime('%Y-%m-%d %H:%M:%S')
        # Pending: no additional dates
        
        # Generate invoice items (1-4 items)
        num_items = random.randint(1, 4)
        subtotal = 0
        invoice_items = []
        
        for _ in range(num_items):
            service = random.choice(services)
            service_id, service_code, description, details, category, rate = service
            
            if category == 'Packages':
                quantity = 1
            else:
                quantity = random.randint(1, 10)
            
            total = rate * quantity
            subtotal += total
            
            invoice_items.append({
                'service_id': service_id,
                'service_code': service_code,
                'description': description,
                'details': details,
                'category': category,
                'quantity': quantity,
                'rate': rate,
                'total': total
            })
        
        # Calculate tax and total (9% GST)
        tax = subtotal * 0.09
        total_amount = subtotal + tax
        
        # Generate notes from invoice items
        notes = '; '.join([f"{item['description']} ({item['quantity']}x @ ${item['rate']:.2f})" for item in invoice_items])
        
        # Insert invoice
        cursor.execute("""
            INSERT INTO invoices 
            (user_id, invoice_number, client_id, client_name, email, 
             sent_date, delivered_date, failed_date, opened_date, resent_date, status, failed_reason, subtotal, tax, total, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (1, invoice_number, client_id, client_name, email,
              sent_date, delivered_date, failed_date, opened_date, None, status, failed_reason, subtotal, tax, total_amount, notes))
        
        invoice_id = cursor.lastrowid
        
        # Insert invoice items
        for item in invoice_items:
            cursor.execute("""
                INSERT INTO invoice_items 
                (invoice_id, service_id, service_code, description, details, 
                 category, quantity, rate, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (invoice_id, item['service_id'], item['service_code'],
                  item['description'], item['details'], item['category'],
                  item['quantity'], item['rate'], item['total']))
        
        invoices_created += 1
        
        if i % 10 == 0:
            print(f"   Created invoice {i}/{num_invoices}")
    
    # Create special invoice for queksiqi@gmail.com with FAILED status
    # This invoice will appear in invoice_delivery but NOT in approvals
    special_service = services[0]  # Use first service
    service_id, service_code, description, details, category, rate = special_service
    
    special_quantity = 2
    special_subtotal = rate * special_quantity
    special_tax = special_subtotal * 0.09
    special_total = special_subtotal + special_tax
    special_notes = f"{description} - Test Invoice"
    
    # Create invoice with FAILED delivery status
    cursor.execute("""
        INSERT INTO invoices 
        (user_id, invoice_number, client_id, client_name, email, 
         sent_date, delivered_date, failed_date, opened_date, resent_date, status, failed_reason, subtotal, tax, total, notes, approval_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (1, f"INV-{datetime.now().year}-9999", special_client_id, 'QuekSiqi Test Client', 'queksiqi@gmail.com',
          (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'), None, 
          (datetime.now() - timedelta(days=1, hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
          None, None, 'failed',
          'Email address rejected by recipient server - mailbox unknown',
          special_subtotal, special_tax, special_total, special_notes, 'approved'))
    
    special_invoice_id = cursor.lastrowid
    
    # Insert invoice item for special invoice
    cursor.execute("""
        INSERT INTO invoice_items 
        (invoice_id, service_id, service_code, description, details, 
         category, quantity, rate, total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (special_invoice_id, service_id, service_code, description, details,
           category, special_quantity, rate, special_subtotal))
    
    conn.commit()
    conn.close()
    print(f"Created {invoices_created} invoices")
    print(f"   Created special invoice for queksiqi@gmail.com with FAILED status")

def show_stats():
    """Show database statistics"""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    print("\nDATABASE STATISTICS:")
    
    # Count tables
    tables = ['users', 'services', 'clients', 'invoices', 'invoice_items']
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  • {table:15}: {count}")
    
    # Invoice status breakdown
    cursor.execute("""
        SELECT status, COUNT(*) 
        FROM invoices 
        WHERE user_id = 1 
        GROUP BY status
    """)
    print("\n📈 Invoice Status:")
    for status, count in cursor.fetchall():
        print(f"  • {status:10}: {count}")
    
    # Client with most invoices
    cursor.execute("""
        SELECT c.client_name, COUNT(i.id) as invoice_count
        FROM clients c
        LEFT JOIN invoices i ON c.id = i.client_id
        WHERE c.user_id = 1
        GROUP BY c.id
        ORDER BY invoice_count DESC
        LIMIT 5
    """)
    print("\nTop Clients by Invoice Count:")
    for client, count in cursor.fetchall():
        print(f"  • {client:30}: {count} invoices")
    
    # Clients with 0 invoices
    cursor.execute("""
        SELECT COUNT(*)
        FROM clients c
        WHERE c.user_id = 1 
        AND NOT EXISTS (
            SELECT 1 FROM invoices i 
            WHERE i.client_id = c.id
        )
    """)
    zero_invoice_clients = cursor.fetchone()[0]
    print(f"\nClients with 0 invoices: {zero_invoice_clients}")
    
    conn.close()

def seed_default_settings():
    """Seed default application settings"""
    print("Seeding default settings...")
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    default_settings = [
        (1, 'webhook_url', '', 'text', 'TurboSMTP webhook endpoint URL'),
        (1, 'webhook_enabled', 'false', 'boolean', 'Enable webhook processing'),
        (1, 'turbosmtp_consumer_key', '206dba74960ac7a826cb', 'password', 'TurboSMTP Consumer Key'),
        (1, 'turbosmtp_consumer_secret', 'DMnUWjXp0z4ViHLJyfN7', 'password', 'TurboSMTP Consumer Secret'),
        (1, 'business_name', 'FourVoice', 'text', 'Business name for invoices'),
        (1, 'business_email', 'emp@gmail.com', 'text', 'Business contact email'),
        (1, 'business_phone', '+65 9123 4567', 'text', 'Business contact phone'),
    ]
    
    for user_id, key, value, setting_type, description in default_settings:
        cursor.execute("""
            INSERT OR REPLACE INTO settings (user_id, setting_key, setting_value, setting_type, description, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (user_id, key, value, setting_type, description))
    
    conn.commit()
    conn.close()
    print(f"✓ Seeded {len(default_settings)} default settings")

def main():
    """Main function"""
    print("=" * 50)
    print("DATABASE SEEDING TOOL")
    print("=" * 50)
    
    # Get parameters
    try:
        num_invoices = int(sys.argv[1]) if len(sys.argv) > 1 else 100
        num_clients = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    except ValueError:
        print("Invalid parameters. Using defaults.")
        num_invoices = 100
        num_clients = 80
    
    print(f"\nSettings:")
    print(f"  • Invoices to create: {num_invoices}")
    print(f"  • Clients to create: {num_clients}")
    print(f"  • Expected ratio: {num_clients} clients : {num_invoices} invoices")
    print()
    
    # Initialize
    init_db()
    ensure_user_exists()
    seed_services()
    
    # Seed clients and get their IDs
    client_ids = seed_clients(num_clients)
    
    # Seed invoices
    seed_invoices(num_invoices, client_ids)
    
    # Seed approval statuses
    seed_approval_statuses()
    
    # Seed default settings
    seed_default_settings()
    
    # Show statistics
    show_stats()
    
    print("\n" + "=" * 50)
    print("SEEDING COMPLETE!")
    print("=" * 50)
    print("\nYour database now contains:")
    print(f"   • {len(CORE_SERVICES)} services")
    print(f"   • {num_clients} clients")
    print(f"   • {num_invoices} invoices (with approval statuses)")
    print(f"\nDatabase file: app.db")
    print("\nYou can now run your Flask app with: python app.py")

if __name__ == "__main__":
    main()