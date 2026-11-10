import subprocess
import os
import json
import shutil

DEFAULT_FOLDER_ID = "1CDVPt7JAEnzbW8rJsEv1MChtV7zf9NFG"  # Pithapuram_Rural_GPs_and_MPTC_Voters_2026


def _get_gdrive_bin():
    return shutil.which("gdrive") or "gdrive"


class GoogleDriveSync:
    def __init__(self, target_folder_name="AP_175_ACs_GP_MPTC_2026", parent_folder_id=DEFAULT_FOLDER_ID):
        self.target_folder_name = target_folder_name
        self.parent_folder_id = parent_folder_id
        self.root_folder_id = None
        self.gdrive_bin = _get_gdrive_bin()

    def _run(self, args, timeout=60):
        return subprocess.run(
            [self.gdrive_bin] + args,
            capture_output=True, text=True, timeout=timeout, shell=False
        )

    def ensure_target_folder(self):
        if self.root_folder_id:
            return self.root_folder_id

        try:
            res = self._run(["readonly", "search", "--name-contains", self.target_folder_name, "--json"], timeout=30)
            if res.returncode == 0 and res.stdout.strip():
                items = json.loads(res.stdout)
                for item in items:
                    if item.get("name") == self.target_folder_name:
                        self.root_folder_id = item.get("id")
                        return self.root_folder_id
        except Exception as e:
            print(f"[GDrive Search Error] {e}", flush=True)

        try:
            cmd = ["mutate", "mkdir", self.target_folder_name, "--json"]
            if self.parent_folder_id:
                cmd.extend(["--parent", self.parent_folder_id])
            res = self._run(cmd, timeout=30)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                self.root_folder_id = data.get("id")
                return self.root_folder_id
        except Exception as e:
            print(f"[GDrive Mkdir Error] {e}", flush=True)
        return self.parent_folder_id

    def upload_constituency_archive(self, file_path, parent_id=None):
        if not parent_id:
            parent_id = self.ensure_target_folder()
        if not os.path.exists(file_path):
            return None, "File does not exist"

        fname = os.path.basename(file_path)
        try:
            existing_id = None
            res_s = self._run(["readonly", "search", "--parent-id", parent_id, "--name-contains", fname, "--json"], timeout=30)
            if res_s.returncode == 0 and res_s.stdout.strip():
                for it in json.loads(res_s.stdout):
                    if it.get("name") == fname:
                        existing_id = it.get("id")
                        break

            if existing_id:
                res = self._run(["mutate", "update", existing_id, file_path, "--json"], timeout=60)
            else:
                res = self._run(["mutate", "upload", file_path, "--parent", parent_id, "--json"], timeout=60)

            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                fid = data.get("id") or existing_id
                url = data.get("webViewLink") or (f"https://drive.google.com/open?id={fid}" if fid else None)
                return fid, url
        except Exception as e:
            print(f"[GDrive Upload Error] {e}", flush=True)
        return None, None
