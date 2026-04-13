import requests
import json
import time

BASE_URL = "http://localhost:8081"
HEADERS = {
    "CF-Access-Jwt-Assertion": "test-token",
    "CF-Access-Authenticated-User-Email": "test@example.com",
    "Content-Type": "application/json"
}

def run_test():
    session_id = None
    try:
        # 1. Manual Unlock
        unlock_res = requests.post(f"{BASE_URL}/api/v2/control/manual-unlock", headers=HEADERS, json={"method": "cloudflare"})
        unlock_data = unlock_res.json()
        session_id = unlock_data.get("session_id")
        print(f"Unlock Result: {unlock_res.status_code}, Session: {session_id}")

        # 2. Emergency Clear
        clear_res = requests.post(f"{BASE_URL}/api/v2/control/emergency_clear", headers=HEADERS, json={"confirmation": True, "reason": "post-firmware-sync diagnostic"})
        print(f"Emergency Clear: {clear_res.status_code}")

        # 3. Capture BEFORE
        endpoints = [
            "/api/v2/hardware/robohat",
            "/api/v2/dashboard/telemetry",
            "/api/v2/fusion/state"
        ]
        before = {ep: requests.get(f"{BASE_URL}{ep}", headers=HEADERS).json() for ep in endpoints}

        # 4. Drive
        drive_payload = {
            "session_id": session_id,
            "vector": {"linear": 0.4, "angular": 0.0},
            "duration_ms": 250,
            "reason": "post-firmware-sync diagnostic",
            "max_speed_limit": 0.5
        }
        drive_res = requests.post(f"{BASE_URL}/api/v2/control/drive", headers=HEADERS, json=drive_payload)
        print(f"Drive Result: {drive_res.status_code}")

        # 5. Brief Wait and Capture AFTER
        time.sleep(0.3)
        after = {ep: requests.get(f"{BASE_URL}{ep}", headers=HEADERS).json() for ep in endpoints}

        # Summary bits
        print("\nSummary:")
        for ep in endpoints:
            print(f"--- {ep} ---")
            print(f"Before: {json.dumps(before[ep])[:200]}...")
            print(f"After:  {json.dumps(after[ep])[:200]}...")

    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        # 6. Emergency Stop
        if session_id:
            stop_res = requests.post(f"{BASE_URL}/api/v2/control/emergency", headers=HEADERS, json={"session_id": session_id})
            print(f"Final Emergency Stop: {stop_res.status_code}")

if __name__ == "__main__":
    run_test()
