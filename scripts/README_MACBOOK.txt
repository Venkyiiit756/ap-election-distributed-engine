APSEC Distributed Election Harvester - MacBook Worker Kit
==========================================================

Option A (Fastest): Paste into Antigravity on MacBook
-----------------------------------------------------
"Download http://192.168.1.5:8085/mac-kit.zip (or fallback https://seniors-auditor-presentation-george.trycloudflare.com/mac-kit.zip), unzip to ~/apsec_mac_worker, and run bash ~/apsec_mac_worker/scripts/join_mac.sh 4 in the background."

Option B: Direct Terminal (macOS)
---------------------------------
  bash scripts/join_mac.sh 4

Or explicitly point to Coordinator URL:
  python3 -u worker/worker_node.py --coordinator-url http://192.168.1.5:8085 --workers 4

Fallback Cloudflare Tunnel URL (if LAN port 8085 is blocked by Windows Firewall):
  python3 -u worker/worker_node.py --coordinator-url https://seniors-auditor-presentation-george.trycloudflare.com --workers 4
