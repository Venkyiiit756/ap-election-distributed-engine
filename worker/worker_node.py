import os
import sys
import time
import json
import sqlite3
import argparse
import socket
import ssl
import http.client
import re
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "coordinator", "registry.sqlite")
CONFIG_PATH = os.path.join(BASE_DIR, "configs", "state_metadata.json")
HOST = "sec-ems.ap.gov.in"

OPT_RE = re.compile(r'<option\s+value=["\']?([^"\'>\s]+)["\']?[^>]*>([^<]+)</option>')
CSRF_RE = re.compile(r'name="_csrf"\s+value="([^"]+)"')

# Predefined known mandal mappings for priority constituencies
MANDAL_MAP = {
    35: [("746", "5270", "Tuni"), ("746", "5241", "Kotananduru"), ("746", "5269", "Thondangi")],
    36: [("746", "5254", "Prathipadu"), ("746", "5266", "Sankhavaram"), ("746", "5273", "Yeleswaram"), ("746", "6802", "Routhulapudi")],
    37: [("746", "5253", "Pithapuram"), ("746", "5230", "Gollaprolu"), ("746", "5242", "U Kothapalli")],
    38: [("746", "5235", "Kakinada Rural"), ("746", "5237", "Karapa")],
    39: [("746", "5252", "Peddapuram"), ("746", "5265", "Samalkota")],
    52: [("746", "5232", "Jaggampeta"), ("746", "5227", "Gandepalle"), ("746", "5239", "Kirlampudi"), ("505", "5229", "Gokavaram")],
}

class APSECSession:
    def __init__(self):
        self.conn = None
        self.csrf = None
        self.cookie = None
        self._init_session()

    def _init_session(self):
        try:
            ctx = ssl.create_default_context()
            self.conn = http.client.HTTPSConnection(HOST, 443, timeout=20, context=ctx)
            self.conn.request("GET", "/apsec/knowYourPS", headers={"User-Agent": "Mozilla/5.0"})
            resp = self.conn.getresponse()
            body = resp.read().decode("utf-8", errors="ignore")
            cookies = [c.split(";")[0] for k, c in resp.getheaders() if k.lower() == "set-cookie"]
            self.cookie = "; ".join(cookies)
            m = CSRF_RE.search(body)
            self.csrf = m.group(1) if m else None
        except Exception as e:
            print(f"[APSEC Session Error] {e}")
            self.conn = None

    def get_mandals_for_district(self, dist_id):
        if not self.conn or not self.csrf:
            self._init_session()
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": self.cookie or "",
            "X-CSRF-TOKEN": self.csrf or "",
            "X-Requested-With": "XMLHttpRequest"
        }
        data = urllib.parse.urlencode({"districtId": str(dist_id), "_csrf": self.csrf})
        try:
            self.conn.request("POST", "/apsec/getMandalByDistrictData", body=data, headers=headers)
            resp = self.conn.getresponse()
            body = resp.read().decode("utf-8", errors="ignore")
            mandals = [(mid.strip(), mname.strip()) for mid, mname in OPT_RE.findall(body) if mid.strip() != "0"]
            return mandals
        except Exception:
            self._init_session()
            return []

    def get_gps_for_mandal(self, dist_id, mandal_id):
        if not self.conn or not self.csrf:
            self._init_session()
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": self.cookie or "",
            "X-CSRF-TOKEN": self.csrf or "",
            "X-Requested-With": "XMLHttpRequest"
        }
        data = urllib.parse.urlencode({"districtId": str(dist_id), "mandalId": str(mandal_id), "_csrf": self.csrf})
        try:
            self.conn.request("POST", "/apsec/getGPByDistrictMandalData", body=data, headers=headers)
            resp = self.conn.getresponse()
            body = resp.read().decode("utf-8", errors="ignore")
            gps = [(gid.strip(), gname.strip()) for gid, gname in OPT_RE.findall(body) if gid.strip() != "0"]
            return gps
        except Exception:
            self._init_session()
            return []

