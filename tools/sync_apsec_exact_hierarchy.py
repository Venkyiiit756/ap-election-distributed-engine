import ssl, http.client, re, json, sqlite3, os, time

DISTRICTS = [
    ("745", "Alluri Sitharama Raju"), ("744", "Anakapalli"), ("502", "Ananthapuramu"),
    ("753", "Annamayya"), ("750", "Bapatla"), ("503", "Chittoor"),
    ("747", "Dr B R Ambedkar Konaseema"), ("505", "East Godavari"), ("748", "Eluru"),
    ("506", "Guntur"), ("746", "Kakinada"), ("510", "Krishna"),
    ("511", "Kurnool"), ("790", "Markapuram"), ("755", "Nandyal"),
    ("749", "NTR"), ("751", "Palnadu"), ("743", "Parvathipuram Manyam"),
    ("791", "Polavaram"), ("517", "Prakasam"), ("519", "Srikakulam"),
    ("515", "Sri Potti Sreeramulu Nellore"), ("754", "Sri Sathya Sai"),
    ("752", "Tirupati"), ("520", "Visakhapatnam"), ("521", "Vizianagaram"),
    ("523", "West Godavari"), ("504", "Y S R Kadapa")
]

ctx = ssl.create_default_context()
conn = http.client.HTTPSConnection("sec-ems.ap.gov.in", 443, timeout=20, context=ctx)
conn.request("GET", "/apsec/rollsHome", headers={"User-Agent": "Mozilla/5.0"})
r = conn.getresponse()
body = r.read().decode("utf-8", errors="ignore")
csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', body).group(1)
cookie_val = "; ".join([c.split(";")[0] for k, c in r.getheaders() if k.lower() == "set-cookie"])

hdrs = {"User-Agent": "Mozilla/5.0", "Cookie": cookie_val}
ajax_hdrs = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Cookie": cookie_val,
    "X-CSRF-TOKEN": csrf,
    "X-Requested-With": "XMLHttpRequest"
}

ac_to_dists = {}
dist_revdivs = {}

for dist_id, dist_name in DISTRICTS:
    conn.request("GET", f"/apsec/getAssemblyConstituenciesByDistrict?districtId={dist_id}", headers=hdrs)
    ac_resp = conn.getresponse().read().decode("utf-8", errors="ignore")
    acs = [(int(v), lbl.strip()) for v, lbl in re.findall(r'<option[^>]*value=["\']?(\d+)["\']?[^>]*>([^<]+)</option>', ac_resp) if v != "0"]

    conn.request("POST", "/apsec/getRevenueDivisionDataAjaxWithRevenueId", body=f"districtId={dist_id}&_csrf={csrf}", headers=ajax_hdrs)
    rev_resp = conn.getresponse().read().decode("utf-8", errors="ignore")
    revs = [(v, lbl.strip()) for v, lbl in re.findall(r'<option[^>]*value=["\']?([^"\'>]+)["\']?[^>]*>([^<]+)</option>', rev_resp) if v != "0"]
    dist_revdivs[dist_id] = revs

    print(f"District {dist_id} ({dist_name}): {len(acs)} ACs, {len(revs)} RevDivs")
    for ac_no, ac_lbl in acs:
        ac_to_dists.setdefault(ac_no, []).append((dist_id, dist_name, ac_lbl))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "coordinator", "registry.sqlite")
OUT_PATH = os.path.join(BASE_DIR, "configs", "apsec_district_hierarchy.json")

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump({"districts": DISTRICTS, "revdivs": dist_revdivs, "ac_to_dists": ac_to_dists}, f, indent=2)

# Update constituencies with primary authentic APSEC district_id
db = sqlite3.connect(DB_PATH)
cur = db.cursor()
for ac_no, dlist in ac_to_dists.items():
    primary_did, primary_dname, _ = dlist[0]
    cur.execute("UPDATE constituencies SET district_id = ?, district_name = ? WHERE ac_no = ?", (primary_did, primary_dname, ac_no))
db.commit()
db.close()
print(f"[✓] Synced {len(ac_to_dists)} ACs with authentic APSEC district IDs and saved {OUT_PATH}")
