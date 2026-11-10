import http.server
import socketserver
import json
import sqlite3
import os
import sys
import time
import urllib.parse
import threading
import csv
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "coordinator", "registry.sqlite")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
COORDINATOR_LOCK = threading.Lock()
CONTROL_QUEUE = {}
REMOTE_AGENTS = {}
CMD_SEQ = [0]

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
      <div class="stat-title">Mandals Completed</div>
      <div class="stat-val" id="stat-mandals" style="color:#4ade80;">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Active Worker Nodes</div>
      <div class="stat-val" id="stat-nodes" style="color:#38bdf8;">--</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Voter Throughput</div>
      <div class="stat-val" id="stat-rate">-- voters/s</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">HTTP Request Rate</div>
      <div class="stat-val" id="stat-req-rate" style="color:#facc15;">-- req/s</div>
    </div>
  </div>

  <div class="card">
    <h3>Active Worker Cluster (Laptops / Servers)</h3>
    <table>
      <thead>
        <tr>
          <th>Node ID</th>
          <th>Host & IP</th>
          <th>Active Threads</th>
          <th>Current Lease</th>
          <th>Voter Rate</th>
          <th>HTTP Rate</th>
          <th>Last Heartbeat</th>
          <th>Status</th>
          <th>Remote Control</th>
        </tr>
      </thead>
      <tbody id="nodes-tbody">
        <tr><td colspan="9" style="text-align:center; color:var(--muted);">No active nodes registered yet. Launch a worker node to join cluster.</td></tr>
      </tbody>
    </table>
    <div id="remote-logs-panel" style="margin-top:16px; display:none;">
      <h4 style="font-size:13px; color:#94a3b8; margin-bottom:8px;">Remote Agent Live Console</h4>
      <pre id="remote-logs-pre" style="background:#0f172a; border:1px solid var(--border); border-radius:8px; padding:12px; font-size:12px; color:#cbd5e1; max-height:220px; overflow:auto; white-space:pre-wrap;"></pre>
    </div>
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
function sendNodeCmd(nodeId, action, workers) {
  fetch('/api/node/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId, action: action, workers: workers })
  }).then(r => r.json()).then(() => refreshTelemetry());
}

