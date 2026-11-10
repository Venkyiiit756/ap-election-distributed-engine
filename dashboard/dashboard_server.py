import http.server
import socketserver
import json
import sqlite3
import os
import sys
import time
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coordinator", "registry.sqlite")

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Andhra Pradesh Distributed Electoral Pipeline — Live Telemetry</title>
<style>
  :root {
    --primary: #2563eb;
    --primary-dark: #1d4ed8;
    --success: #16a34a;
    --warning: #d97706;
    --bg: #0f172a;
    --card: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 24px; }
  .container { max-width: 1300px; margin: 0 auto; }
  header { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 1px solid var(--border); padding: 24px 30px; border-radius: 12px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }
  header h1 { font-size: 22px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 10px; }
  .badge-live { background: #22c55e22; border: 1px solid #22c55e; color: #4ade80; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
  
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; }
  .stat-title { font-size: 13px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-val { font-size: 26px; font-weight: 700; color: var(--text); margin-top: 6px; }
  
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 22px; margin-bottom: 24px; }
  .card h3 { font-size: 17px; margin-bottom: 14px; color: #e2e8f0; display: flex; justify-content: space-between; }
  
  table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  th { background: #0f172a; text-align: left; padding: 12px 14px; font-weight: 600; color: #94a3b8; border-bottom: 1px solid var(--border); }
  td { padding: 12px 14px; border-bottom: 1px solid var(--border); color: #cbd5e1; }
  tr:hover { background: #33415544; }
  
  .status-badge { display: inline-block; padding: 3px 10px; border-radius: 6px; font-size: 11.5px; font-weight: 600; }
  .status-PENDING { background: #334155; color: #94a3b8; }
  .status-IN_PROGRESS { background: #fef08a22; border: 1px solid #facc15; color: #fef08a; }
  .status-COMPLETED { background: #22c55e22; border: 1px solid #22c55e; color: #86efac; }
  .status-SYNCED { background: #38bdf822; border: 1px solid #38bdf8; color: #7dd3fc; }
  
  .btn { background: var(--primary); color: white; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: 600; display: inline-block; }
  .btn:hover { background: var(--primary-dark); }
</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1>Andhra Pradesh Electoral Pipeline — Live Telemetry</h1>
      <p style="color:var(--muted); font-size:13.5px; margin-top:4px;">Multi-Node Distributed Harvester & Cloud Synchronizer (175 Assembly Constituencies)</p>
    </div>
    <div>
      <span class="badge-live">● TELEMETRY ACTIVE</span>
    </div>
  </header>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-title">Total Constituencies</div>
      <div class="stat-val" id="stat-acs">175</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Completed ACs</div>
      <div class="stat-val" id="stat-completed" style="color:#4ade80;">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Active Worker Nodes</div>
      <div class="stat-val" id="stat-nodes" style="color:#38bdf8;">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Cluster Throughput</div>
      <div class="stat-val" id="stat-rate">-- req/s</div>
    </div>
  </div>

  <div class="card">
    <h3>Active Worker Cluster (Laptops / Servers)</h3>
    <table>
      <thead>
        <tr>
          <th>Node ID</th>
          <th>Host & IP</th>
          <th>Parallel Workers</th>
          <th>Current Lease</th>
          <th>Throughput</th>
          <th>Last Heartbeat</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="nodes-tbody">
        <tr><td colspan="7" style="text-align:center; color:var(--muted);">No active nodes registered yet. Launch a worker node to join cluster.</td></tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h3>Assembly Constituencies Status Grid</h3>
    <table>
      <thead>
        <tr>
          <th>AC No</th>
          <th>Constituency</th>
          <th>District</th>
          <th>Status</th>
          <th>Progress (GPs / Voters)</th>
          <th>Assigned Node</th>
          <th>Google Drive Cloud Link</th>
        </tr>
      </thead>
      <tbody id="acs-tbody">
        <tr><td colspan="7" style="text-align:center; color:var(--muted);">Loading telemetry registry...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<script>
function refreshTelemetry() {
  fetch('/api/telemetry')
    .then(r => r.json())
    .then(data => {
      document.getElementById('stat-completed').innerText = data.completed_acs + " / " + data.total_acs;
      document.getElementById('stat-nodes').innerText = data.nodes.length;
      document.getElementById('stat-rate').innerText = data.cluster_rate.toFixed(1) + " req/s";

      // Nodes Table
      const nbody = document.getElementById('nodes-tbody');
      if (data.nodes.length === 0) {
        nbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--muted);">No active nodes connected yet. Run worker_node.py on any laptop to begin.</td></tr>';
      } else {
        nbody.innerHTML = data.nodes.map(n => `
          <tr>
            <td><strong>${n.node_id}</strong></td>
            <td>${n.hostname} (${n.ip_address})</td>
            <td>${n.workers_count} threads</td>
            <td>AC ${n.current_ac || 'Idle'}</td>
            <td>${n.rate.toFixed(1)} voters/s</td>
            <td>${n.last_seen_sec}s ago</td>
            <td><span class="status-badge status-COMPLETED">${n.status}</span></td>
          </tr>
        `).join('');
      }

      // ACs Table
      const abody = document.getElementById('acs-tbody');
      abody.innerHTML = data.constituencies.map(ac => `
        <tr>
          <td><strong>${ac.ac_no}</strong></td>
          <td>${ac.ac_name}</td>
          <td>${ac.district_name}</td>
          <td><span class="status-badge status-${ac.status}">${ac.status}</span></td>
          <td>${ac.completed_gps} / ${ac.total_gps} GPs (${ac.completed_voters.toLocaleString()} voters)</td>
          <td>${ac.assigned_node || '—'}</td>
          <td>${ac.gdrive_url ? `<a class="btn" target="_blank" href="${ac.gdrive_url}">Open Drive</a>` : '<span style="color:var(--muted)">Pending Sync</span>'}</td>
        </tr>
      `).join('');
    })
    .catch(err => console.error("Telemetry error:", err));
}

setInterval(refreshTelemetry, 2500);
refreshTelemetry();
</script>
</body>
</html>
"""

class TelemetryHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        elif parsed.path == "/api/telemetry":
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            # ACs
            cur.execute("SELECT ac_no, ac_name, district_name, status, total_gps, completed_gps, completed_voters, assigned_node, gdrive_url FROM constituencies ORDER BY ac_no ASC")
            acs = []
            comp_cnt = 0
            for r in cur.fetchall():
                if r[3] in ('COMPLETED', 'SYNCED'):
                    comp_cnt += 1
                acs.append({
                    "ac_no": r[0], "ac_name": r[1], "district_name": r[2],
                    "status": r[3], "total_gps": r[4], "completed_gps": r[5],
                    "completed_voters": r[6], "assigned_node": r[7], "gdrive_url": r[8]
                })

            # Nodes
            cur.execute("SELECT node_id, hostname, ip_address, workers_count, last_heartbeat, current_ac, rate_voters_per_sec, status FROM worker_nodes")
            nodes = []
            cluster_rate = 0.0
            now = time.time()
            for r in cur.fetchall():
                cluster_rate += r[6]
                nodes.append({
                    "node_id": r[0], "hostname": r[1], "ip_address": r[2],
                    "workers_count": r[3], "last_seen_sec": int(now - r[4]),
                    "current_ac": r[5], "rate": r[6], "status": r[7]
                })

            conn.close()

            payload = {
                "total_acs": len(acs),
                "completed_acs": comp_cnt,
                "cluster_rate": cluster_rate,
                "nodes": nodes,
                "constituencies": acs
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        super().do_GET()

def run_telemetry_server(port=8085):
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    server = socketserver.ThreadingTCPServer(("0.0.0.0", port), TelemetryHandler)
    server.allow_reuse_address = True
    print(f"[Telemetry] Server running on http://0.0.0.0:{port}")
    server.serve_forever()

if __name__ == "__main__":
    run_telemetry_server()
