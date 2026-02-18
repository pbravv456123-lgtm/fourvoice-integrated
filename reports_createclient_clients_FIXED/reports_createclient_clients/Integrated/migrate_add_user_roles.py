"""
Migration script to add role column to users table for existing databases.
Run this once to update your database schema.
"""

import sqlite3
import os

DB_FILE = "app.db"

def migrate():
    """Add role column to users table if it doesn't exist"""
    
    if not os.path.exists(DB_FILE):
        print(f"Database file '{DB_FILE}' not found. No migration needed.")
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Check if role column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'role' in columns:
            print("✓ Role column already exists in users table. No migration needed.")
            conn.close()
            return
        
        print("Adding 'role' column to users table...")
        
        # Add role column with default value 'employee'
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN role TEXT NOT NULL DEFAULT 'employee' 
            CHECK (role IN ('admin', 'employee'))
        """)
        
        # Update the default user (id=1) to be an admin
        cursor.execute("UPDATE users SET role = 'admin' WHERE id = 1")
        
        conn.commit()
        conn.close()
        
        print("✓ Successfully added role column to users table.")
        print("✓ User ID 1 has been set as admin.")
        print("\nMigration completed successfully!")
        
    except Exception as e:
        print(f"✗ Error during migration: {e}")
        if conn:
            conn.rollback()
            conn.close()
        raise

if __name__ == "__main__":
    print("="*60)
    print("Database Migration: Add User Roles")
    print("="*60)
    migrate()