function refreshTelemetry() {
  fetch('/api/telemetry')
    .then(r => r.json())
    .then(data => {
      document.getElementById('stat-mandals').innerText = data.completed_mandals + " / " + data.total_mandals;
      document.getElementById('stat-nodes').innerText = data.nodes.length;
      document.getElementById('stat-rate').innerText = data.cluster_rate.toFixed(1) + " voters/s";
      document.getElementById('stat-req-rate').innerText = data.http_req_rate.toFixed(1) + " req/s";

      const remoteMap = {};
      (data.remote_agents || []).forEach(a => { remoteMap[a.node_id] = a; });

      // Nodes Table
      const nbody = document.getElementById('nodes-tbody');
      if (data.nodes.length === 0) {
        nbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--muted);">No active nodes connected yet. Run worker_node.py on any laptop to begin.</td></tr>';
      } else {
        nbody.innerHTML = data.nodes.map(n => {
          const isRemote = Boolean(remoteMap[n.node_id]);
          const ctrl = isRemote ? `
            <button class="btn" style="padding:3px 8px; margin-right:4px;" onclick="sendNodeCmd('${n.node_id}','scale',2)">2T</button>
            <button class="btn" style="padding:3px 8px; margin-right:4px;" onclick="sendNodeCmd('${n.node_id}','scale',4)">4T</button>
            <button class="btn" style="padding:3px 8px; margin-right:4px;" onclick="sendNodeCmd('${n.node_id}','update',${n.workers_count})">Update</button>
            <button class="btn" style="padding:3px 8px; background:#dc2626;" onclick="sendNodeCmd('${n.node_id}','stop',0)">Stop</button>
          ` : '<span style="color:var(--muted)">Local Host</span>';
          return `
          <tr>
            <td><strong>${n.node_id}</strong></td>
            <td>${n.hostname} (${n.ip_address})</td>
            <td>${n.workers_count} active thread${n.workers_count === 1 ? '' : 's'}</td>
            <td>AC ${n.current_ac || 'Idle'}</td>
            <td>${n.rate.toFixed(1)} voters/s</td>
            <td>${data.http_req_rate.toFixed(1)} req/s</td>
            <td>${n.last_seen_sec}s ago</td>
            <td><span class="status-badge status-COMPLETED">${n.status}</span></td>
            <td>${ctrl}</td>
          </tr>`;
        }).join('');
      }

      const logPanel = document.getElementById('remote-logs-panel');
      const logPre = document.getElementById('remote-logs-pre');
      const agents = data.remote_agents || [];
      if (agents.length > 0) {
        logPanel.style.display = 'block';
        logPre.innerText = agents.map(a =>
          `=== ${a.node_id} (${a.worker_running ? 'RUNNING ' + a.workers_count + 'T' : 'STOPPED'} | seen ${a.last_poll_sec}s ago) ===\n` +
          (a.log_tail || []).join('\n')
        ).join('\n\n');
      } else {
        logPanel.style.display = 'none';
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

        elif parsed.path == "/mac-kit.zip":
            kit_path = os.path.join(EXPORTS_DIR, "apsec_mac_worker_kit.zip")
            if not os.path.exists(kit_path):
                self._send_json(404, {"error": "mac-kit.zip not built yet"})
                return
            with open(kit_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="apsec_mac_worker_kit.zip"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif parsed.path == "/api/telemetry":
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cur = conn.cursor()
            now = time.time()

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

            # Mandals & live 60-second HTTP request rate estimate (GPs + MPTCs updated in last 60s)
            total_mandals = cur.execute("SELECT COUNT(*) FROM mandals").fetchone()[0]
            completed_mandals = cur.execute("SELECT COUNT(*) FROM mandals WHERE status='COMPLETED'").fetchone()[0]
            gps_60s = cur.execute("SELECT COUNT(*) FROM gram_panchayats WHERE updated_at > ?", (now - 60,)).fetchone()[0]
            mptcs_60s = cur.execute("SELECT COUNT(DISTINCT mptc_id || '_' || mandal_id) FROM mptc_mappings WHERE updated_at > ?", (now - 60,)).fetchone()[0]
            http_req_rate = round((gps_60s + mptcs_60s) / 60.0, 2)

            # Nodes
            cur.execute("SELECT node_id, hostname, ip_address, workers_count, last_heartbeat, current_ac, rate_voters_per_sec, status FROM worker_nodes")
            nodes = []
            cluster_rate = 0.0
            for r in cur.fetchall():
                cluster_rate += r[6]
                active_threads = 1 if r[3] == 24 else r[3]
                nodes.append({
                    "node_id": r[0], "hostname": r[1], "ip_address": r[2],
                    "workers_count": active_threads, "last_seen_sec": int(now - r[4]),
                    "current_ac": r[5], "rate": r[6], "status": r[7]
                })

            conn.close()

            with COORDINATOR_LOCK:
                remote_agents = []
                for nid, info in REMOTE_AGENTS.items():
                    remote_agents.append({
                        "node_id": nid,
                        "hostname": info.get("hostname"),
                        "ip_address": info.get("ip_address"),
                        "worker_running": info.get("worker_running", False),
                        "workers_count": info.get("workers_count", 0),
                        "last_poll_sec": int(now - info.get("last_poll", now)),
                        "pending_cmds": len(CONTROL_QUEUE.get(nid, [])),
                        "log_tail": info.get("log_tail", [])
                    })

            payload = {
                "total_acs": len(acs),
                "completed_acs": comp_cnt,
                "total_mandals": total_mandals,
                "completed_mandals": completed_mandals,
                "cluster_rate": cluster_rate,
                "http_req_rate": http_req_rate,
                "nodes": nodes,
                "remote_agents": remote_agents,
                "constituencies": acs
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        elif parsed.path == "/api/node/logs":
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("node_id", [None])[0]
            with COORDINATOR_LOCK:
                if target:
                    data = REMOTE_AGENTS.get(target, {})
                else:
                    data = REMOTE_AGENTS
            self._send_json(200, {"agents": data})
            return

        super().do_GET()

    def _send_json(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "invalid json"})
            return

        now = time.time()

        if parsed.path == "/api/heartbeat":
            with COORDINATOR_LOCK:
                conn = sqlite3.connect(DB_PATH, timeout=30)
                conn.execute("""
                INSERT INTO worker_nodes (node_id, hostname, ip_address, workers_count, last_heartbeat, current_ac, rate_voters_per_sec, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                ON CONFLICT(node_id) DO UPDATE SET
                    hostname=excluded.hostname,
                    ip_address=excluded.ip_address,
                    workers_count=excluded.workers_count,
                    last_heartbeat=excluded.last_heartbeat,
                    current_ac=excluded.current_ac,
                    rate_voters_per_sec=excluded.rate_voters_per_sec,
                    status='ACTIVE'
                """, (
                    body.get("node_id"), body.get("hostname", "remote"),
                    body.get("ip_address", self.client_address[0]),
                    int(body.get("workers_count", 1)), now,
                    body.get("current_ac"), float(body.get("rate", 0.0))
                ))
                conn.commit()
                conn.close()
            self._send_json(200, {"ok": True})
            return

        elif parsed.path == "/api/claim_mandal":
            node_id = body.get("node_id", "remote-node")
            with COORDINATOR_LOCK:
                conn = sqlite3.connect(DB_PATH, timeout=30)
                cur = conn.cursor()
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
                if not row:
                    conn.close()
                    self._send_json(200, {"mandal": None})
                    return
                m_id, d_id, d_name, rd_id, m_name, pri_ac = row
                cur.execute("UPDATE mandals SET status = 'IN_PROGRESS', assigned_node = ?, updated_at = ? WHERE mandal_id = ?", (node_id, now, m_id))
                conn.commit()
                conn.close()
            self._send_json(200, {
                "mandal": {
                    "mandal_id": m_id, "district_id": d_id, "district_name": d_name,
                    "rev_div_id": rd_id, "mandal_name": m_name, "primary_ac_no": pri_ac
                }
            })
            return

        elif parsed.path == "/api/submit_mandal":
            node_id = body.get("node_id", "remote-node")
            m_id = str(body.get("mandal_id"))
            d_id = str(body.get("district_id"))
            rd_id = str(body.get("rev_div_id"))
            m_name = body.get("mandal_name", "")
            mandal_ac = int(body.get("mandal_ac") or 0)
            mptcs = body.get("mptcs", [])
            gps = body.get("gps", [])
            wards_by_gp = body.get("wards_by_gp", {})

            touched_acs = set()
            mandal_voters = 0
            with COORDINATOR_LOCK:
                conn = sqlite3.connect(DB_PATH, timeout=30)
                cur = conn.cursor()
                for mp in mptcs:
                    ac_val = int(mp.get("ac_no") or mandal_ac or 0)
                    cur.execute("""
                    INSERT INTO mptc_mappings (district_id, mandal_id, mandal_name, mptc_id, mptc_name, gp_id, gp_name, wards_range, ac_no, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(mandal_id, mptc_id, gp_id, wards_range) DO UPDATE SET
                        mptc_name=excluded.mptc_name, gp_name=excluded.gp_name, ac_no=excluded.ac_no, updated_at=excluded.updated_at
                    """, (str(mp["district_id"]), str(mp["mandal_id"]), mp["mandal_name"], str(mp["mptc_id"]), mp["mptc_name"], str(mp["gp_id"]), mp["gp_name"], mp["wards_range"], ac_val, now))

                for gp in gps:
                    gp_id = str(gp["gp_id"])
                    ac_no = int(gp.get("ac_no") or mandal_ac or 0)
                    if ac_no:
                        touched_acs.add(ac_no)
                    w_list = wards_by_gp.get(gp_id, [])
                    mandal_voters += int(gp.get("total", 0))
                    cur.execute("""
                    INSERT INTO gram_panchayats (gp_id, ac_no, district_id, rev_div_id, mandal_id, mandal_name, gp_name_en, official_voters, harvested_voters, male_voters, female_voters, other_voters, wards_count, dpo_confirmed, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'COMPLETED', ?)
                    ON CONFLICT(gp_id) DO UPDATE SET
                        ac_no=excluded.ac_no, district_id=excluded.district_id, rev_div_id=excluded.rev_div_id,
                        mandal_id=excluded.mandal_id, mandal_name=excluded.mandal_name, gp_name_en=excluded.gp_name_en,
                        official_voters=excluded.official_voters, harvested_voters=excluded.harvested_voters,
                        male_voters=excluded.male_voters, female_voters=excluded.female_voters, other_voters=excluded.other_voters,
                        wards_count=excluded.wards_count, status='COMPLETED', updated_at=excluded.updated_at
                    """, (gp_id, ac_no, d_id, rd_id, m_id, m_name, gp["gp_name"], gp["total"], gp["total"], gp["male"], gp["female"], gp["other"], len(w_list), now))

                    for w in w_list:
                        cur.execute("""
                        INSERT INTO ward_strengths (ac_no, mandal_id, gp_id, ward_no, male_voters, female_voters, other_voters, total_voters, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(gp_id, ward_no) DO UPDATE SET
                            ac_no=excluded.ac_no, male_voters=excluded.male_voters, female_voters=excluded.female_voters,
                            other_voters=excluded.other_voters, total_voters=excluded.total_voters, updated_at=excluded.updated_at
                        """, (ac_no, m_id, gp_id, str(w["ward_no"]), w["male"], w["female"], w["other"], w["total"], now))

                cur.execute("""
                UPDATE mandals
                SET status = 'COMPLETED', primary_ac_no = CASE WHEN primary_ac_no=0 THEN ? ELSE primary_ac_no END,
                    total_gps = ?, total_voters = ?, assigned_node = ?, updated_at = ?
                WHERE mandal_id = ?
                """, (mandal_ac, len(gps), mandal_voters, node_id, now, m_id))

                for ac_no in touched_acs:
                    row = cur.execute("SELECT COUNT(*), COALESCE(SUM(official_voters), 0) FROM gram_panchayats WHERE ac_no = ?", (ac_no,)).fetchone()
                    cnt, voters = row
                    pending_m = cur.execute("SELECT COUNT(*) FROM mandals WHERE primary_ac_no = ? AND status != 'COMPLETED'", (ac_no,)).fetchone()[0]
                    total_m = cur.execute("SELECT COUNT(*) FROM mandals WHERE primary_ac_no = ?", (ac_no,)).fetchone()[0]
                    done_ac = (total_m > 0 and pending_m == 0)
                    cur.execute("""
                    UPDATE constituencies
                    SET total_gps = ?, completed_gps = ?, total_voters = ?, completed_voters = ?,
                        status = CASE WHEN status = 'SYNCED' THEN 'SYNCED' WHEN ? THEN 'COMPLETED' ELSE 'IN_PROGRESS' END,
                        assigned_node = ?, updated_at = ?
                    WHERE ac_no = ?
                    """, (cnt, cnt, voters, voters, 1 if done_ac else 0, node_id, now, ac_no))
                conn.commit()
                conn.close()

            self._send_json(200, {"ok": True, "gps": len(gps), "voters": mandal_voters})
            return

        elif parsed.path == "/api/node/poll":
            nid = str(body.get("node_id") or "remote-agent")
            with COORDINATOR_LOCK:
                REMOTE_AGENTS[nid] = {
                    "hostname": body.get("hostname", "remote"),
                    "ip_address": body.get("ip_address", self.client_address[0]),
                    "worker_running": bool(body.get("worker_running", False)),
                    "workers_count": int(body.get("workers_count", 0)),
                    "last_poll": now,
                    "log_tail": list(body.get("log_tail", []))[-50:]
                }
                q = CONTROL_QUEUE.get(nid, [])
                cmd = q.pop(0) if q else None
            self._send_json(200, {"ok": True, "command": cmd})
            return

        elif parsed.path == "/api/node/command":
            nid = str(body.get("node_id") or "all")
            action = str(body.get("action") or "restart").lower()
            workers = int(body.get("workers") or 4)
            with COORDINATOR_LOCK:
                CMD_SEQ[0] += 1
                cmd = {"id": CMD_SEQ[0], "action": action, "workers": workers, "created_at": now}
                targets = list(REMOTE_AGENTS.keys()) if nid == "all" else [nid]
                for t in targets:
                    CONTROL_QUEUE.setdefault(t, []).append(dict(cmd))
            self._send_json(200, {"ok": True, "queued_for": targets, "command": cmd})
            return

        self._send_json(404, {"error": "not found"})

def run_telemetry_server(port=8085):
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("0.0.0.0", port), TelemetryHandler)
    print(f"[Telemetry] Server running on http://0.0.0.0:{port}")
    server.serve_forever()

if __name__ == "__main__":
    run_telemetry_server()
