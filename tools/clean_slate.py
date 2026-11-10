import sqlite3, os, time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coordinator", "registry.sqlite")
conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()

cur.execute("DELETE FROM gram_panchayats")
cur.execute("DELETE FROM ward_strengths")
cur.execute("DELETE FROM mptc_mappings")
cur.execute("UPDATE mandals SET status = 'PENDING', total_gps = 0, total_voters = 0, assigned_node = NULL, updated_at = ?", (time.time(),))
cur.execute("""
UPDATE constituencies
SET total_gps = 0, completed_gps = 0, total_voters = 0, completed_voters = 0,
    status = CASE WHEN status='SYNCED' THEN 'SYNCED' ELSE 'PENDING' END,
    assigned_node = NULL, lease_expires_at = 0, updated_at = ?
""", (time.time(),))
# Keep Kakinada Rural & Peddapuram existing completed stats until re-rolled
cur.execute("UPDATE constituencies SET total_gps=35, completed_gps=35, total_voters=198392, completed_voters=198392 WHERE ac_no=38")
cur.execute("UPDATE constituencies SET total_gps=41, completed_gps=41, total_voters=100816, completed_voters=100816 WHERE ac_no=39")

conn.commit()
print("Cleaned stale rows! Total mandals pending:", cur.execute("SELECT count(*) FROM mandals WHERE status='PENDING'").fetchone()[0])
conn.close()
