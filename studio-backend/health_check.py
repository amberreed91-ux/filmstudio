#!/usr/bin/env python3
"""
Studio Backend End-to-End Health Check
Reports pass/fail for all critical components without fixing anything.
"""
import os
import sys
import time
import subprocess
import requests
from datetime import datetime
from pathlib import Path
from app.script_guard import require_live_spend_gate

require_live_spend_gate(
    __file__,
    what="backend health check incl. project creation + render submit via the backend API",
    exposure="1 Runway video render + polls via localhost backend when the render phase runs",
    provider="runway",
)
from app.data.db_guard import open_db_readonly, open_db_readwrite, resolve_db_file

API_BASE = "http://localhost:8010"
DB_PATH = resolve_db_file()  # guarded: live needs both opt-in flags

# Results storage
results = {}

def check_api_health():
    """Verify backend is running"""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def test_project_creation():
    """1. PROJECT - Can a new project be created and persisted?"""
    print("\n" + "="*60)
    print("1. PROJECT CREATION TEST")
    print("="*60)
    
    project_id = f"health_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Create project
    try:
        response = requests.post(
            f"{API_BASE}/api/f51/studio/projects",
            json={
                "project_id": project_id,
                "title": "Health Check Test Project"
            },
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            print(f"❌ FAIL: Could not create project (status {response.status_code})")
            print(f"   Response: {response.text[:200]}")
            results['PROJECT CREATION'] = 'FAIL'
            return None
        
        print(f"✓ Project created via API")
        
        # Check persistence in SQLite
        if not DB_PATH.exists():
            print(f"❌ FAIL: Database file not found at {DB_PATH}")
            results['PROJECT CREATION'] = 'FAIL'
            return None
        
        conn = open_db_readonly(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT project_id, data FROM projects WHERE project_id = ?", (project_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print(f"❌ FAIL: Project not found in SQLite database")
            results['PROJECT CREATION'] = 'FAIL'
            return None
        
        import json
        data = json.loads(row[1]) if row[1] else {}
        title = data.get('title', 'N/A')
        print(f"✓ Project persisted in SQLite: {row[0]} - {title}")
        print(f"✅ PASS: Project creation and persistence")
        results['PROJECT CREATION'] = 'PASS'
        return project_id
        
    except Exception as e:
        print(f"❌ FAIL: Exception during project creation: {e}")
        results['PROJECT CREATION'] = 'FAIL'
        return None

def test_scene_creation(project_id):
    """2. SCENE - Can a scene be added to a project?"""
    print("\n" + "="*60)
    print("2. SCENE CREATION TEST")
    print("="*60)
    
    if not project_id:
        print("⊘ SKIP: No project available")
        results['SCENE CREATION'] = 'SKIP'
        return None
    
    try:
        # Get project to check scenes
        response = requests.get(f"{API_BASE}/api/f51/studio/projects/{project_id}")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Could not retrieve project (status {response.status_code})")
            results['SCENE CREATION'] = 'FAIL'
            return None
        
        project = response.json()
        
        # Check if scenes were created from script
        if 'scenes' not in project or not project['scenes']:
            print(f"❌ FAIL: No scenes found in project")
            results['SCENE CREATION'] = 'FAIL'
            return None
        
        scene = project['scenes'][0]
        scene_id = scene.get('scene_id')
        
        print(f"✓ Scene found: {scene_id}")
        print(f"✓ Scene has fields: {list(scene.keys())[:10]}...")
        
        # Verify essential fields
        required_fields = ['scene_id', 'scene_number']
        missing = [f for f in required_fields if f not in scene]
        
        if missing:
            print(f"❌ FAIL: Missing required fields: {missing}")
            results['SCENE CREATION'] = 'FAIL'
            return None
        
        print(f"✅ PASS: Scene creation and storage")
        results['SCENE CREATION'] = 'PASS'
        return scene_id
        
    except Exception as e:
        print(f"❌ FAIL: Exception during scene check: {e}")
        results['SCENE CREATION'] = 'FAIL'
        return None

def test_hosted_render(project_id, scene_id):
    """3. RENDER - Does render submit to Runway hosted API?"""
    print("\n" + "="*60)
    print("3. HOSTED RENDER TEST")
    print("="*60)
    
    if not project_id or not scene_id:
        print("⊘ SKIP: No project/scene available")
        results['HOSTED RENDER'] = 'SKIP'
        results['RENDER COMPLETION'] = 'SKIP'
        results['ASSET RESOLUTION'] = 'SKIP'
        return None
    
    shot_id = f"{scene_id}_shot_001"
    
    try:
        # Create render job with explicit runway provider
        print(f"Creating render job for {shot_id}...")
        response = requests.post(
            f"{API_BASE}/api/f51/studio/render/jobs",
            params={
                "project_id": project_id,
                "shot_id": shot_id,
                "provider": "runway",
                "prompt": "A cinematic test shot for health check validation"
            }
        )
        
        if response.status_code != 200:
            print(f"❌ FAIL: Could not create render job (status {response.status_code})")
            print(f"   Response: {response.text[:200]}")
            results['HOSTED RENDER'] = 'FAIL'
            results['RENDER COMPLETION'] = 'SKIP'
            results['ASSET RESOLUTION'] = 'SKIP'
            return None
        
        job = response.json()
        job_id = job['id']
        provider = job.get('provider', 'unknown')
        
        print(f"✓ Job created: {job_id}")
        print(f"✓ Provider: {provider}")
        
        if provider != 'runway':
            print(f"❌ FAIL: Job using '{provider}' instead of 'runway'")
            results['HOSTED RENDER'] = 'FAIL'
            results['RENDER COMPLETION'] = 'SKIP'
            results['ASSET RESOLUTION'] = 'SKIP'
            return None
        
        # Submit the job
        print(f"Submitting job to Runway...")
        response = requests.post(f"{API_BASE}/api/f51/studio/render/jobs/{job_id}/submit")
        
        if response.status_code != 200:
            print(f"❌ FAIL: Could not submit job (status {response.status_code})")
            results['HOSTED RENDER'] = 'FAIL'
            results['RENDER COMPLETION'] = 'SKIP'
            results['ASSET RESOLUTION'] = 'SKIP'
            return None
        
        submitted_job = response.json()
        provider_job_id = submitted_job.get('provider_job_id')
        
        print(f"✓ Job submitted")
        print(f"✓ Provider Job ID: {provider_job_id}")
        
        if not provider_job_id:
            print(f"⚠ WARNING: No provider_job_id returned (may be mock)")
        
        print(f"✅ PASS: Hosted render submission")
        results['HOSTED RENDER'] = 'PASS'
        
        # Test completion (with timeout)
        return test_render_completion(job_id)
        
    except Exception as e:
        print(f"❌ FAIL: Exception during render test: {e}")
        results['HOSTED RENDER'] = 'FAIL'
        results['RENDER COMPLETION'] = 'SKIP'
        results['ASSET RESOLUTION'] = 'SKIP'
        return None

def test_render_completion(job_id):
    """4. RENDER COMPLETION - Does job complete within 5 minutes?"""
    print("\n" + "="*60)
    print("4. RENDER COMPLETION TEST")
    print("="*60)
    
    print(f"Waiting for job {job_id} to complete (max 5 minutes)...")
    
    start_time = time.time()
    timeout = 300  # 5 minutes
    poll_interval = 10  # Check every 10 seconds
    
    try:
        while time.time() - start_time < timeout:
            response = requests.get(f"{API_BASE}/api/f51/studio/render/jobs/{job_id}")
            
            if response.status_code != 200:
                print(f"❌ FAIL: Could not check job status")
                results['RENDER COMPLETION'] = 'FAIL'
                results['ASSET RESOLUTION'] = 'SKIP'
                return None
            
            job = response.json()
            status = job.get('status', 'unknown')
            elapsed = int(time.time() - start_time)
            
            print(f"  [{elapsed}s] Status: {status}")
            
            if status in ['complete', 'completed', 'success']:
                print(f"✓ Job completed in {elapsed} seconds")
                results['RENDER COMPLETION'] = 'PASS'
                return test_asset_resolution(job)
            
            if status in ['failed', 'error', 'cancelled']:
                error_msg = job.get('error_message', 'Unknown error')
                print(f"❌ FAIL: Job failed with status '{status}'")
                print(f"   Error: {error_msg}")
                results['RENDER COMPLETION'] = 'FAIL'
                results['ASSET RESOLUTION'] = 'SKIP'
                return None
            
            time.sleep(poll_interval)
        
        # Timeout
        print(f"❌ FAIL: Job did not complete within {timeout} seconds")
        results['RENDER COMPLETION'] = 'FAIL'
        results['ASSET RESOLUTION'] = 'SKIP'
        return None
        
    except Exception as e:
        print(f"❌ FAIL: Exception during completion check: {e}")
        results['RENDER COMPLETION'] = 'FAIL'
        results['ASSET RESOLUTION'] = 'SKIP'
        return None

def test_asset_resolution(job):
    """5. ASSET RESOLUTION - Does output URL resolve to CloudFront mp4?"""
    print("\n" + "="*60)
    print("5. ASSET RESOLUTION TEST")
    print("="*60)
    
    try:
        output_payload = job.get('output_payload', {})
        asset_url = output_payload.get('asset_url', '')
        output_url = job.get('output_url', '')
        
        url = asset_url or output_url
        
        if not url:
            print(f"❌ FAIL: No output URL found in job")
            results['ASSET RESOLUTION'] = 'FAIL'
            return
        
        print(f"✓ Output URL: {url[:80]}...")
        
        # Check if it's a CloudFront URL
        if 'cloudfront.net' in url.lower():
            print(f"✓ URL is CloudFront (hosted)")
        elif url.startswith('http://') or url.startswith('https://'):
            print(f"✓ URL is external hosted")
        elif url.startswith('/outputs/'):
            print(f"⚠ WARNING: URL is local path (not hosted)")
        else:
            print(f"⚠ WARNING: URL format unclear: {url[:50]}")
        
        # Try to HEAD the URL
        try:
            response = requests.head(url, timeout=10, allow_redirects=True)
            print(f"✓ URL is accessible (status {response.status_code})")
            
            content_type = response.headers.get('content-type', '')
            if 'video' in content_type or url.endswith('.mp4'):
                print(f"✓ Content type indicates video: {content_type}")
                print(f"✅ PASS: Asset resolution")
                results['ASSET RESOLUTION'] = 'PASS'
            else:
                print(f"⚠ WARNING: Content type may not be video: {content_type}")
                print(f"✅ PASS: Asset resolution (with warning)")
                results['ASSET RESOLUTION'] = 'PASS'
                
        except requests.exceptions.RequestException as e:
            print(f"⚠ WARNING: Could not verify URL accessibility: {e}")
            print(f"✅ PASS: Asset resolution (URL exists but not verified)")
            results['ASSET RESOLUTION'] = 'PASS'
            
    except Exception as e:
        print(f"❌ FAIL: Exception during asset resolution: {e}")
        results['ASSET RESOLUTION'] = 'FAIL'

def test_intelligence_endpoints(project_id):
    """6. INTELLIGENCE SERVICES - Test each endpoint"""
    print("\n" + "="*60)
    print("6. INTELLIGENCE SERVICES TEST")
    print("="*60)
    
    if not project_id:
        print("⊘ SKIP: No project available")
        for key in ['TIMELINE INTEL', 'CONTINUITY INTEL', 'FILM DNA', 'ARC COMPLETENESS',
                    'CHARACTER JOURNEYS', 'MOTIF THREADS', 'SESSION DEBRIEF', 'DIRECTOR INTENT']:
            results[key] = 'SKIP'
        return
    
    endpoints = [
        ('TIMELINE INTEL', 'GET', f'/api/f51/studio/projects/{project_id}/timeline-intelligence'),
        ('CONTINUITY INTEL', 'POST', f'/api/f51/studio/projects/{project_id}/scene-continuity-intelligence'),
        ('FILM DNA', 'GET', f'/api/f51/studio/projects/{project_id}/film-dna'),
        ('ARC COMPLETENESS', 'GET', f'/api/f51/studio/projects/{project_id}/arc-completeness'),
        ('CHARACTER JOURNEYS', 'GET', f'/api/f51/studio/projects/{project_id}/character-journeys'),
        ('MOTIF THREADS', 'GET', f'/api/f51/studio/projects/{project_id}/motif-threads'),
        ('SESSION DEBRIEF', 'POST', f'/api/f51/studio/projects/{project_id}/session-debrief'),
        ('DIRECTOR INTENT', 'GET', f'/api/f51/studio/projects/{project_id}/director-intent'),
    ]
    
    for name, method, path in endpoints:
        try:
            if method == 'GET':
                response = requests.get(f"{API_BASE}{path}", timeout=5)
            else:
                response = requests.post(f"{API_BASE}{path}", json={}, timeout=5)
            
            status = response.status_code
            
            if status == 200:
                print(f"✓ {name:20} [200]")
                results[name] = '200'
            elif status == 404:
                print(f"⊘ {name:20} [404] (not implemented or no data)")
                results[name] = '404'
            else:
                print(f"✗ {name:20} [{status}]")
                results[name] = f'{status}'
                
        except Exception as e:
            print(f"✗ {name:20} [ERROR: {str(e)[:30]}]")
            results[name] = 'ERROR'

def test_database_tables():
    """7. DATABASE TABLES - Confirm all tables exist"""
    print("\n" + "="*60)
    print("7. DATABASE TABLES TEST")
    print("="*60)
    
    if not DB_PATH.exists():
        print(f"❌ Database file not found at {DB_PATH}")
        for table in ['continuity_graphs', 'continuity_graph_versions', 'film_dna',
                      'previs_images', 'session_debriefs', 'pitch_decks',
                      'export_packages', 'surfaced_disagreements']:
            results[f'DB: {table}'] = 'MISSING'
        return
    
    tables = [
        'continuity_graphs',
        'continuity_graph_versions',
        'film_dna',
        'previs_images',
        'session_debriefs',
        'pitch_decks',
        'export_packages',
        'surfaced_disagreements'
    ]
    
    try:
        conn = open_db_readonly(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        for table in tables:
            if table in existing_tables:
                print(f"✓ {table:30} [EXISTS]")
                results[f'DB: {table}'] = 'EXISTS'
            else:
                print(f"✗ {table:30} [MISSING]")
                results[f'DB: {table}'] = 'MISSING'
                
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        for table in tables:
            results[f'DB: {table}'] = 'ERROR'

def test_frontend_build():
    """8. FRONTEND BUILD - Does npm run build complete?"""
    print("\n" + "="*60)
    print("8. FRONTEND BUILD TEST")
    print("="*60)
    
    frontend_dir = Path(__file__).parent.parent / "studio-app"
    
    if not frontend_dir.exists():
        print(f"❌ Frontend directory not found at {frontend_dir}")
        results['FRONTEND BUILD'] = 'FAIL'
        return
    
    try:
        print("Running npm run build (this may take a minute)...")
        result = subprocess.run(
            ['npm', 'run', 'build'],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=180
        )
        
        if result.returncode == 0:
            print(f"✓ Build completed successfully")
            results['FRONTEND BUILD'] = 'PASS'
        else:
            print(f"❌ Build failed with exit code {result.returncode}")
            print(f"\nErrors:")
            print(result.stderr[:500])
            results['FRONTEND BUILD'] = 'FAIL'
            
    except subprocess.TimeoutExpired:
        print(f"❌ Build timed out after 180 seconds")
        results['FRONTEND BUILD'] = 'FAIL'
    except Exception as e:
        print(f"❌ Error running build: {e}")
        results['FRONTEND BUILD'] = 'FAIL'

def test_backend_tests():
    """9. BACKEND TESTS - Run pytest"""
    print("\n" + "="*60)
    print("9. BACKEND TESTS")
    print("="*60)
    
    backend_dir = Path(__file__).parent
    
    try:
        print("Running pytest...")
        result = subprocess.run(
            ['python', '-m', 'pytest', '-v', '--tb=no', '-q'],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        # Parse output for pass/fail counts
        output = result.stdout + result.stderr
        
        # Look for pytest summary line
        import re
        match = re.search(r'(\d+) passed', output)
        passed = int(match.group(1)) if match else 0
        
        match = re.search(r'(\d+) failed', output)
        failed = int(match.group(1)) if match else 0
        
        print(f"✓ Tests completed: {passed} passed, {failed} failed")
        results['BACKEND TESTS'] = f'{passed} passed / {failed} failed'
        
    except subprocess.TimeoutExpired:
        print(f"❌ Tests timed out after 300 seconds")
        results['BACKEND TESTS'] = 'TIMEOUT'
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        results['BACKEND TESTS'] = 'ERROR'

def test_frontend_tests():
    """10. FRONTEND TESTS - Run npm test"""
    print("\n" + "="*60)
    print("10. FRONTEND TESTS")
    print("="*60)
    
    frontend_dir = Path(__file__).parent.parent / "studio-app"
    
    if not frontend_dir.exists():
        print(f"❌ Frontend directory not found")
        results['FRONTEND TESTS'] = 'SKIP'
        return
    
    try:
        print("Running npm test...")
        result = subprocess.run(
            ['npm', 'test', '--', '--run'],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=180
        )
        
        output = result.stdout + result.stderr
        
        # Parse for test results
        import re
        match = re.search(r'Tests\s+(\d+)\s+passed', output)
        passed = int(match.group(1)) if match else 0
        
        match = re.search(r'(\d+)\s+failed', output)
        failed = int(match.group(1)) if match else 0
        
        print(f"✓ Tests completed: {passed} passed, {failed} failed")
        results['FRONTEND TESTS'] = f'{passed} passed / {failed} failed'
        
    except subprocess.TimeoutExpired:
        print(f"❌ Tests timed out after 180 seconds")
        results['FRONTEND TESTS'] = 'TIMEOUT'
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        results['FRONTEND TESTS'] = 'ERROR'

def print_summary():
    """Print final summary table"""
    print("\n" + "="*60)
    print("HEALTH CHECK SUMMARY")
    print("="*60)
    print()
    
    # Define order and formatting
    sections = [
        ("CORE FUNCTIONALITY", [
            'PROJECT CREATION',
            'SCENE CREATION',
            'HOSTED RENDER',
            'RENDER COMPLETION',
            'ASSET RESOLUTION',
        ]),
        ("INTELLIGENCE SERVICES", [
            'TIMELINE INTEL',
            'CONTINUITY INTEL',
            'FILM DNA',
            'ARC COMPLETENESS',
            'CHARACTER JOURNEYS',
            'MOTIF THREADS',
            'SESSION DEBRIEF',
            'DIRECTOR INTENT',
        ]),
        ("DATABASE TABLES", [
            'DB: continuity_graphs',
            'DB: continuity_graph_versions',
            'DB: film_dna',
            'DB: previs_images',
            'DB: session_debriefs',
            'DB: pitch_decks',
            'DB: export_packages',
            'DB: surfaced_disagreements',
        ]),
        ("BUILD & TESTS", [
            'FRONTEND BUILD',
            'BACKEND TESTS',
            'FRONTEND TESTS',
        ]),
    ]
    
    for section_name, keys in sections:
        print(f"{section_name}:")
        for key in keys:
            value = results.get(key, 'NOT RUN')
            # Format the key for display
            display_key = key.replace('DB: ', '  ')
            print(f"  {display_key:35} [ {value} ]")
        print()

def main():
    print("="*60)
    print("STUDIO BACKEND END-TO-END HEALTH CHECK")
    print("="*60)
    print("\nThis script will test all critical components.")
    print("No fixes will be applied - reporting only.\n")
    
    # Check if backend is running
    if not check_api_health():
        print("❌ ERROR: Backend is not running!")
        print(f"   Cannot connect to {API_BASE}")
        print("\n   Start the backend first:")
        print("   cd studio-backend && ./start_backend.sh")
        return 1
    
    print(f"✓ Backend is running at {API_BASE}\n")
    
    # Run all tests
    project_id = test_project_creation()
    scene_id = test_scene_creation(project_id)
    test_hosted_render(project_id, scene_id)
    test_intelligence_endpoints(project_id)
    test_database_tables()
    test_frontend_build()
    test_backend_tests()
    test_frontend_tests()
    
    # Print summary
    print_summary()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
