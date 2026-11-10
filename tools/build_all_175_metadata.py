import os
import json
import sqlite3
import time

DISTRICT_MAP = {
    1: ("516", "Srikakulam"),
    2: ("516", "Srikakulam"),
    3: ("516", "Srikakulam"),
    4: ("516", "Srikakulam"),
    5: ("516", "Srikakulam"),
    6: ("516", "Srikakulam"),
    7: ("516", "Srikakulam"),
    8: ("516", "Srikakulam"),
    9: ("518", "Vizianagaram"),
    10: ("744", "Parvathipuram Manyam"),
    11: ("744", "Parvathipuram Manyam"),
    12: ("744", "Parvathipuram Manyam"),
    13: ("744", "Parvathipuram Manyam"),
    14: ("518", "Vizianagaram"),
    15: ("518", "Vizianagaram"),
    16: ("518", "Vizianagaram"),
    17: ("518", "Vizianagaram"),
    18: ("518", "Vizianagaram"),
    19: ("518", "Vizianagaram"),
    20: ("517", "Visakhapatnam"),
    21: ("517", "Visakhapatnam"),
    22: ("517", "Visakhapatnam"),
    23: ("517", "Visakhapatnam"),
    24: ("517", "Visakhapatnam"),
    25: ("517", "Visakhapatnam"),
    26: ("745", "Anakapalli"),
    27: ("745", "Anakapalli"),
    28: ("791", "Alluri Sitharama Raju"),
    29: ("791", "Alluri Sitharama Raju"),
    30: ("745", "Anakapalli"),
    31: ("745", "Anakapalli"),
    32: ("745", "Anakapalli"),
    33: ("745", "Anakapalli"),
    34: ("745", "Anakapalli"),
    35: ("746", "Kakinada"),
    36: ("746", "Kakinada"),
    37: ("746", "Kakinada"),
    38: ("746", "Kakinada"),
    39: ("746", "Kakinada"),
    40: ("505", "East Godavari"),
    41: ("746", "Kakinada"),
    42: ("747", "Dr B R Ambedkar Konaseema"),
    43: ("747", "Dr B R Ambedkar Konaseema"),
    44: ("747", "Dr B R Ambedkar Konaseema"),
    45: ("747", "Dr B R Ambedkar Konaseema"),
    46: ("747", "Dr B R Ambedkar Konaseema"),
    47: ("747", "Dr B R Ambedkar Konaseema"),
    48: ("747", "Dr B R Ambedkar Konaseema"),
    49: ("505", "East Godavari"),
    50: ("505", "East Godavari"),
    51: ("505", "East Godavari"),
    52: ("746", "Kakinada"),
    53: ("791", "Alluri Sitharama Raju"),
    54: ("505", "East Godavari"),
    55: ("505", "East Godavari"),
    56: ("506", "West Godavari"),
    57: ("506", "West Godavari"),
    58: ("506", "West Godavari"),
    59: ("506", "West Godavari"),
    60: ("506", "West Godavari"),
    61: ("506", "West Godavari"),
    62: ("506", "West Godavari"),
    63: ("748", "Eluru"),
    64: ("748", "Eluru"),
    65: ("748", "Eluru"),
    66: ("748", "Eluru"),
    67: ("748", "Eluru"),
    68: ("748", "Eluru"),
    69: ("749", "NTR"),
    70: ("748", "Eluru"),
    71: ("510", "Krishna"),
    72: ("510", "Krishna"),
    73: ("510", "Krishna"),
    74: ("510", "Krishna"),
    75: ("510", "Krishna"),
    76: ("510", "Krishna"),
    77: ("510", "Krishna"),
    78: ("510", "Krishna"),
    79: ("749", "NTR"),
    80: ("749", "NTR"),
    81: ("749", "NTR"),
    82: ("749", "NTR"),
    83: ("749", "NTR"),
    84: ("749", "NTR"),
    85: ("751", "Palnadu"),
    86: ("507", "Guntur"),
    87: ("507", "Guntur"),
    88: ("507", "Guntur"),
    89: ("750", "Bapatla"),
    90: ("750", "Bapatla"),
    91: ("507", "Guntur"),
    92: ("750", "Bapatla"),
    93: ("507", "Guntur"),
    94: ("507", "Guntur"),
    95: ("507", "Guntur"),
    96: ("751", "Palnadu"),
    97: ("751", "Palnadu"),
    98: ("751", "Palnadu"),
    99: ("751", "Palnadu"),
    100: ("751", "Palnadu"),
    101: ("751", "Palnadu"),
    102: ("511", "Prakasam"),
    103: ("511", "Prakasam"),
    104: ("750", "Bapatla"),
    105: ("750", "Bapatla"),
    106: ("750", "Bapatla"),
    107: ("511", "Prakasam"),
    108: ("511", "Prakasam"),
    109: ("515", "SPSR Nellore"),
    110: ("511", "Prakasam"),
    111: ("511", "Prakasam"),
    112: ("511", "Prakasam"),
    113: ("511", "Prakasam"),
    114: ("515", "SPSR Nellore"),
    115: ("515", "SPSR Nellore"),
    116: ("515", "SPSR Nellore"),
    117: ("515", "SPSR Nellore"),
    118: ("515", "SPSR Nellore"),
    119: ("515", "SPSR Nellore"),
    120: ("754", "Tirupati"),
    121: ("754", "Tirupati"),
    122: ("754", "Tirupati"),
    123: ("515", "SPSR Nellore"),
    124: ("503", "YSR Kadapa"),
    125: ("753", "Annamayya"),
    126: ("503", "YSR Kadapa"),
    127: ("753", "Annamayya"),
    128: ("753", "Annamayya"),
    129: ("503", "YSR Kadapa"),
    130: ("503", "YSR Kadapa"),
    131: ("503", "YSR Kadapa"),
    132: ("503", "YSR Kadapa"),
    133: ("503", "YSR Kadapa"),
    134: ("755", "Nandyal"),
    135: ("755", "Nandyal"),
    136: ("755", "Nandyal"),
    137: ("512", "Kurnool"),
    138: ("755", "Nandyal"),
    139: ("755", "Nandyal"),
    140: ("755", "Nandyal"),
    141: ("512", "Kurnool"),
    142: ("512", "Kurnool"),
    143: ("512", "Kurnool"),
    144: ("512", "Kurnool"),
    145: ("512", "Kurnool"),
    146: ("512", "Kurnool"),
    147: ("512", "Kurnool"),
    148: ("502", "Ananthapuramu"),
    149: ("502", "Ananthapuramu"),
    150: ("502", "Ananthapuramu"),
    151: ("502", "Ananthapuramu"),
    152: ("502", "Ananthapuramu"),
    153: ("502", "Ananthapuramu"),
    154: ("502", "Ananthapuramu"),
    155: ("502", "Ananthapuramu"),
    156: ("752", "Sri Sathya Sai"),
    157: ("752", "Sri Sathya Sai"),
    158: ("752", "Sri Sathya Sai"),
    159: ("752", "Sri Sathya Sai"),
    160: ("752", "Sri Sathya Sai"),
    161: ("752", "Sri Sathya Sai"),
    162: ("753", "Annamayya"),
    163: ("753", "Annamayya"),
    164: ("753", "Annamayya"),
    165: ("504", "Chittoor"),
    166: ("754", "Tirupati"),
    167: ("754", "Tirupati"),
    168: ("754", "Tirupati"),
    169: ("754", "Tirupati"),
    170: ("504", "Chittoor"),
    171: ("504", "Chittoor"),
    172: ("504", "Chittoor"),
    173: ("504", "Chittoor"),
    174: ("504", "Chittoor"),
    175: ("504", "Chittoor"),
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_ACS_PATH = os.path.join(BASE_DIR, "configs", "all_175_acs.json")
CONFIG_PATH = os.path.join(BASE_DIR, "configs", "state_metadata.json")
DB_PATH = os.path.join(BASE_DIR, "coordinator", "registry.sqlite")

def main():
    with open(ALL_ACS_PATH, "r", encoding="utf-8") as f:
        raw_acs = json.load(f)

    # Read existing state_metadata.json for district list
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    constituencies = []
    for ac_no, name in raw_acs:
        clean_name = name.replace(" AC (NOTA Total)", "").strip()
        slug = f"{ac_no:02d}_{clean_name.replace(' ', '_').replace('(', '').replace(')', '').replace('.', '')}"
        dist_id, dist_name = DISTRICT_MAP.get(ac_no, ("0", "Unknown"))
        constituencies.append({
            "ac_no": ac_no,
            "ac_slug": slug,
            "ac_name": clean_name,
            "district_id": dist_id,
            "district_name": dist_name
        })

    meta["constituencies"] = constituencies
    meta["total_constituencies"] = len(constituencies)
    meta["updated_at"] = time.time()

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[Metadata] Wrote {len(constituencies)} constituencies to {CONFIG_PATH}")

    # Seed into coordinator database
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
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

    seeded = 0
    now = time.time()
    for ac in constituencies:
        cur.execute("""
        INSERT OR IGNORE INTO constituencies (ac_no, ac_slug, ac_name, district_id, district_name, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (ac["ac_no"], ac["ac_slug"], ac["ac_name"], ac["district_id"], ac["district_name"], now))
        if cur.rowcount > 0:
            seeded += 1

    conn.commit()
    total_db = cur.execute("SELECT COUNT(*) FROM constituencies").fetchone()[0]
    print(f"[DB] Seeded {seeded} new constituencies. Total in registry: {total_db}")
    conn.close()

if __name__ == "__main__":
    main()
