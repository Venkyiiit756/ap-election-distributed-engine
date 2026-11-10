import csv
import os
import sqlite3
import time
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "coordinator", "registry.sqlite")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")


def main():
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()

    # Ensure ACs with harvested GPs (including AC 153 Anantapur Urban) are marked COMPLETED if all mandals are done
    pending_global = cur.execute("SELECT COUNT(*) FROM mandals WHERE status != 'COMPLETED'").fetchone()[0]
    if pending_global == 0:
        cur.execute("""
        UPDATE constituencies
        SET status = CASE WHEN status = 'SYNCED' THEN 'SYNCED' ELSE 'COMPLETED' END,
            updated_at = ?
        WHERE status = 'IN_PROGRESS' AND completed_gps > 0
        """, (time.time(),))
        conn.commit()

    acs = cur.execute(
        "SELECT DISTINCT ac_no FROM gram_panchayats WHERE ac_no > 0 ORDER BY ac_no ASC"
    ).fetchall()

    exported_zips = []
    summary_rows = []
    for (ac_no,) in acs:
        ac_row = cur.execute(
            "SELECT ac_slug, ac_name, district_name FROM constituencies WHERE ac_no = ?",
            (ac_no,)
        ).fetchone()
        if not ac_row:
            continue
        ac_slug, ac_name, dist_name = ac_row
        gp_rows = cur.execute(
            "SELECT ac_no, mandal_id, mandal_name, gp_id, gp_name_en, male_voters, female_voters, other_voters, official_voters, wards_count "
            "FROM gram_panchayats WHERE ac_no = ? ORDER BY mandal_name, gp_name_en",
            (ac_no,)
        ).fetchall()
        ward_rows = cur.execute(
            "SELECT w.ac_no, w.mandal_id, w.gp_id, g.gp_name_en, w.ward_no, w.male_voters, w.female_voters, w.other_voters, w.total_voters "
            "FROM ward_strengths w LEFT JOIN gram_panchayats g ON w.gp_id = g.gp_id "
            "WHERE w.ac_no = ? ORDER BY w.gp_id, CAST(w.ward_no AS INTEGER)",
            (ac_no,)
        ).fetchall()
        mptc_rows = cur.execute(
            "SELECT ac_no, district_id, mandal_id, mandal_name, mptc_id, mptc_name, gp_id, gp_name, wards_range "
            "FROM mptc_mappings WHERE ac_no = ? ORDER BY mandal_name, mptc_name",
            (ac_no,)
        ).fetchall()

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
            for p in (gp_csv, ward_csv, mptc_csv):
                zf.write(p, os.path.basename(p))
        exported_zips.append(zip_path)
        summary_rows.append((ac_no, ac_name, dist_name, len(gp_rows), sum(r[8] for r in gp_rows), len(ward_rows), len(mptc_rows)))

    summary_csv = os.path.join(EXPORTS_DIR, "APSEC_Rural_158_ACs_Summary_2026.csv")
    with open(summary_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["AC_No", "AC_Name", "District_Name", "GP_Count", "Total_Rural_Voters", "Ward_Rows_Count", "MPTC_Rows_Count"])
        w.writerows(summary_rows)

    master_zip = os.path.join(EXPORTS_DIR, "APSEC_Rural_158_ACs_Master_2026.zip")
    with zipfile.ZipFile(master_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(summary_csv, os.path.basename(summary_csv))
        for zp in exported_zips:
            zf.write(zp, os.path.basename(zp))

    conn.close()
    print(f"EXPORTED_ACS={len(exported_zips)} MASTER_ZIP={master_zip} SIZE={os.path.getsize(master_zip)}")


if __name__ == "__main__":
    main()
