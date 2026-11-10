import subprocess
import os
import json

DEFAULT_FOLDER_ID = "1CDVPt7JAEnzbW8rJsEv1MChtV7zf9NFG"  # Pithapuram_Rural_GPs_and_MPTC_Voters_2026

class GoogleDriveSync:
    def __init__(self, target_folder_name="AP_175_ACs_GP_MPTC_2026", parent_folder_id=DEFAULT_FOLDER_ID):
        self.target_folder_name = target_folder_name
        self.parent_folder_id = parent_folder_id
        self.root_folder_id = None

    def ensure_target_folder(self):
        if self.root_folder_id:
            return self.root_folder_id

        try:
            res = subprocess.run(
                ["gdrive", "readonly", "search", "--name-contains", self.target_folder_name, "--json"],
                capture_output=True, text=True, timeout=30
            )
            if res.returncode == 0 and res.stdout.strip():
                items = json.loads(res.stdout)
                for item in items:
                    if item.get("name") == self.target_folder_name:
                        self.root_folder_id = item.get("id")
                        return self.root_folder_id
        except Exception:
            pass

        try:
            cmd = ["gdrive", "mutate", "mkdir", self.target_folder_name, "--json"]
            if self.parent_folder_id:
                cmd.extend(["--parent", self.parent_folder_id])
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                self.root_folder_id = data.get("id")
                return self.root_folder_id
        except Exception as e:
            print(f"[GDrive Error] Could not create folder: {e}", flush=True)
        return self.parent_folder_id

    def upload_constituency_archive(self, file_path, parent_id=None):
        if not parent_id:
            parent_id = self.ensure_target_folder()
        if not os.path.exists(file_path):
            return None, "File does not exist"

        fname = os.path.basename(file_path)
        try:
            # Check if file already exists inside target folder to update in place
            existing_id = None
            res_s = subprocess.run(
                ["gdrive", "readonly", "search", "--parent-id", parent_id, "--name-contains", fname, "--json"],
                capture_output=True, text=True, timeout=30
            )
            if res_s.returncode == 0 and res_s.stdout.strip():
                for it in json.loads(res_s.stdout):
                    if it.get("name") == fname:
                        existing_id = it.get("id")
                        break

            if existing_id:
                res = subprocess.run(["gdrive", "mutate", "update", existing_id, file_path, "--json"], capture_output=True, text=True, timeout=60)
            else:
                res = subprocess.run(["gdrive", "mutate", "upload", file_path, "--parent", parent_id, "--json"], capture_output=True, text=True, timeout=60)

            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                fid = data.get("id") or existing_id
                url = data.get("webViewLink") or (f"https://drive.google.com/open?id={fid}" if fid else None)
                return fid, url
        except Exception as e:
            print(f"[GDrive Upload Error] {e}", flush=True)
        return None, None
