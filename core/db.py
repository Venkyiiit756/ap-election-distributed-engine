import sqlite3
import os
import json
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coordinator", "registry.sqlite")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")

    # Constituencies table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS constituencies (
        ac_no INTEGER PRIMARY KEY,
        ac_slug TEXT UNIQUE,
        ac_name TEXT,
        district_id TEXT,
        district_name TEXT,
        status TEXT DEFAULT 'PENDING',
        total_gps INTEGER DEFAULT 0,
        completed_gps INTEGER DEFAULT 0,
        total_voters INTEGER DEFAULT 0,
        completed_voters INTEGER DEFAULT 0,
        assigned_node TEXT,
        lease_expires_at REAL DEFAULT 0,
        gdrive_url TEXT,
        updated_at REAL
    )
    """)

    # Gram Panchayats table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS gram_panchayats (
        gp_id TEXT PRIMARY KEY,
        ac_no INTEGER,
        mandal_id TEXT,
        mandal_name TEXT,
        gp_name_en TEXT,
        gp_name_te TEXT,
        official_voters INTEGER DEFAULT 0,
        harvested_voters INTEGER DEFAULT 0,
        male_voters INTEGER DEFAULT 0,
        female_voters INTEGER DEFAULT 0,
        other_voters INTEGER DEFAULT 0,
        wards_count INTEGER DEFAULT 0,
        dpo_confirmed INTEGER DEFAULT 0,
        status TEXT DEFAULT 'PENDING',
        assigned_node TEXT,
        lease_expires_at REAL DEFAULT 0,
        updated_at REAL,
        FOREIGN KEY (ac_no) REFERENCES constituencies (ac_no)
    )
    """)

    # Safe column migrations for existing gram_panchayats table
    for col_def in [
        "male_voters INTEGER DEFAULT 0",
        "female_voters INTEGER DEFAULT 0",
        "other_voters INTEGER DEFAULT 0",
        "wards_count INTEGER DEFAULT 0",
        "dpo_confirmed INTEGER DEFAULT 0",
        "district_id TEXT",
        "rev_div_id TEXT"
    ]:
        col_name = col_def.split()[0]
        try:
            cur.execute(f"ALTER TABLE gram_panchayats ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass

    # MPTC Delimitation Mappings table (MPTC -> GP -> Ward Ranges)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mptc_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        district_id TEXT,
        mandal_id TEXT,
        mandal_name TEXT,
        mptc_id TEXT,
        mptc_name TEXT,
        gp_id TEXT,
        gp_name TEXT,
        wards_range TEXT,
        ac_no INTEGER,
        updated_at REAL,
        UNIQUE(mandal_id, mptc_id, gp_id, wards_range)
    )
    """)

    # GP Ward-level Voter Strengths table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ward_strengths (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ac_no INTEGER,
        mandal_id TEXT,
        gp_id TEXT,
        ward_no TEXT,
        male_voters INTEGER DEFAULT 0,
        female_voters INTEGER DEFAULT 0,
        other_voters INTEGER DEFAULT 0,
        total_voters INTEGER DEFAULT 0,
        updated_at REAL,
        UNIQUE(gp_id, ward_no)
    )
    """)

    # Active Worker Nodes table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS worker_nodes (
        node_id TEXT PRIMARY KEY,
        hostname TEXT,
        ip_address TEXT,
        workers_count INTEGER,
        last_heartbeat REAL,
        current_ac INTEGER,
        rate_voters_per_sec REAL DEFAULT 0,
        status TEXT DEFAULT 'ACTIVE'
    )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Initialized distributed registry at: {DB_PATH}")

if __name__ == "__main__":
    init_db()
