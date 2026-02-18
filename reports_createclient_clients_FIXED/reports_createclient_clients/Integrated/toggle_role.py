"""
Quick script to toggle user role between admin and employee for testing
"""
import sqlite3
import os

DB_FILE = "app.db"

def toggle_role():
    """Toggle the default user's role"""
    try:
        if not os.path.exists(DB_FILE):
            print(f"❌ Database file '{DB_FILE}' not found")
            print("   Please run the app first to initialize the database")
            return
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("❌ Users table not found in database")
            print("   Please run the app first to initialize the database")
            conn.close()
            return
        
        # Check if role column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'role' not in columns:
            print("❌ Role column not found in users table")
            print("   Please run: python migrate_add_user_roles.py")
            conn.close()
            return
        
        # Get current role
        cursor.execute("SELECT id, name, email, role FROM users WHERE id = 1")
        user = cursor.fetchone()
        
        if not user:
            print("❌ Default user not found (ID 1)")
            conn.close()
            return
        
        user_id, name, email, current_role = user
        new_role = 'employee' if current_role == 'admin' else 'admin'
        
        # Define role-based user details
        role_settings = {
            'admin': {'name': 'Admin User', 'email': 'admin@example.com'},
            'employee': {'name': 'Employee', 'email': 'emp@gmail.com'}
        }
        
        new_name = role_settings[new_role]['name']
        new_email = role_settings[new_role]['email']
        
        # Update role, name, and email
        cursor.execute("UPDATE users SET role = ?, name = ?, email = ? WHERE id = 1", (new_role, new_name, new_email))
        conn.commit()
        conn.close()
        
        print(f"✓ User updated successfully!")
        print(f"  Previous: {name} ({current_role})")
        print(f"           Email: {email}")
        print(f"")
        print(f"  New: {new_name} ({new_role})")
        print(f"       Email: {new_email}")
        print(f"")
        print(f"Permissions:")
        if new_role == 'admin':
            print(f"  ✓ Can manage settings")
            print(f"  ✓ Can approve/reject invoices")
            print(f"  ✓ Can access all features")
        else:
            print(f"  ✗ Cannot manage settings")
            print(f"  ✗ Cannot approve/reject invoices")
            print(f"  ✓ Can create and view invoices")
            print(f"  ✓ Can resend invoices")
        print(f"")
        print(f"Restart the Flask app to see changes.")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("Toggle User Role (Admin ↔ Employee)")
    print("="*60)
    toggle_role()
