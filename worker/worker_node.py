import os
import sys
import time
import json
import sqlite3
import argparse
import socket
import concurrent.futures

sys.stdout.reconfigure(encoding="utf-8")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "coordinator", "registry.sqlite")

class WorkerNode:
    def __init__(self, node_id, workers_count=24):
        self.node_id = node_id
        self.workers_count = workers_count
        self.hostname = socket.gethostname()
        self.ip_address = socket.gethostbyname(self.hostname)
        self.current_ac = None
        self.voters_harvested = 0
        self.start_time = time.time()

    def register_heartbeat(self, rate=0.0):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO worker_nodes (node_id, hostname, ip_address, workers_count, last_heartbeat, current_ac, rate_voters_per_sec, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
            ON CONFLICT(node_id) DO UPDATE SET
                last_heartbeat=excluded.last_heartbeat,
                current_ac=excluded.current_ac,
                rate_voters_per_sec=excluded.rate_voters_per_sec,
                status='ACTIVE'
            """, (self.node_id, self.hostname, self.ip_address, self.workers_count, time.time(), self.current_ac, rate))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Worker Heartbeat Error] {e}")

    def claim_next_ac(self):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = time.time()
        # Find next pending AC or expired lease
        cur.execute("""
        SELECT ac_no, ac_slug, ac_name FROM constituencies
        WHERE status = 'PENDING' OR (status = 'LEASED' AND lease_expires_at < ?)
        ORDER BY ac_no ASC LIMIT 1
        """, (now,))
        row = cur.fetchone()
        if row:
            ac_no, ac_slug, ac_name = row
            # Lease for 45 minutes
            cur.execute("""
            UPDATE constituencies SET status = 'LEASED', assigned_node = ?, lease_expires_at = ?, updated_at = ?
            WHERE ac_no = ?
            """, (self.node_id, now + 2700, now, ac_no))
            conn.commit()
            conn.close()
            self.current_ac = ac_no
            return ac_no, ac_slug, ac_name
        conn.close()
        return None, None, None

    def run(self):
        print(f"===========================================================")
        print(f"[Node {self.node_id}] Started on {self.hostname} ({self.ip_address})")
        print(f"[Node {self.node_id}] Thread Pool: {self.workers_count} concurrent workers")
        print(f"===========================================================")
        self.register_heartbeat()

        while True:
            ac_no, ac_slug, ac_name = self.claim_next_ac()
            if not ac_no:
                print(f"[Node {self.node_id}] No pending ACs available. Sleeping 30s...")
                self.register_heartbeat(rate=0.0)
                time.sleep(30)
                continue

            print(f"\n--> [Node {self.node_id}] Claimed AC {ac_no}: {ac_name} ({ac_slug})")
            # Execute processing loop...
            self.register_heartbeat(rate=42.5)
            time.sleep(5) # Simulation step for coordinator loop

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed Worker Node")
    parser.add_argument("--node-id", type=str, default=f"node-{socket.gethostname().lower()}", help="Unique identifier for this laptop/server")
    parser.add_argument("--workers", type=int, default=24, help="Number of concurrent worker threads")
    args = parser.parse_args()

    node = WorkerNode(args.node_id, args.workers)
    node.register_heartbeat()
    print(f"Worker node initialized and registered into SQLite coordinator.")
