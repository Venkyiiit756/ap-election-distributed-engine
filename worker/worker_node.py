import os
import sys
import time
import json
import csv
import sqlite3
import argparse
import socket
import ssl
import http.client
import re
import urllib.parse
import zipfile
import threading
import concurrent.futures
from collections import deque

sys.stdout.reconfigure(encoding="utf-8")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from core.gdrive_sync import GoogleDriveSync

DB_PATH = os.path.join(BASE_DIR, "coordinator", "registry.sqlite")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
HOST = "sec-ems.ap.gov.in"

OPT_RE = re.compile(r'<option\s+value=["\']?([^"\'>\s]+)["\']?[^>]*>([^<]+)</option>')
CSRF_RE = re.compile(r'name="_csrf"\s+value="([^"]+)"')
TR_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
TD_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)


class APSECClient:
    def __init__(self):
        self.conn = None
        self.csrf = None
        self.cookie = None
        self._init_session()

    def _init_session(self):
        for attempt in range(4):
            try:
                if self.conn:
                    try:
                        self.conn.close()
                    except Exception:
                        pass
                ctx = ssl.create_default_context()
                self.conn = http.client.HTTPSConnection(HOST, 443, timeout=15, context=ctx)
                self.conn.request("GET", "/apsec/rollsHome", headers={"User-Agent": "Mozilla/5.0"})
                resp = self.conn.getresponse()
                body = resp.read().decode("utf-8", errors="ignore")
                cookies = [c.split(";")[0] for k, c in resp.getheaders() if k.lower() == "set-cookie"]
                self.cookie = "; ".join(cookies)
                m = CSRF_RE.search(body)
                self.csrf = m.group(1) if m else None
                if self.csrf:
                    self.post("/apsec/rollsRural", {"localBodiesType": "rural", "sublocalBodiesType": "MPTC"})
                    return
            except Exception:
                time.sleep(1.0 * (attempt + 1))

    def post(self, path, data, ajax=False, retries=4, timeout=15):
        for attempt in range(retries):
            try:
                if not self.conn or not self.csrf:
                    self._init_session()
                self.conn.timeout = timeout
                if self.conn.sock:
                    self.conn.sock.settimeout(timeout)
                payload = dict(data)
                payload["_csrf"] = self.csrf
                hdrs = {
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" if ajax else "application/x-www-form-urlencoded",
                    "Cookie": self.cookie or "",
                    "Connection": "keep-alive",
                }
                if ajax:
                    hdrs["X-CSRF-TOKEN"] = self.csrf or ""
                    hdrs["X-Requested-With"] = "XMLHttpRequest"

                self.conn.request("POST", path, body=urllib.parse.urlencode(payload), headers=hdrs)
                resp = self.conn.getresponse()
                body = resp.read().decode("utf-8", errors="ignore")
                if resp.status == 200:
                    m = CSRF_RE.search(body)
                    if m:
                        self.csrf = m.group(1)
                    return body
                self._init_session()
            except Exception:
                self._init_session()
                time.sleep(0.5 * (attempt + 1))
        return ""

    def get_mandals_in_revdiv(self, dist_id, rev_div_id):
        html = self.post("/apsec/getGPDistrictMandalReport", {"districtId": str(dist_id), "revenueDivisionId": str(rev_div_id)})
        mandals = []
        for d, rd, mid in re.findall(r"urlPostSubmit\('getGPDistrictMandalGPReport',\s*\[[^\]]+\],\s*\['([^']+)',\s*'([^']+)',\s*'([^']+)'\]\)", html):
            lbl_m = re.search(rf"'{mid}'[^>]*>([^<]+)</a>", html)
            mname = lbl_m.group(1).strip() if lbl_m else mid
            mandals.append((d.strip(), rd.strip(), mid.strip(), mname))
        return mandals

    def get_gps_strength(self, dist_id, rev_div_id, mandal_id):
        html = self.post("/apsec/getGPDistrictMandalGPReport", {
            "districtId": str(dist_id),
            "revenueDivisionId": str(rev_div_id),
            "mandalId": str(mandal_id)
        })
        gps = []
        for tr in TR_RE.findall(html):
            tr_clean = re.sub(r'<!--.*?-->', '', tr, flags=re.DOTALL)
            tds = TD_RE.findall(tr_clean)
            if len(tds) < 6:
                continue
            m_id = re.search(r"'getWardDistrictMandalGPReport',\s*\[[^\]]+\],\s*\['[^']+',\s*'[^']+',\s*'[^']+',\s*'([^']+)'\]", tds[1], re.DOTALL)
            if not m_id:
                continue
            gp_id = m_id.group(1).strip()
            gp_name = re.sub(r'<[^>]+>', '', tds[1]).strip()
            try:
                male = int(re.sub(r'<[^>]+>', '', tds[2]).strip())
                female = int(re.sub(r'<[^>]+>', '', tds[3]).strip())
                other = int(re.sub(r'<[^>]+>', '', tds[4]).strip())
                total = int(re.sub(r'<[^>]+>', '', tds[5]).strip())
            except ValueError:
                male = female = other = total = 0
            gps.append({
                "gp_id": gp_id, "gp_name": gp_name,
                "male": male, "female": female, "other": other, "total": total
            })
        return gps

    def get_wards_strength(self, dist_id, rev_div_id, mandal_id, gp_id):
        html = self.post("/apsec/getWardDistrictMandalGPReport", {
            "districtId": str(dist_id),
            "revenueDivisionId": str(rev_div_id),
            "mandalId": str(mandal_id),
            "gpId": str(gp_id)
        }, retries=1, timeout=6)
        wards = []
        for tr in TR_RE.findall(html):
            tds = [re.sub(r'<[^>]+>', '', td).strip() for td in TD_RE.findall(tr)]
            if len(tds) >= 10 and tds[0].isdigit():
                try:
                    wards.append({
                        "ward_no": tds[5],
                        "male": int(tds[6]),
                        "female": int(tds[7]),
                        "other": int(tds[8]),
                        "total": int(tds[9])
                    })
                except ValueError:
                    pass
        return wards

    def get_mptcs_for_mandal(self, dist_id, rev_div_id, mandal_id, mandal_name):
        html = self.post("/apsec/getMPTCByDistrictMandalData", {"districtId": str(dist_id), "mandalId": str(mandal_id)}, ajax=True)
        mptcs = [(mid.strip(), mn.strip()) for mid, mn in OPT_RE.findall(html) if mid.strip() != "0"]
        mappings = []
        for mptc_id, mptc_name in mptcs:
            res_html = self.post("/apsec/getMPTCWiseDataTable", {
                "localBodiesType": "rural",
                "sublocalBodiesType": "MPTC",
                "electionAgent": "105",
                "districtId": str(dist_id),
                "revenueDivision": str(rev_div_id),
                "mandalId": str(mandal_id),
                "mptcId": str(mptc_id)
            })
            matches = re.findall(r"popupData\([^,]+,\s*\[[^\]]+\],\s*\['[^']+','([^']+)','([^']+)','([^']+)'\]\)", res_html)
            td_rows = re.findall(r'<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*><a[^>]*popupData', res_html, re.DOTALL)
            for idx, (wards, ac_id, gp_id) in enumerate(matches):
                gp_name = td_rows[idx][0].strip() if idx < len(td_rows) else ""
                mappings.append({
                    "district_id": str(dist_id),
                    "mandal_id": str(mandal_id),
                    "mandal_name": mandal_name,
                    "mptc_id": str(mptc_id),
                    "mptc_name": mptc_name,
                    "gp_id": str(gp_id),
                    "gp_name": gp_name,
                    "wards_range": wards.strip(),
                    "ac_no": int(ac_id) if ac_id.isdigit() else 0
                })
        return mappings


