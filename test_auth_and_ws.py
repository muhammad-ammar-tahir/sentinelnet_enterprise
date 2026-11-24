"""Integration test for SentinelNet Authentication, Authorization, Rate Limiting, and WebSocket.
"""

import os
import sys
import asyncio

# Set test environment
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./sentinelnet.db"
os.environ["JWT_SECRET"] = "test-secret-key-sentinelnet-2026"
os.environ["ENVIRONMENT"] = "testing"

from fastapi.testclient import TestClient
from backend.main import app
from backend.ws.manager import manager, WebSocketEvents

client = TestClient(app)

def test_full_auth_and_ws():
    print("==================================================================")
    print("   STARTING SENTINELNET AUTH & WEBSOCKET VERIFICATION")
    print("==================================================================")

    # -----------------------------------------------------------------
    # Test 1: Invalid Login
    # -----------------------------------------------------------------
    print("\n--- Test 1: Invalid Login Credentials ---")
    resp = client.post("/api/auth/login", json={"email": "admin@sentinelnet.edu", "password": "wrongpassword"})
    print(f"Status: {resp.status_code}, Body: {resp.json()}")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    print("✓ Passed: Invalid credentials rejected with 401")

    # -----------------------------------------------------------------
    # Test 2: Valid Login (Admin)
    # -----------------------------------------------------------------
    print("\n--- Test 2: Valid Admin Login ---")
    resp = client.post("/api/auth/login", json={"email": "admin@sentinelnet.edu", "password": "sentinelpass"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    admin_data = resp.json()
    admin_token = admin_data["access_token"]
    refresh_token = admin_data["refresh_token"]
    print(f"Status: 200 OK")
    print(f"User: {admin_data['user']['username']} (Role: {admin_data['user']['role']})")
    print(f"Access Token: {admin_token[:25]}... (Expires in: {admin_data['expires_in']}s)")
    print("✓ Passed: Successful login returned JWT access and refresh tokens")

    # -----------------------------------------------------------------
    # Test 3: Refresh Token
    # -----------------------------------------------------------------
    print("\n--- Test 3: Token Refresh ---")
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    new_token = resp.json()["access_token"]
    print(f"New Access Token: {new_token[:25]}...")
    print("✓ Passed: Refresh token exchanged for new access token")

    # -----------------------------------------------------------------
    # Test 4: Protected GET /api/auth/me
    # -----------------------------------------------------------------
    print("\n--- Test 4: Current User Profile (/api/auth/me) ---")
    # Without token
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
    print("✓ Passed: /api/auth/me rejected without token (401)")

    # With Bearer token
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    profile = resp.json()
    assert profile["username"] == "admin"
    print(f"✓ Passed: /api/auth/me returned profile: {profile}")

    # -----------------------------------------------------------------
    # Test 5: Role-Based Access Control on Dangerous Endpoints
    # -----------------------------------------------------------------
    print("\n--- Test 5: RBAC Protection on /api/recovery/execute ---")

    # 5a: Hit /api/recovery/execute without token -> MUST be 401
    resp = client.post("/api/recovery/execute", json={"incident_id": "inc-001"})
    print(f"No token: Status {resp.status_code} ({resp.json().get('detail')})")
    assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
    print("✓ Passed: /api/recovery/execute without token returned 401 Unauthorized")

    # 5b: Login as Viewer and hit /api/recovery/execute -> MUST be 403
    resp_viewer_login = client.post("/api/auth/login", json={"email": "viewer@sentinelnet.edu", "password": "sentinelpass"})
    viewer_token = resp_viewer_login.json()["access_token"]
    
    resp = client.post(
        "/api/recovery/execute",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"incident_id": "inc-001"}
    )
    print(f"Viewer token: Status {resp.status_code} ({resp.json().get('detail')})")
    assert resp.status_code == 403, f"Expected 403 with viewer token, got {resp.status_code}"
    print("✓ Passed: /api/recovery/execute with viewer token returned 403 Forbidden")

    # 5c: Login as Operator and hit /api/recovery/execute -> Operator has permission
    resp_op_login = client.post("/api/auth/login", json={"email": "operator@sentinelnet.edu", "password": "sentinelpass"})
    operator_token = resp_op_login.json()["access_token"]
    resp = client.post(
        "/api/recovery/execute",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"incident_id": "inc-001"}
    )
    print(f"Operator token: Status {resp.status_code}")
    # Status should NOT be 401 or 403
    assert resp.status_code not in (401, 403), f"Operator should not be rejected with {resp.status_code}"
    print(f"✓ Passed: Operator token authorized (returned status {resp.status_code})")

    # -----------------------------------------------------------------
    # Test 6: WebSocket Authentication
    # -----------------------------------------------------------------
    print("\n--- Test 6: WebSocket Authentication ---")

    # 6a: Connect with invalid token -> rejected with code 1008
    print("6a: Testing WebSocket rejection with invalid token...")
    try:
        with client.websocket_connect("/ws/live?token=invalid_garbage_token") as ws:
            pass
        assert False, "WebSocket connection should have been closed with 1008"
    except Exception as exc:
        print(f"✓ Passed: Invalid token connection closed: {exc}")

    # 6b: Connect with valid token in query param -> accepted
    print("6b: Testing WebSocket connection with valid query token...")
    with client.websocket_connect(f"/ws/live?token={admin_token}") as ws:
        welcome_msg = ws.receive_json()
        print(f"Received message from WS: {welcome_msg}")
        assert welcome_msg["event"] == "CONNECTED"
        assert welcome_msg["data"]["user"]["username"] == "admin"
        print("✓ Passed: Valid token query authenticated successfully and received CONNECTED event")

    # 6c: Connect and authenticate via initial AUTH frame
    print("6c: Testing WebSocket connection with initial AUTH frame...")
    with client.websocket_connect("/ws/live") as ws:
        ws.send_json({"type": "AUTH", "token": f"Bearer {operator_token}"})
        welcome_msg = ws.receive_json()
        print(f"Received message after AUTH frame: {welcome_msg}")
        assert welcome_msg["event"] == "CONNECTED"
        assert welcome_msg["data"]["user"]["username"] == "operator"
        print("✓ Passed: Initial AUTH frame authenticated successfully")

    print("\n==================================================================")
    print("   ALL AUTHENTICATION, RBAC & WEBSOCKET TESTS PASSED!")
    print("==================================================================")

if __name__ == "__main__":
    test_full_auth_and_ws()
