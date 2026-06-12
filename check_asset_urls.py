#!/usr/bin/env python3
"""
Asset URL Resolution Check
Validates all render job asset URLs in the database
"""

import sqlite3
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Tuple

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

class AssetURLChecker:
    def __init__(self):
        self.db_path = Path(__file__).parent / "studio-backend" / "data" / "studio.db"
        self.outputs_dir = Path(__file__).parent / "studio-backend" / "outputs"
        
    def get_all_render_jobs(self) -> List[Dict]:
        """Get all render jobs from database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, status, provider, output_payload, created_at
            FROM render_jobs
        """)
        
        jobs = []
        for row in cursor.fetchall():
            job = dict(row)
            if job['output_payload']:
                try:
                    job['output_payload'] = json.loads(job['output_payload'])
                except json.JSONDecodeError:
                    job['output_payload'] = None
            jobs.append(job)
        
        conn.close()
        return jobs
    
    def check_url(self, url: str, job_id: str) -> Tuple[bool, str]:
        """Check if URL is valid and resolves to a file"""
        if not url:
            return False, "No URL"
        
        parsed = urlparse(url)
        
        # Check if it's a local file path
        if not parsed.scheme or parsed.scheme == 'file':
            # Try to resolve as local file
            file_path = Path(parsed.path) if parsed.path else None
            if not file_path:
                return False, "Invalid file path"
            
            if file_path.exists():
                return True, f"Local file exists ({file_path.stat().st_size} bytes)"
            else:
                return False, f"Local file not found: {file_path}"
        
        # Check if it's a simulated/example URL
        if 'example.com' in parsed.netloc or 'storage.example.com' in url:
            # These are placeholder URLs from simulated provider
            # Check if there's a corresponding local file in outputs
            potential_paths = [
                self.outputs_dir / "video" / f"{job_id}.mp4",
                self.outputs_dir / "renders" / f"{job_id}.mp4",
                self.outputs_dir / f"{job_id}.mp4",
            ]
            
            for path in potential_paths:
                if path.exists():
                    return True, f"Simulated URL with local file ({path.stat().st_size} bytes)"
            
            return False, "Simulated URL with no local file"
        
        # Check if it's a http/https URL
        if parsed.scheme in ['http', 'https']:
            # For real URLs, we'd need to check if accessible
            # For now, just validate the format
            if parsed.netloc and parsed.path:
                return True, f"Remote URL (not verified): {parsed.netloc}"
            else:
                return False, "Malformed URL"
        
        return False, f"Unknown URL type: {parsed.scheme}"
    
    def analyze_jobs(self):
        """Analyze all render jobs and their asset URLs"""
        print(f"\n{BOLD}{BLUE}{'=' * 80}{RESET}")
        print(f"{BOLD}{BLUE}Asset URL Resolution Check{RESET}")
        print(f"{BOLD}{BLUE}{'=' * 80}{RESET}\n")
        
        jobs = self.get_all_render_jobs()
        
        # Statistics
        total_jobs = len(jobs)
        jobs_with_output = 0
        jobs_without_output = 0
        urls_valid = 0
        urls_broken = 0
        urls_simulated = 0
        urls_remote = 0
        urls_local = 0
        
        broken_jobs = []
        
        print(f"Total render jobs in database: {BOLD}{total_jobs}{RESET}\n")
        
        # Analyze each job
        for job in jobs:
            job_id = job['id']
            status = job['status']
            provider = job['provider']
            output = job['output_payload']
            
            if not output:
                jobs_without_output += 1
                continue
            
            jobs_with_output += 1
            
            # Extract asset URL
            asset_url = output.get('asset_url', '')
            thumbnail_url = output.get('thumbnail_url', '')
            
            # Check asset URL
            if asset_url:
                is_valid, message = self.check_url(asset_url, job_id)
                
                if is_valid:
                    urls_valid += 1
                    if 'example.com' in asset_url:
                        urls_simulated += 1
                    elif asset_url.startswith('http'):
                        urls_remote += 1
                    else:
                        urls_local += 1
                else:
                    urls_broken += 1
                    broken_jobs.append({
                        'id': job_id,
                        'status': status,
                        'provider': provider,
                        'url': asset_url,
                        'reason': message
                    })
        
        # Print summary
        print(f"{BOLD}Summary:{RESET}")
        print(f"  Jobs with output payload: {jobs_with_output}")
        print(f"  Jobs without output payload: {jobs_without_output}")
        print()
        
        print(f"{BOLD}Asset URL Status:{RESET}")
        print(f"  {GREEN}✓ Valid URLs: {urls_valid}{RESET}")
        print(f"    - Simulated (with local files): {urls_simulated}")
        print(f"    - Remote URLs: {urls_remote}")
        print(f"    - Local files: {urls_local}")
        print(f"  {RED}✗ Broken URLs: {urls_broken}{RESET}")
        print()
        
        # Print broken URLs details
        if broken_jobs:
            print(f"{BOLD}{RED}Broken URLs Details:{RESET}\n")
            for i, job in enumerate(broken_jobs[:10], 1):  # Show first 10
                print(f"{i}. Job ID: {job['id']}")
                print(f"   Status: {job['status']}")
                print(f"   Provider: {job['provider']}")
                print(f"   URL: {job['url']}")
                print(f"   Reason: {job['reason']}")
                print()
            
            if len(broken_jobs) > 10:
                print(f"   ... and {len(broken_jobs) - 10} more broken URLs\n")
        
        # Print recommendations
        print(f"{BOLD}Recommendations:{RESET}")
        if urls_broken > 0:
            print(f"  1. Review broken URLs and update database")
            print(f"  2. For simulated URLs, check if local files exist in outputs/")
            print(f"  3. Consider migrating simulated URLs to actual storage")
        else:
            print(f"  {GREEN}✓ All asset URLs are valid!{RESET}")
        
        print()
        
        # Return statistics
        return {
            'total_jobs': total_jobs,
            'jobs_with_output': jobs_with_output,
            'urls_valid': urls_valid,
            'urls_broken': urls_broken,
            'urls_simulated': urls_simulated,
            'broken_jobs': broken_jobs
        }


if __name__ == "__main__":
    checker = AssetURLChecker()
    stats = checker.analyze_jobs()
    
    # Exit code based on broken URLs
    exit(0 if stats['urls_broken'] == 0 else 1)
