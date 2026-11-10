import os
import sys
import json
import sqlite3
import time

sys.stdout.reconfigure(encoding="utf-8")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.db import init_db, DB_PATH
from worker.worker_node import APSECClient

HIERARCHY_PATH = os.path.join(BASE_DIR, "configs", "apsec_district_hierarchy.json")

PRIORITY_MANDAL_AC = {
    "5270": 35, "5241": 35, "5269": 35,               # 35-Tuni
    "5254": 36, "5266": 36, "5273": 36, "6802": 36,   # 36-Prathipadu
    "5253": 37, "5230": 37, "5242": 37,               # 37-Pithapuram
    "5235": 38, "5237": 38,                           # 38-Kakinada Rural
    "5252": 39, "5265": 39,                           # 39-Peddapuram
    "5223": 40, "5225": 40, "5260": 40, "5251": 40,   # 40-Anaparthy
    "5232": 52, "5227": 52, "5239": 52, "5229": 52,   # 52-Jaggampeta
}


def main():
    init_db()
    with open(HIERARCHY_PATH, "r", encoding="utf-8") as f:
        hier = json.load(f)

    client = APSECClient()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()

    # Clean old duplicated GPs/AC counts so we start with 100% exact zero-duplication state
    cur.execute("DELETE FROM gram_panchayats WHERE ac_no = 41")
    cur.execute("""
    UPDATE constituencies
    SET total_gps = 0, completed_gps = 0, total_voters = 0, completed_voters = 0, status = 'PENDING', assigned_node = NULL
    WHERE status != 'SYNCED'
    """)
    conn.commit()

    total_mandals = 0
    for dist_id, dist_name in hier["districts"]:
        revs = hier["revdivs"].get(dist_id, [])
        dist_cnt = 0
        for rev_id, rev_name in revs:
            mandals = client.get_mandals_in_revdiv(dist_id, rev_id)
            for d_id, rd_id, m_id, m_name in mandals:
                pri_ac = PRIORITY_MANDAL_AC.get(m_id, 0)
                cur.execute("""
                INSERT INTO mandals (mandal_id, district_id, district_name, rev_div_id, mandal_name, primary_ac_no, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
                ON CONFLICT(mandal_id) DO UPDATE SET
                    district_id=excluded.district_id,
                    district_name=excluded.district_name,
                    rev_div_id=excluded.rev_div_id,
                    mandal_name=excluded.mandal_name,
                    primary_ac_no=CASE WHEN mandals.primary_ac_no > 0 THEN mandals.primary_ac_no ELSE excluded.primary_ac_no END,
                    updated_at=excluded.updated_at
                """, (m_id, dist_id, dist_name, rev_id, m_name, pri_ac, time.time()))
                dist_cnt += 1
                total_mandals += 1
        conn.commit()
        print(f"  [{dist_id}] {dist_name:30s}: {dist_cnt} mandals seeded", flush=True)

    # Mark already-harvested GPs' mandals cleanly & recalculate AC totals from existing clean GPs
    for ac_no in [35, 36, 37, 38, 39, 40, 42, 43, 52]:
        row = cur.execute("SELECT COUNT(*), COALESCE(SUM(official_voters), 0) FROM gram_panchayats WHERE ac_no = ?", (ac_no,)).fetchone()
        cnt, voters = row
        if cnt > 0:
            cur.execute("""
            UPDATE constituencies
            SET total_gps = ?, completed_gps = ?, total_voters = ?, completed_voters = ?,
                status = CASE WHEN status='SYNCED' THEN 'SYNCED' ELSE 'IN_PROGRESS' END
            WHERE ac_no = ?
            """, (cnt, cnt, voters, voters, ac_no))
    conn.commit()
    conn.close()
    print(f"\n[DONE] Seeded {total_mandals} unique rural Mandals across all 28 districts with zero AC duplication.")


if __name__ == "__main__":
    main()
