import sqlite3
import os
import json
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coordinator", "registry.sqlite")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Constituencies table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS constituencies (
        ac_no INTEGER PRIMARY KEY,
        ac_slug TEXT UNIQUE,
        ac_name TEXT,
        district_id TEXT,
        district_name TEXT,
        status TEXT DEFAULT 'PENDING',  -- PENDING, LEASED, IN_PROGRESS, COMPLETED, SYNCED
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
        status TEXT DEFAULT 'PENDING',  -- PENDING, IN_PROGRESS, COMPLETED
        assigned_node TEXT,
        lease_expires_at REAL DEFAULT 0,
        updated_at REAL,
        FOREIGN KEY (ac_no) REFERENCES constituencies (ac_no)
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

def seed_constituencies_from_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    for ac in meta.get("sample_constituencies", []):
        cur.execute("""
        INSERT OR IGNORE INTO constituencies (ac_no, ac_slug, ac_name, district_id, district_name, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (ac["ac_no"], ac["ac_slug"], ac["ac_name"], ac["district_id"], ac["district_name"], time.time()))

    conn.commit()
    conn.close()
    print("[DB] Seeded initial constituencies into coordinator registry.")

if __name__ == "__main__":
    init_db()
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "state_metadata.json")
    if os.path.exists(cfg):
        seed_constituencies_from_config(cfg)
