import argparse
import collections
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

LAN_URL = "http://192.168.1.5:8085"
TUNNEL_URL = "https://seniors-auditor-presentation-george.trycloudflare.com"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_SCRIPT = os.path.join(REPO_ROOT, "worker", "worker_node.py")


def resolve_coordinator(preferred=None):
    candidates = [preferred.rstrip("/")] if preferred else [LAN_URL, TUNNEL_URL]
    for url in candidates:
        try:
            with urllib.request.urlopen(f"{url}/api/telemetry", timeout=3) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            continue
    return candidates[-1]


def install_launch_agent(node_id, workers, coord_url):
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(plist_dir, exist_ok=True)
    plist_path = os.path.join(plist_dir, "com.apsec.macagent.plist")
    log_path = os.path.join(REPO_ROOT, "mac_agent.log")
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.apsec.macagent</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>-u</string>
    <string>{os.path.abspath(__file__)}</string>
    <string>--node-id</string>
    <string>{node_id}</string>
    <string>--workers</string>
    <string>{workers}</string>
    <string>--coordinator-url</string>
    <string>{coord_url}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log_path}</string>
  <key>StandardErrorPath</key><string>{log_path}</string>
</dict>
</plist>
"""
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(plist)
    subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
    subprocess.run(["launchctl", "load", plist_path], check=True)
    print(f"[MacAgent] LaunchAgent installed & running: {plist_path}", flush=True)


class RemoteAgent:
    def __init__(self, node_id, workers, coord_url, idle=False):
        self.node_id = node_id
        self.workers = max(1, workers)
        self.coord_url = coord_url.rstrip("/")
        self.hostname = socket.gethostname()
        try:
            self.ip_address = socket.gethostbyname(self.hostname)
        except Exception:
            self.ip_address = "0.0.0.0"
        self.proc = None
        self.log_tail = collections.deque(maxlen=60)
        self.lock = threading.Lock()
        if not idle:
            self.start_worker(self.workers)

    def _log(self, msg):
        print(msg, flush=True)
        with self.lock:
            self.log_tail.append(msg)

    def _read_stream(self, proc):
        if not proc.stdout:
            return
        for line in proc.stdout:
            text = line.rstrip("\r\n")
            if text:
                print(text, flush=True)
                with self.lock:
                    self.log_tail.append(text)

    def stop_worker(self):
        if self.proc and self.proc.poll() is None:
            self._log("[MacAgent] Stopping worker process...")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def start_worker(self, workers):
        self.stop_worker()
        self.workers = max(1, int(workers))
        cmd = [
            sys.executable, "-u", WORKER_SCRIPT,
            "--node-id", self.node_id,
            "--workers", str(self.workers),
            "--coordinator-url", self.coord_url
        ]
        self._log(f"[MacAgent] Starting worker ({self.workers}T) -> {self.coord_url}")
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        t = threading.Thread(target=self._read_stream, args=(self.proc,), daemon=True)
        t.start()

    def self_update(self, workers):
        self._log(f"[MacAgent] Downloading updated kit from {self.coord_url}/mac-kit.zip ...")
        self.stop_worker()
        with urllib.request.urlopen(f"{self.coord_url}/mac-kit.zip", timeout=30) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(REPO_ROOT)
        sh_path = os.path.join(REPO_ROOT, "scripts", "join_mac.sh")
        if os.path.exists(sh_path):
            os.chmod(sh_path, 0o755)
        self._log("[MacAgent] Update extracted; reloading agent...")
        os.execv(sys.executable, [
            sys.executable, "-u", os.path.abspath(__file__),
            "--node-id", self.node_id,
            "--workers", str(workers),
            "--coordinator-url", self.coord_url
        ])

    def poll_once(self):
        running = self.proc is not None and self.proc.poll() is None
        with self.lock:
            tail = list(self.log_tail)[-40:]
        payload = json.dumps({
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "worker_running": running,
            "workers_count": self.workers if running else 0,
            "log_tail": tail
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.coord_url}/api/node/poll",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def run(self):
        self._log(f"[MacAgent] Remote control active for node '{self.node_id}' -> {self.coord_url}")
        while True:
            try:
                res = self.poll_once()
                cmd = res.get("command")
                if cmd:
                    action = cmd.get("action")
                    w = int(cmd.get("workers") or self.workers)
                    self._log(f"[MacAgent] Executed remote command: {action} (workers={w})")
                    if action in ("start", "scale", "restart"):
                        self.start_worker(w)
                    elif action == "stop":
                        self.stop_worker()
                    elif action == "update":
                        self.self_update(w)
            except Exception as e:
                print(f"[MacAgent Poll Error] {e}", flush=True)
                self.coord_url = resolve_coordinator()
            time.sleep(4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APSEC Remote-Orchestrated MacBook Cluster Agent")
    parser.add_argument("--node-id", type=str, default=f"macbook-{socket.gethostname().split('.')[0].lower()}")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--coordinator-url", type=str, default=None)
    parser.add_argument("--idle", action="store_true", help="Stay idle waiting for Windows coordinator start command")
    parser.add_argument("--install-autostart", action="store_true", help="Install macOS LaunchAgent and run persistently")
    args = parser.parse_args()

    coord = resolve_coordinator(args.coordinator_url)
    if args.install_autostart:
        install_launch_agent(args.node_id, args.workers, coord)
        sys.exit(0)

    agent = RemoteAgent(args.node_id, args.workers, coord, idle=args.idle)
    agent.run()
