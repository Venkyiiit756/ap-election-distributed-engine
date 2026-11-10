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

sys.stdout.reconfigure(encoding="utf-8")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from core.gdrive_sync import GoogleDriveSync

DB_PATH = os.path.join(BASE_DIR, "coordinator", "registry.sqlite")
HIERARCHY_PATH = os.path.join(BASE_DIR, "configs", "apsec_district_hierarchy.json")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
HOST = "sec-ems.ap.gov.in"

OPT_RE = re.compile(r'<option\s+value=["\']?([^"\'>\s]+)["\']?[^>]*>([^<]+)</option>')
CSRF_RE = re.compile(r'name="_csrf"\s+value="([^"]+)"')
TR_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
TD_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)

# Exact (dist_id, rev_div_id, mandal_id, mandal_name) mappings for Kakinada LS & East Godavari / Konaseema ACs
AC_MANDAL_MAP = {
    35: [("746", "746002", "5270", "Tuni"), ("746", "746002", "5241", "Kotananduru"), ("746", "746002", "5269", "Thondangi")],
    36: [("746", "746002", "5254", "Prathipadu"), ("746", "746002", "5266", "Sankhavaram"), ("746", "746002", "5273", "Yeleswaram"), ("746", "746002", "6802", "Routhulapudi")],
    37: [("746", "746001", "5253", "Pithapuram"), ("746", "746001", "5230", "Gollaprolu"), ("746", "746001", "5242", "U Kothapalli")],
    38: [("746", "746001", "5235", "Kakinada Rural"), ("746", "746001", "5237", "Karapa")],
    39: [("746", "746002", "5252", "Peddapuram"), ("746", "746001", "5265", "Samalkota")],
    40: [("505", "505001", "5223", "Anaparthi"), ("505", "505001", "5225", "Biccavolu"), ("505", "505001", "5260", "Rangampeta"), ("746", "746001", "5251", "Pedapudi")],
    52: [("746", "746002", "5232", "Jaggampeta"), ("746", "746002", "5227", "Gandepalle"), ("746", "746002", "5239", "Kirlampudi"), ("505", "505001", "5229", "Gokavaram")],
}


