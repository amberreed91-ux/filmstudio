#!/usr/bin/env python3
"""
Test script to verify Runway provider is working and create a test render
"""
import os
import sys
import requests
import json
from datetime import datetime

API_BASE = "http://localhost:8010"

def check_providers():
    """Check provider status"""
    print("=" * 60)
    print("CHECKING PROVIDER STATUS")
    print("=" * 60)
    
    response = requests.get(f"{API_BASE}/api/f51/studio/render/providers")
    providers = response.json()
    
    for provider in providers:
        print(f"\nProvider: {provider['name']}")
        print(f"  ID: {provider['provider_id']}")
        print(f"  Enabled: {provider['enabled']}")
        print(f"  Mode: {provider['provider_mode']}")
        print(f"  Ready for hosted: {provider['ready_for_hosted_generation']}")
        print(f"  Is mock: {provider['is_mock']}")
        print(f"  Is simulated: {provider['is_simulated']}")
        print(f"  Display: {provider['display_label']}")
    
    # Find Runway
    runway = next((p for p in providers if p['provider_id'] == 'runway'), None)
    if not runway:
        print("\n❌ ERROR: Runway provider not found!")
        return False
    
    if not runway['ready_for_hosted_generation']:
        print(f"\n❌ ERROR: Runway not ready for hosted generation!")
        print(f"   Missing: {runway['missing_requirements']}")
        return False
    
    print(f"\n✅ Runway is ready for hosted generation!")
    return True

def create_test_render():
    """Create a test render job with Runway"""
    print("\n" + "=" * 60)
    print("CREATING TEST RENDER WITH RUNWAY")
    print("=" * 60)
    
    # Create job parameters
    shot_id = f"test_runway_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    project_id = "proj-001"
    provider = "runway"
    prompt = "A serene mountain landscape at sunset, cinematic wide shot"
    
    print(f"\nCreating render job:")
    print(f"  Project: {project_id}")
    print(f"  Shot: {shot_id}")
    print(f"  Provider: {provider}")
    print(f"  Prompt: {prompt}")
    
    # Create the job with query parameters
    params = {
        "project_id": project_id,
        "shot_id": shot_id,
        "provider": provider,
        "prompt": prompt
    }
    
    response = requests.post(
        f"{API_BASE}/api/f51/studio/render/jobs",
        params=params
    )
    
    if response.status_code != 200:
        print(f"\n❌ ERROR: Failed to create job!")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        return None
    
    job = response.json()
    print(f"\n✅ Job created successfully!")
    print(f"   Job ID: {job['id']}")
    print(f"   Provider: {job['provider']}")
    print(f"   Status: {job['status']}")
    
    return job['id']

def submit_job(job_id):
    """Submit the job for rendering"""
    print("\n" + "=" * 60)
    print(f"SUBMITTING JOB: {job_id}")
    print("=" * 60)
    
    response = requests.post(
        f"{API_BASE}/api/f51/studio/render/jobs/{job_id}/submit"
    )
    
    if response.status_code != 200:
        print(f"\n❌ ERROR: Failed to submit job!")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        return False
    
    job = response.json()
    print(f"\n✅ Job submitted successfully!")
    print(f"   Job ID: {job['id']}")
    print(f"   Provider: {job['provider']}")
    print(f"   Status: {job['status']}")
    print(f"   Provider Job ID: {job.get('provider_job_id', 'N/A')}")
    
    return True

def main():
    print("\n🎬 RUNWAY PROVIDER TEST SCRIPT")
    print("=" * 60)
    
    # Check if backend is running
    try:
        response = requests.get(f"{API_BASE}/health", timeout=2)
        if response.status_code != 200:
            print("❌ Backend is not healthy!")
            return 1
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to backend at {API_BASE}")
        print(f"   Error: {e}")
        print("\n   Make sure the backend is running:")
        print("   cd studio-backend && ./start_backend.sh")
        return 1
    
    print(f"✅ Backend is running at {API_BASE}\n")
    
    # Check providers
    if not check_providers():
        return 1
    
    # Create test render
    job_id = create_test_render()
    if not job_id:
        return 1
    
    # Submit the job
    if not submit_job(job_id):
        return 1
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE!")
    print("=" * 60)
    print(f"\nYour test render has been submitted to Runway.")
    print(f"Job ID: {job_id}")
    print(f"\nCheck the backend logs to see the Runway API interaction:")
    print(f"  Look for 'Runway task_id captured' in the logs")
    print(f"\nOr check the job status:")
    print(f"  curl http://localhost:8010/api/f51/studio/render/jobs/{job_id}")
    
    return 0

if __name__ == "__main__":
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from app.script_guard import require_live_spend_gate

    require_live_spend_gate(
        __file__,
        what="create + submit a test render job to Runway via the local backend API",
        exposure="1 Runway video render + polls via localhost backend",
        provider="runway",
    )
    sys.exit(main())
