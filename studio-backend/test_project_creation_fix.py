#!/usr/bin/env python3
"""
Quick test to verify project creation endpoint works correctly with JSON body.
"""
import os
import requests
import sqlite3
from pathlib import Path
from app.data.db_guard import open_db_readonly, open_db_readwrite, resolve_db_file
from datetime import datetime

API_BASE = "http://localhost:8010"
DB_PATH = resolve_db_file()  # guarded: live needs both opt-in flags

def test_project_creation():
    """Test project creation with correct JSON body format"""
    # Opt-in gate: this script POSTs to a live dev server AND opens the
    # live DB path directly. Never run by accident (incl. pytest root scope).
    if os.getenv("STUDIO_ALLOW_LIVE_SCRIPTS") != "1":
        print("REFUSING: set STUDIO_ALLOW_LIVE_SCRIPTS=1 to run this live-server script.")
        return False

    print("Testing Project Creation Endpoint")
    print("="*60)
    
    project_id = f"test_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Test with JSON body (CORRECT format)
    print("\n1. Creating project with JSON body...")
    response = requests.post(
        f"{API_BASE}/api/f51/studio/projects",
        json={
            "project_id": project_id,
            "title": "Test Project - JSON Body"
        },
        headers={"Content-Type": "application/json"}
    )
    
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ PASS: Project created via API")
        data = response.json()
        print(f"   Project ID: {data.get('project_id')}")
        print(f"   Title: {data.get('title')}")
    else:
        print(f"   ❌ FAIL: {response.text[:200]}")
        return False
    
    # Check persistence
    print("\n2. Checking database persistence...")
    if not DB_PATH.exists():
        print(f"   ❌ FAIL: Database not found at {DB_PATH}")
        return False
    
    conn = open_db_readwrite(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT project_id, data FROM projects WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        print(f"   ✅ PASS: Project persisted in database")
        print(f"   DB Record: {row[0]}")
        import json
        data = json.loads(row[1]) if row[1] else {}
        print(f"   Title from data: {data.get('title', 'N/A')}")
    else:
        print(f"   ❌ FAIL: Project not found in database")
        return False
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED - Project creation endpoint working correctly")
    print("="*60)
    return True

if __name__ == "__main__":
    success = test_project_creation()
    exit(0 if success else 1)