class APSECClient:
    def __init__(self):
        self.conn = None
        self.csrf = None
        self.cookie = None
        self._init_session()

    def _init_session(self):
        for attempt in range(5):
            try:
                ctx = ssl.create_default_context()
                self.conn = http.client.HTTPSConnection(HOST, 443, timeout=25, context=ctx)
                self.conn.request("GET", "/apsec/rollsHome", headers={"User-Agent": "Mozilla/5.0"})
                resp = self.conn.getresponse()
                body = resp.read().decode("utf-8", errors="ignore")
                cookies = [c.split(";")[0] for k, c in resp.getheaders() if k.lower() == "set-cookie"]
                self.cookie = "; ".join(cookies)
                m = CSRF_RE.search(body)
                self.csrf = m.group(1) if m else None
                if self.csrf:
                    # Also initialize MPTC rolls session state
                    self.post("/apsec/rollsRural", {"localBodiesType": "rural", "sublocalBodiesType": "MPTC"})
                    return
            except Exception as e:
                print(f"[APSEC Session Retry {attempt+1}] {e}", flush=True)
                time.sleep(1.5 * (attempt + 1))

    def post(self, path, data, ajax=False):
        for attempt in range(4):
            try:
                if not self.conn or not self.csrf:
                    self._init_session()
                payload = dict(data)
                payload["_csrf"] = self.csrf
                hdrs = {
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" if ajax else "application/x-www-form-urlencoded",
                    "Cookie": self.cookie or "",
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

    def get_rev_divs(self, dist_id):
        html = self.post("/apsec/getRevenueDivisionDataAjaxWithRevenueId", {"districtId": str(dist_id)}, ajax=True)
        return [(v.strip(), n.strip()) for v, n in OPT_RE.findall(html) if v.strip() != "0"]

    def get_mandals_in_revdiv(self, dist_id, rev_div_id):
        html = self.post("/apsec/getGPDistrictMandalReport", {"districtId": str(dist_id), "revenueDivisionId": str(rev_div_id)})
        mandals = []
        for d, rd, mid in re.findall(r"urlPostSubmit\('getGPDistrictMandalGPReport',\s*\[[^\]]+\],\s*\['([^']+)',\s*'([^']+)',\s*'([^']+)'\]\)", html):
            # Try to find label
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
        })
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
    def __init__(self, node_id, workers_count=24):
        self.node_id = node_id
        self.workers_count = workers_count
        self.hostname = socket.gethostname()
        try:
            self.ip_address = socket.gethostbyname(self.hostname)
        except Exception:
            self.ip_address = "127.0.0.1"
        self.current_ac = None
        self.client = APSECClient()
        self.gdrive = GoogleDriveSync()
        self.hierarchy = {}
        if os.path.exists(HIERARCHY_PATH):
            with open(HIERARCHY_PATH, "r", encoding="utf-8") as f:
                self.hierarchy = json.load(f)

    def register_heartbeat(self, rate=0.0):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO worker_nodes (node_id, hostname, ip_address, workers_count, last_heartbeat, current_ac, rate_voters_per_sec, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
            ON CONFLICT(node_id) DO UPDATE SET
                last_heartbeat=excluded.last_heartbeat,
                current_ac=excluded.current_ac,
                rate_voters_per_sec=excluded.rate_voters_per_sec,
                status='ACTIVE'
            """, (self.node_id, self.hostname, self.ip_address, self.workers_count, time.time(), self.current_ac, round(rate, 1)))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Heartbeat Error] {e}", flush=True)

    def claim_next_ac(self):
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cur = conn.cursor()
        now = time.time()
        cur.execute("""
        SELECT ac_no, ac_slug, ac_name, district_id, district_name FROM constituencies
        WHERE status = 'PENDING' OR (status = 'LEASED' AND lease_expires_at < ?)
        ORDER BY
            CASE
                WHEN ac_no IN (35, 36, 37, 52) THEN 0
                WHEN ac_no IN (38, 39, 40, 41) THEN 1
                ELSE 2
            END,
            ac_no ASC LIMIT 1
        """, (now,))
        row = cur.fetchone()
        if row:
            ac_no, ac_slug, ac_name, dist_id, dist_name = row
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

    def get_mandals_for_ac(self, ac_no, dist_id):
        if ac_no in AC_MANDAL_MAP:
            return AC_MANDAL_MAP[ac_no]
        # Otherwise discover mandals via district revdivs
        revs = self.hierarchy.get("revdivs", {}).get(str(dist_id), [])
        if not revs:
            revs = self.client.get_rev_divs(dist_id)
        mandals = []
        seen = set()
        for rev_id, _ in revs:
            for d_id, rd_id, m_id, m_name in self.client.get_mandals_in_revdiv(dist_id, rev_id):
                if m_id not in seen:
                    seen.add(m_id)
                    mandals.append((d_id, rd_id, m_id, m_name))
        return mandals

    def export_ac_bundle(self, ac_no, ac_slug, gp_rows, ward_rows, mptc_rows):
        out_dir = os.path.join(EXPORTS_DIR, ac_slug)
        os.makedirs(out_dir, exist_ok=True)

        gp_csv = os.path.join(out_dir, f"{ac_slug}_GP_Voter_Strength_2026.csv")
        with open(gp_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["AC_No", "Mandal_ID", "Mandal_Name", "GP_ID", "GP_Name", "Male_Voters", "Female_Voters", "Other_Voters", "Total_Voters", "Wards_Count"])
            w.writerows(gp_rows)

        ward_csv = os.path.join(out_dir, f"{ac_slug}_Ward_Voter_Strength_2026.csv")
        with open(ward_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["AC_No", "Mandal_ID", "GP_ID", "GP_Name", "Ward_No", "Male_Voters", "Female_Voters", "Other_Voters", "Total_Voters"])
            w.writerows(ward_rows)

        mptc_csv = os.path.join(out_dir, f"{ac_slug}_MPTC_Ward_Mapping_2026.csv")
        with open(mptc_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["AC_No", "District_ID", "Mandal_ID", "Mandal_Name", "MPTC_ID", "MPTC_Name", "GP_ID", "GP_Name", "Wards_Range"])
            w.writerows(mptc_rows)

        zip_path = os.path.join(EXPORTS_DIR, f"{ac_slug}_APSEC_GP_MPTC_2026.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in [gp_csv, ward_csv, mptc_csv]:
                zf.write(p, os.path.basename(p))
        return zip_path

    def process_constituency(self, ac_no, ac_slug, ac_name, dist_id, dist_name):
        t0 = time.time()
        print(f"\n[*] Processing AC-{ac_no}: {ac_name} (Dist {dist_id}: {dist_name})", flush=True)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("UPDATE constituencies SET status = 'IN_PROGRESS', updated_at = ? WHERE ac_no = ?", (time.time(), ac_no))
        conn.commit()
        conn.close()

        mandals = self.get_mandals_for_ac(ac_no, dist_id)
        print(f"  Found {len(mandals)} mandals to harvest.", flush=True)

        gp_export_rows = []
        ward_export_rows = []
        mptc_export_rows = []
        total_gps_cnt = 0
        completed_gps_cnt = 0
        total_voters_cnt = 0

        for d_id, rd_id, m_id, m_name in mandals:
            # 1. Harvest GP Voter Strengths
            gps = self.client.get_gps_strength(d_id, rd_id, m_id)
            total_gps_cnt += len(gps)
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cur = conn.cursor()
            cur.execute("UPDATE constituencies SET total_gps = ? WHERE ac_no = ?", (total_gps_cnt, ac_no))

            for gp in gps:
                gp_id = gp["gp_id"]
                wards = self.client.get_wards_strength(d_id, rd_id, m_id, gp_id)
                wards_count = len(wards)
                completed_gps_cnt += 1
                total_voters_cnt += gp["total"]

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
                """, (gp_id, ac_no, d_id, rd_id, m_id, m_name, gp["gp_name"], gp["total"], gp["total"], gp["male"], gp["female"], gp["other"], wards_count, time.time()))

                for w in wards:
                    cur.execute("""
                    INSERT INTO ward_strengths (ac_no, mandal_id, gp_id, ward_no, male_voters, female_voters, other_voters, total_voters, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(gp_id, ward_no) DO UPDATE SET
                        male_voters=excluded.male_voters,
                        female_voters=excluded.female_voters,
                        other_voters=excluded.other_voters,
                        total_voters=excluded.total_voters,
                        updated_at=excluded.updated_at
                    """, (ac_no, m_id, gp_id, w["ward_no"], w["male"], w["female"], w["other"], w["total"], time.time()))
                    ward_export_rows.append([ac_no, m_id, gp_id, gp["gp_name"], w["ward_no"], w["male"], w["female"], w["other"], w["total"]])

                gp_export_rows.append([ac_no, m_id, m_name, gp_id, gp["gp_name"], gp["male"], gp["female"], gp["other"], gp["total"], wards_count])

                # Live telemetry update every GP
                cur.execute("""
                UPDATE constituencies
                SET completed_gps = ?, completed_voters = ?, total_voters = ?, updated_at = ?
                WHERE ac_no = ?
                """, (completed_gps_cnt, total_voters_cnt, total_voters_cnt, time.time(), ac_no))
                conn.commit()

                elapsed = max(0.5, time.time() - t0)
                self.register_heartbeat(rate=total_voters_cnt / elapsed)

            # 2. Harvest MPTC -> GP -> Ward mappings for this Mandal
            mptcs = self.client.get_mptcs_for_mandal(d_id, rd_id, m_id, m_name)
            for mp in mptcs:
                cur.execute("""
                INSERT INTO mptc_mappings (district_id, mandal_id, mandal_name, mptc_id, mptc_name, gp_id, gp_name, wards_range, ac_no, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mandal_id, mptc_id, gp_id, wards_range) DO UPDATE SET
                    mptc_name=excluded.mptc_name,
                    gp_name=excluded.gp_name,
                    ac_no=excluded.ac_no,
                    updated_at=excluded.updated_at
                """, (mp["district_id"], mp["mandal_id"], mp["mandal_name"], mp["mptc_id"], mp["mptc_name"], mp["gp_id"], mp["gp_name"], mp["wards_range"], mp["ac_no"] or ac_no, time.time()))
                mptc_export_rows.append([mp["ac_no"] or ac_no, mp["district_id"], mp["mandal_id"], mp["mandal_name"], mp["mptc_id"], mp["mptc_name"], mp["gp_id"], mp["gp_name"], mp["wards_range"]])
            conn.commit()
            conn.close()
            print(f"    Mandal {m_name}: {len(gps)} GPs, {len(mptcs)} MPTC mappings, {total_voters_cnt:,} cumulative voters.", flush=True)

        zip_path = self.export_ac_bundle(ac_no, ac_slug, gp_export_rows, ward_export_rows, mptc_export_rows)
        fid, gurl = self.gdrive.upload_constituency_archive(zip_path)
        new_status = "SYNCED" if gurl else "COMPLETED"
        conn = sqlite3.connect(DB_PATH, timeout=30)
        if gurl:
            conn.execute("UPDATE constituencies SET status = ?, gdrive_url = COALESCE(gdrive_url, ?), updated_at = ? WHERE ac_no = ?", (new_status, gurl, time.time(), ac_no))
        else:
            conn.execute("UPDATE constituencies SET status = ?, updated_at = ? WHERE ac_no = ?", (new_status, time.time(), ac_no))
        conn.commit()
        conn.close()
        print(f"[DONE] AC-{ac_no} {ac_name}: {completed_gps_cnt} GPs, {len(ward_export_rows)} Wards, {len(mptc_export_rows)} MPTC maps -> {zip_path} | GDrive: {gurl}", flush=True)

    def run(self):
        print("===========================================================", flush=True)
        print(f"[Node {self.node_id}] Started on {self.hostname} ({self.ip_address})", flush=True)
        print("===========================================================", flush=True)
        self.register_heartbeat()

        while True:
            ac_no, ac_slug, ac_name, dist_id, dist_name = self.claim_next_ac()
            if not ac_no:
                print(f"[Node {self.node_id}] All pending ACs completed. Sleeping 30s...", flush=True)
                self.register_heartbeat(rate=0.0)
                time.sleep(30)
                continue

            self.process_constituency(ac_no, ac_slug, ac_name, dist_id, dist_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed APSEC GP & MPTC Worker Node")
    parser.add_argument("--node-id", type=str, default=f"node-{socket.gethostname().lower()}")
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    node = WorkerNode(args.node_id, args.workers)
    node.run()
