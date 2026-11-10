import subprocess
import os
import sys
import shutil

class GoogleDriveSync:
    def __init__(self, target_folder_name="Andhra_Pradesh_Electoral_Rolls_2026"):
        self.target_folder_name = target_folder_name
        self.root_folder_id = None

    def ensure_target_folder(self):
        # Check if already cached
        if self.root_folder_id:
            return self.root_folder_id

        # Use gdrive CLI to search or create
        try:
            res = subprocess.run(["gdrive", "readonly", "search", "--name-contains", self.target_folder_name, "--json"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                # Parse or find ID
                for line in res.stdout.splitlines():
                    if self.target_folder_name in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            self.root_folder_id = parts[0]
                            return self.root_folder_id
        except Exception:
            pass

        # Create folder if not found
        try:
            res = subprocess.run(["gdrive", "mutate", "mkdir", self.target_folder_name], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                if "ID:" in line:
                    self.root_folder_id = line.split("ID:")[1].strip().rstrip(")")
                    return self.root_folder_id
        except Exception as e:
            print(f"[GDrive Error] Could not create folder: {e}")
        return None

    def upload_constituency_archive(self, file_path, parent_id=None):
        if not parent_id:
            parent_id = self.ensure_target_folder()
        if not os.path.exists(file_path):
            return None, "File does not exist"

        cmd = ["gdrive", "mutate", "upload", file_path]
        if parent_id:
            cmd.extend(["--parent", parent_id])

        res = subprocess.run(cmd, capture_output=True, text=True)
        file_id = None
        for line in res.stdout.splitlines():
            if "ID:" in line:
                file_id = line.split("ID:")[1].strip().rstrip(")")
                break

        url = f"https://drive.google.com/file/d/{file_id}/view" if file_id else None
        return file_id, url
