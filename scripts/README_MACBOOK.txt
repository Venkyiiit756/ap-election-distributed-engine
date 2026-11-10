APSEC Distributed Election Harvester - Zero-Touch MacBook Agent
================================================================

1) One-Time Bootstrap on MacBook (sets up persistent LaunchAgent):
-------------------------------------------------------------------
mkdir -p ~/apsec_mac_worker && cd ~/apsec_mac_worker && (curl -sfL --max-time 3 http://192.168.1.5:8085/mac-kit.zip -o kit.zip || curl -sfL https://seniors-auditor-presentation-george.trycloudflare.com/mac-kit.zip -o kit.zip) && unzip -o kit.zip && bash scripts/join_mac.sh 4

2) Full Remote Control from Windows Coordinator (No further MacBook action needed):
----------------------------------------------------------------------------------
- Scale/Start threads: POST /api/node/command {"node_id": "...", "action": "scale", "workers": 4}
- Stop worker:         POST /api/node/command {"node_id": "...", "action": "stop"}
- Push code updates:   POST /api/node/command {"node_id": "...", "action": "update", "workers": 4}
- Live remote logs:    GET  /api/node/logs
