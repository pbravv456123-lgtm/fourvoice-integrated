import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "app.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_conn(): # Get a database connection
    conn = sqlite3.connect(DB_PATH) # Connect to the database
    conn.row_factory = sqlite3.Row # Enable dictionary-like row access
    conn.execute("PRAGMA foreign_keys = ON;") # Enable foreign key support
    return conn # Return the connection


def init_db(): # Initialize the database schema
    with get_conn() as conn: # Get database connection
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8")) # Execute schema script


def query_all(sql, params=()): # Query multiple rows
    with get_conn() as conn: # Get database connection
        return conn.execute(sql, params).fetchall() # Fetch all results


def query_one(sql, params=()): # Query single row
    with get_conn() as conn: # Get database connection
        return conn.execute(sql, params).fetchone() # Fetch one result


def execute(sql, params=()): # Execute a statement
    with get_conn() as conn: # Get database connection
        cur = conn.execute(sql, params) # Execute the SQL statement
        conn.commit() # Commit changes
        return cur.lastrowid # Return last inserted row ID