class WorkerNode:
    def __init__(self, node_id, workers_count=2):
        self.node_id = node_id
        self.workers_count = max(1, workers_count)
        self.hostname = socket.gethostname()
        try:
            self.ip_address = socket.gethostbyname(self.hostname)
        except Exception:
            self.ip_address = "127.0.0.1"
        self.current_ac = None
        self.db_lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.voter_events = deque()  # (timestamp, count) over rolling 30s window
        self.tls = threading.local()

    def get_client(self):
        if not hasattr(self.tls, "client"):
            self.tls.client = APSECClient()
        return self.tls.client

    def record_voters(self, count):
        now = time.time()
        with self.rate_lock:
            if count > 0:
                self.voter_events.append((now, count))
            cutoff = now - 30.0
            while self.voter_events and self.voter_events[0][0] < cutoff:
                self.voter_events.popleft()
            total = sum(v for _, v in self.voter_events)
            span = max(5.0, (now - self.voter_events[0][0]) if self.voter_events else 5.0)
            return total / min(30.0, span)

    def register_heartbeat(self, rate=None):
        if rate is None:
            rate = self.record_voters(0)
        try:
            with self.db_lock:
                conn = sqlite3.connect(DB_PATH, timeout=30)
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO worker_nodes (node_id, hostname, ip_address, workers_count, last_heartbeat, current_ac, rate_voters_per_sec, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                ON CONFLICT(node_id) DO UPDATE SET
                    workers_count=excluded.workers_count,
                    last_heartbeat=excluded.last_heartbeat,
                    current_ac=excluded.current_ac,
                    rate_voters_per_sec=excluded.rate_voters_per_sec,
                    status='ACTIVE'
                """, (self.node_id, self.hostname, self.ip_address, self.workers_count, time.time(), self.current_ac, round(rate, 1)))
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"[Heartbeat Error] {e}", flush=True)

    def release_stalled_mandals(self):
        with self.db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.execute("UPDATE mandals SET status='PENDING', assigned_node=NULL WHERE status='IN_PROGRESS'")
            conn.commit()
            conn.close()

    def claim_next_mandal(self):
        with self.db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cur = conn.cursor()
            now = time.time()
            cur.execute("""
            SELECT mandal_id, district_id, district_name, rev_div_id, mandal_name, primary_ac_no
            FROM mandals
            WHERE status = 'PENDING' OR (status = 'IN_PROGRESS' AND updated_at < ?)
            ORDER BY
                CASE
                    WHEN primary_ac_no IN (35, 36, 37, 52, 40) THEN 0
                    WHEN primary_ac_no > 0 THEN 1
                    ELSE 2
                END,
                district_id ASC,
                mandal_name ASC
            LIMIT 1
            """, (now - 300,))
            row = cur.fetchone()
            if row:
                m_id, d_id, d_name, rd_id, m_name, pri_ac = row
                cur.execute("UPDATE mandals SET status = 'IN_PROGRESS', assigned_node = ?, updated_at = ? WHERE mandal_id = ?", (self.node_id, now, m_id))
                conn.commit()
                conn.close()
                return m_id, d_id, d_name, rd_id, m_name, pri_ac
            conn.close()
            return None, None, None, None, None, None

    def rollup_constituencies(self, touched_acs):
        with self.db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cur = conn.cursor()
            for ac_no in touched_acs:
                if not ac_no:
                    continue
                row = cur.execute("SELECT COUNT(*), COALESCE(SUM(official_voters), 0) FROM gram_panchayats WHERE ac_no = ?", (ac_no,)).fetchone()
                cnt, voters = row
                pending_m = cur.execute("SELECT COUNT(*) FROM mandals WHERE primary_ac_no = ? AND status != 'COMPLETED'", (ac_no,)).fetchone()[0]
                total_m = cur.execute("SELECT COUNT(*) FROM mandals WHERE primary_ac_no = ?", (ac_no,)).fetchone()[0]
                done_ac = (total_m > 0 and pending_m == 0)
                cur.execute("""
                UPDATE constituencies
                SET total_gps = ?, completed_gps = ?, total_voters = ?, completed_voters = ?,
                    status = CASE
                        WHEN status = 'SYNCED' THEN 'SYNCED'
                        WHEN ? THEN 'COMPLETED'
                        ELSE 'IN_PROGRESS'
                    END,
                    assigned_node = ?,
                    updated_at = ?
                WHERE ac_no = ?
                """, (cnt, cnt, voters, voters, 1 if done_ac else 0, self.node_id, time.time(), ac_no))
            conn.commit()
            conn.close()

    def export_ac_bundle(self, ac_no):
        with self.db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cur = conn.cursor()
            ac_row = cur.execute("SELECT ac_slug FROM constituencies WHERE ac_no = ?", (ac_no,)).fetchone()
            if not ac_row:
                conn.close()
                return
            ac_slug = ac_row[0]
            gp_rows = cur.execute("SELECT ac_no, mandal_id, mandal_name, gp_id, gp_name_en, male_voters, female_voters, other_voters, official_voters, wards_count FROM gram_panchayats WHERE ac_no = ? ORDER BY mandal_name, gp_name_en", (ac_no,)).fetchall()
            ward_rows = cur.execute("SELECT w.ac_no, w.mandal_id, w.gp_id, g.gp_name_en, w.ward_no, w.male_voters, w.female_voters, w.other_voters, w.total_voters FROM ward_strengths w LEFT JOIN gram_panchayats g ON w.gp_id = g.gp_id WHERE w.ac_no = ? ORDER BY w.gp_id, CAST(w.ward_no AS INTEGER)", (ac_no,)).fetchall()
            mptc_rows = cur.execute("SELECT ac_no, district_id, mandal_id, mandal_name, mptc_id, mptc_name, gp_id, gp_name, wards_range FROM mptc_mappings WHERE ac_no = ? ORDER BY mandal_name, mptc_name", (ac_no,)).fetchall()
            conn.close()

        out_dir = os.path.join(EXPORTS_DIR, ac_slug)
        os.makedirs(out_dir, exist_ok=True)
        gp_csv = os.path.join(out_dir, f"{ac_slug}_GP_Voter_Strength_2026.csv")
        ward_csv = os.path.join(out_dir, f"{ac_slug}_Ward_Voter_Strength_2026.csv")
        mptc_csv = os.path.join(out_dir, f"{ac_slug}_MPTC_Ward_Mapping_2026.csv")

        with open(gp_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["AC_No", "Mandal_ID", "Mandal_Name", "GP_ID", "GP_Name", "Male_Voters", "Female_Voters", "Other_Voters", "Total_Voters", "Wards_Count"])
            w.writerows(gp_rows)
        with open(ward_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["AC_No", "Mandal_ID", "GP_ID", "GP_Name", "Ward_No", "Male_Voters", "Female_Voters", "Other_Voters", "Total_Voters"])
            w.writerows(ward_rows)
        with open(mptc_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["AC_No", "District_ID", "Mandal_ID", "Mandal_Name", "MPTC_ID", "MPTC_Name", "GP_ID", "GP_Name", "Wards_Range"])
            w.writerows(mptc_rows)

        zip_path = os.path.join(EXPORTS_DIR, f"{ac_slug}_APSEC_GP_MPTC_2026.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in [gp_csv, ward_csv, mptc_csv]:
                zf.write(p, os.path.basename(p))
        return zip_path

    def process_mandal(self, m_id, d_id, d_name, rd_id, m_name, pri_ac, thread_idx):
        client = self.get_client()
        print(f"[T{thread_idx}] Harvesting Mandal {m_name} ({m_id}) | Dist {d_id} ({d_name})", flush=True)

        mptcs = client.get_mptcs_for_mandal(d_id, rd_id, m_id, m_name)
        gp_to_ac = {}
        mandal_ac = pri_ac or 0
        for mp in mptcs:
            if mp["ac_no"] > 0:
                gp_to_ac[mp["gp_id"]] = mp["ac_no"]
                if mandal_ac == 0:
                    mandal_ac = mp["ac_no"]

        if mandal_ac > 0:
            self.current_ac = mandal_ac

        gps = client.get_gps_strength(d_id, rd_id, m_id)

        with self.db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cur = conn.cursor()
            for mp in mptcs:
                ac_val = mp["ac_no"] or mandal_ac
                cur.execute("""
                INSERT INTO mptc_mappings (district_id, mandal_id, mandal_name, mptc_id, mptc_name, gp_id, gp_name, wards_range, ac_no, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mandal_id, mptc_id, gp_id, wards_range) DO UPDATE SET
                    mptc_name=excluded.mptc_name,
                    gp_name=excluded.gp_name,
                    ac_no=excluded.ac_no,
                    updated_at=excluded.updated_at
                """, (mp["district_id"], mp["mandal_id"], mp["mandal_name"], mp["mptc_id"], mp["mptc_name"], mp["gp_id"], mp["gp_name"], mp["wards_range"], ac_val, time.time()))
            conn.commit()
            conn.close()

        mandal_voters = 0
        touched_acs = set()
        for gp in gps:
            gp_id = gp["gp_id"]
            ac_no = gp_to_ac.get(gp_id, mandal_ac)
            if ac_no:
                touched_acs.add(ac_no)

            wards = client.get_wards_strength(d_id, rd_id, m_id, gp_id)
            mandal_voters += gp["total"]

            with self.db_lock:
                conn = sqlite3.connect(DB_PATH, timeout=30)
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO gram_panchayats (gp_id, ac_no, district_id, rev_div_id, mandal_id, mandal_name, gp_name_en, official_voters, harvested_voters, male_voters, female_voters, other_voters, wards_count, dpo_confirmed, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'COMPLETED', ?)
                ON CONFLICT(gp_id) DO UPDATE SET
                    ac_no=excluded.ac_no,
                    district_id=excluded.district_id,
                    rev_div_id=excluded.rev_div_id,
                    mandal_id=excluded.mandal_id,
                    mandal_name=excluded.mandal_name,
                    gp_name_en=excluded.gp_name_en,
                    official_voters=excluded.official_voters,
                    harvested_voters=excluded.harvested_voters,
                    male_voters=excluded.male_voters,
                    female_voters=excluded.female_voters,
                    other_voters=excluded.other_voters,
                    wards_count=excluded.wards_count,
                    status='COMPLETED',
                    updated_at=excluded.updated_at
                """, (gp_id, ac_no, d_id, rd_id, m_id, m_name, gp["gp_name"], gp["total"], gp["total"], gp["male"], gp["female"], gp["other"], len(wards), time.time()))

                for w in wards:
                    cur.execute("""
                    INSERT INTO ward_strengths (ac_no, mandal_id, gp_id, ward_no, male_voters, female_voters, other_voters, total_voters, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(gp_id, ward_no) DO UPDATE SET
                        ac_no=excluded.ac_no,
                        male_voters=excluded.male_voters,
                        female_voters=excluded.female_voters,
                        other_voters=excluded.other_voters,
                        total_voters=excluded.total_voters,
                        updated_at=excluded.updated_at
                    """, (ac_no, m_id, gp_id, w["ward_no"], w["male"], w["female"], w["other"], w["total"], time.time()))
                conn.commit()
                conn.close()

            rate = self.record_voters(gp["total"])
            self.register_heartbeat(rate=rate)

        with self.db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.execute("""
            UPDATE mandals
            SET status = 'COMPLETED', primary_ac_no = CASE WHEN primary_ac_no=0 THEN ? ELSE primary_ac_no END,
                total_gps = ?, total_voters = ?, updated_at = ?
            WHERE mandal_id = ?
            """, (mandal_ac, len(gps), mandal_voters, time.time(), m_id))
            conn.commit()
            conn.close()

        self.rollup_constituencies(touched_acs)
        for ac in touched_acs:
            self.export_ac_bundle(ac)

        print(f"[T{thread_idx}] [OK] {m_name} -> AC-{mandal_ac} | {len(gps)} GPs | {mandal_voters:,} voters | {len(mptcs)} MPTC maps", flush=True)

    def worker_loop(self, thread_idx):
        while True:
            m_id, d_id, d_name, rd_id, m_name, pri_ac = self.claim_next_mandal()
            if not m_id:
                time.sleep(15)
                continue
            try:
                self.process_mandal(m_id, d_id, d_name, rd_id, m_name, pri_ac, thread_idx)
            except Exception as e:
                print(f"[T{thread_idx} Error on {m_name}] {e}", flush=True)
                time.sleep(2)

    def run(self):
        print("===========================================================", flush=True)
        print(f"[Node {self.node_id}] Parallel Mandal Worker ({self.workers_count} threads) Active on {self.hostname}", flush=True)
        print("===========================================================", flush=True)
        self.release_stalled_mandals()
        self.register_heartbeat(rate=0.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers_count) as ex:
            for idx in range(1, self.workers_count + 1):
                ex.submit(self.worker_loop, idx)
            while True:
                time.sleep(15)
                self.register_heartbeat()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed APSEC Zero-Duplication GP & MPTC Worker")
    parser.add_argument("--node-id", type=str, default=f"node-{socket.gethostname().lower()}")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    node = WorkerNode(args.node_id, args.workers)
    node.run()
