import sqlite3, os, time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coordinator", "registry.sqlite")
conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()
cur.execute("""
UPDATE constituencies
SET status = 'PENDING', assigned_node = NULL, lease_expires_at = 0, updated_at = ?
WHERE status != 'SYNCED'
""", (time.time(),))
conn.commit()
cnt = cur.execute("SELECT COUNT(*) FROM constituencies WHERE status='PENDING'").fetchone()[0]
print(f"[Queue] Queued {cnt} constituencies for live APSEC GP/Ward/MPTC extraction.")
conn.close()