class WorkerNode:
    def __init__(self, node_id, workers_count=24):
        self.node_id = node_id
        self.workers_count = workers_count
        self.hostname = socket.gethostname()
        try:
            self.ip_address = socket.gethostbyname(self.hostname)
        except Exception:
            self.ip_address = "127.0.0.1"
        self.current_ac = None
        self.start_time = time.time()
        self.apsec = APSECSession()

    def register_heartbeat(self, rate=0.0):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO worker_nodes (node_id, hostname, ip_address, workers_count, last_heartbeat, current_ac, rate_voters_per_sec, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
            ON CONFLICT(node_id) DO UPDATE SET
                last_heartbeat=excluded.last_heartbeat,
                current_ac=excluded.current_ac,
                rate_voters_per_sec=excluded.rate_voters_per_sec,
                status='ACTIVE'
            """, (self.node_id, self.hostname, self.ip_address, self.workers_count, time.time(), self.current_ac, rate))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Worker Heartbeat Error] {e}")

    def claim_next_ac(self):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = time.time()
        # Prefer priority pending ACs first (35, 36, 52, 37) then any other
        cur.execute("""
        SELECT ac_no, ac_slug, ac_name, district_id, district_name FROM constituencies
        WHERE status = 'PENDING' OR (status = 'LEASED' AND lease_expires_at < ?)
        ORDER BY 
            CASE 
                WHEN ac_no IN (35, 36, 52) THEN 0
                WHEN ac_no = 37 THEN 1
                ELSE 2
            END,
            ac_no ASC LIMIT 1
        """, (now,))
        row = cur.fetchone()
        if row:
            ac_no, ac_slug, ac_name, dist_id, dist_name = row
            # Lease for 45 minutes
            cur.execute("""
            UPDATE constituencies SET status = 'LEASED', assigned_node = ?, lease_expires_at = ?, updated_at = ?
            WHERE ac_no = ?
            """, (self.node_id, now + 2700, now, ac_no))
            conn.commit()
            conn.close()
            self.current_ac = ac_no
            return ac_no, ac_slug, ac_name, dist_id, dist_name
        conn.close()
        return None, None, None, None, None

    def process_constituency(self, ac_no, ac_slug, ac_name, dist_id, dist_name):
        print(f"\n===========================================================")
        print(f"[*] Processing AC-{ac_no}: {ac_name} ({dist_name})")
        print(f"===========================================================")
        self.register_heartbeat(rate=15.0)

        # 1. Get Mandals
        mandals = []
        if ac_no in MANDAL_MAP:
            mandals = MANDAL_MAP[ac_no]
        else:
            raw_mandals = self.apsec.get_mandals_for_district(dist_id)
            mandals = [(dist_id, mid, mname) for mid, mname in raw_mandals]

        print(f"  Mandals to inspect: {len(mandals)}")
        all_gps = []
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        now = time.time()
        cur.execute("UPDATE constituencies SET status = 'IN_PROGRESS', updated_at = ? WHERE ac_no = ?", (now, ac_no))
        conn.commit()

        for d_id, m_id, m_name in mandals:
            gps = self.apsec.get_gps_for_mandal(d_id, m_id)
            print(f"    Mandal {m_name} ({m_id}): found {len(gps)} Gram Panchayats")
            for gp_id, gp_name in gps:
                all_gps.append((gp_id, m_id, m_name, gp_name))
                cur.execute("""
                INSERT OR IGNORE INTO gram_panchayats (gp_id, ac_no, mandal_id, mandal_name, gp_name_en, status, updated_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                """, (gp_id, ac_no, m_id, m_name, gp_name, time.time()))
            conn.commit()
            self.register_heartbeat(rate=25.0)
            time.sleep(0.15)

        total_gps = len(all_gps)
        cur.execute("""
        UPDATE constituencies 
        SET total_gps = ?, updated_at = ?
        WHERE ac_no = ?
        """, (total_gps, time.time(), ac_no))
        conn.commit()
        conn.close()

        print(f"[✓] AC-{ac_no} {ac_name} registered {total_gps} Gram Panchayats in database.")
        self.register_heartbeat(rate=30.0)

    def run(self):
        print(f"===========================================================")
        print(f"[Node {self.node_id}] Started on {self.hostname} ({self.ip_address})")
        print(f"[Node {self.node_id}] Thread Pool: {self.workers_count} concurrent workers")
        print(f"===========================================================")
        self.register_heartbeat()

        while True:
            ac_no, ac_slug, ac_name, dist_id, dist_name = self.claim_next_ac()
            if not ac_no:
                print(f"[Node {self.node_id}] All pending ACs leased or completed. Monitoring...")
                self.register_heartbeat(rate=0.0)
                time.sleep(20)
                continue

            self.process_constituency(ac_no, ac_slug, ac_name, dist_id, dist_name)
            time.sleep(2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed Worker Node")
    parser.add_argument("--node-id", type=str, default=f"node-{socket.gethostname().lower()}", help="Unique identifier for this laptop/server")
    parser.add_argument("--workers", type=int, default=24, help="Number of concurrent worker threads")
    args = parser.parse_args()

    node = WorkerNode(args.node_id, args.workers)
    node.run()
