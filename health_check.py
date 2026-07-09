#!/usr/bin/env python3
"""
AI Film Studio Health Check Script
===================================
Comprehensive health verification for the entire application stack.
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
import sqlite3

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

class HealthChecker:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.backend_dir = self.project_root / "studio-backend"
        self.frontend_dir = self.project_root / "studio-app"
        self.results = []
        
    def print_header(self, text: str):
        print(f"\n{BOLD}{BLUE}{'=' * 80}{RESET}")
        print(f"{BOLD}{BLUE}{text.center(80)}{RESET}")
        print(f"{BOLD}{BLUE}{'=' * 80}{RESET}\n")
    
    def print_section(self, text: str):
        print(f"\n{BOLD}{text}{RESET}")
        print("-" * 80)
    
    def print_result(self, check: str, passed: bool, message: str = ""):
        status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        self.results.append((check, passed, message))
        msg_part = f" - {message}" if message else ""
        print(f"  {status} {check}{msg_part}")
        
    def print_warning(self, message: str):
        print(f"  {YELLOW}⚠ WARNING{RESET} {message}")
    
    def print_info(self, message: str):
        print(f"  {BLUE}ℹ INFO{RESET} {message}")

    # =============================================================================
    # CHECK 1: Python Environment & Dependencies
    # =============================================================================
    def check_python_environment(self) -> bool:
        """Verify Python version and backend dependencies"""
        self.print_section("1. Python Environment & Dependencies")
        
        # Check Python version
        py_version = sys.version_info
        python_ok = py_version >= (3, 10)
        self.print_result(
            "Python version",
            python_ok,
            f"{py_version.major}.{py_version.minor}.{py_version.micro}"
        )
        
        # Check requirements.txt exists
        req_file = self.backend_dir / "requirements.txt"
        req_exists = req_file.exists()
        self.print_result("requirements.txt exists", req_exists, str(req_file))
        
        # Check critical dependencies
        critical_deps = ["fastapi", "uvicorn", "pydantic", "aiohttp", "sqlite3"]
        all_deps_ok = True
        
        for dep in critical_deps:
            try:
                if dep == "sqlite3":
                    import sqlite3
                else:
                    __import__(dep)
                self.print_result(f"Dependency: {dep}", True, "installed")
            except ImportError:
                self.print_result(f"Dependency: {dep}", False, "missing")
                all_deps_ok = False
        
        return python_ok and req_exists and all_deps_ok

    # =============================================================================
    # CHECK 2: Database Health
    # =============================================================================
    def check_database(self) -> bool:
        """Verify SQLite database accessibility and schema integrity"""
        self.print_section("2. Database Health Check")
        
        db_path = self.backend_dir / "data" / "studio.db"
        
        # Check database file exists
        db_exists = db_path.exists()
        self.print_result("Database file exists", db_exists, str(db_path))
        
        if not db_exists:
            return False
        
        try:
            # Connect to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            self.print_result("Database connection", True, "Connected")
            
            # Check critical tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            
            critical_tables = [
                "projects",
                "render_jobs",
                "sessions",
                "video_assets",
                "video_keyframes",
                "video_frame_analyses",
                "crew_tasks",
                "project_memories"
            ]
            
            all_tables_ok = True
            for table in critical_tables:
                exists = table in tables
                self.print_result(f"Table: {table}", exists)
                if not exists:
                    all_tables_ok = False
            
            # Check projects count
            cursor.execute("SELECT COUNT(*) FROM projects")
            project_count = cursor.fetchone()[0]
            self.print_info(f"Found {project_count} project(s) in database")
            
            # Check render jobs count
            cursor.execute("SELECT COUNT(*) FROM render_jobs")
            job_count = cursor.fetchone()[0]
            self.print_info(f"Found {job_count} render job(s) in database")
            
            conn.close()
            return all_tables_ok
            
        except Exception as e:
            self.print_result("Database query", False, str(e))
            return False

    # =============================================================================
    # CHECK 3: Backend Configuration
    # =============================================================================
    def check_backend_config(self) -> bool:
        """Verify backend configuration and environment variables"""
        self.print_section("3. Backend Configuration")
        
        # Check .env file
        env_file = self.backend_dir / ".env"
        env_exists = env_file.exists()
        self.print_result(".env file exists", env_exists, str(env_file))
        
        if env_exists:
            # Load and check critical env vars
            env_vars = {}
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()
            
            # Check Runway API key
            runway_key = env_vars.get("RUNWAYML_API_SECRET", "")
            has_runway = bool(runway_key and runway_key != "your_key_here")
            self.print_result(
                "Runway API credentials",
                has_runway,
                "Configured" if has_runway else "Missing or placeholder"
            )
            
            if not has_runway:
                self.print_warning("Runway API key not configured - video renders will fail")
        
        # Check main.py exists
        main_py = self.backend_dir / "main.py"
        main_exists = main_py.exists()
        self.print_result("main.py exists", main_exists, str(main_py))
        
        # Check app directory structure
        app_dir = self.backend_dir / "app"
        app_exists = app_dir.exists() and app_dir.is_dir()
        self.print_result("app/ directory exists", app_exists, str(app_dir))
        
        return env_exists and main_exists and app_exists

    # =============================================================================
    # CHECK 4: Frontend Configuration
    # =============================================================================
    def check_frontend_config(self) -> bool:
        """Verify frontend build configuration"""
        self.print_section("4. Frontend Configuration")
        
        # Check package.json
        package_json = self.frontend_dir / "package.json"
        package_exists = package_json.exists()
        self.print_result("package.json exists", package_exists, str(package_json))
        
        if package_exists:
            try:
                with open(package_json) as f:
                    package_data = json.load(f)
                
                # Check critical dependencies
                deps = package_data.get("dependencies", {})
                critical_deps = ["react", "react-dom", "react-router-dom"]
                
                all_deps_ok = True
                for dep in critical_deps:
                    exists = dep in deps
                    self.print_result(f"Dependency: {dep}", exists, deps.get(dep, "missing"))
                    if not exists:
                        all_deps_ok = False
                
            except json.JSONDecodeError as e:
                self.print_result("package.json parse", False, str(e))
                all_deps_ok = False
        else:
            all_deps_ok = False
        
        # Check node_modules
        node_modules = self.frontend_dir / "node_modules"
        modules_exist = node_modules.exists()
        self.print_result("node_modules installed", modules_exist, str(node_modules))
        
        if not modules_exist:
            self.print_warning("Run 'npm install' in studio-app/ to install dependencies")
        
        # Check vite.config.ts
        vite_config = self.frontend_dir / "vite.config.ts"
        vite_exists = vite_config.exists()
        self.print_result("vite.config.ts exists", vite_exists, str(vite_config))
        
        return package_exists and all_deps_ok and vite_exists

    # =============================================================================
    # CHECK 5: Asset URLs & File System
    # =============================================================================
    def check_assets(self) -> bool:
        """Verify asset directories and file accessibility"""
        self.print_section("5. Asset URLs & File System")
        
        # Check outputs directory
        outputs_dir = self.backend_dir / "outputs"
        outputs_exists = outputs_dir.exists()
        self.print_result("outputs/ directory exists", outputs_exists, str(outputs_dir))
        
        if outputs_exists:
            # Check subdirectories
            subdirs = ["video", "previs", "renders"]
            for subdir in subdirs:
                subdir_path = outputs_dir / subdir
                if subdir_path.exists():
                    file_count = len(list(subdir_path.glob("*")))
                    self.print_info(f"  {subdir}/ contains {file_count} file(s)")
        
        # Check data directory
        data_dir = self.backend_dir / "data"
        data_exists = data_dir.exists()
        self.print_result("data/ directory exists", data_exists, str(data_dir))
        
        # Check write permissions
        try:
            test_file = outputs_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            self.print_result("outputs/ write permission", True, "Writable")
        except Exception as e:
            self.print_result("outputs/ write permission", False, str(e))
            return False
        
        return outputs_exists and data_exists

    # =============================================================================
    # CHECK 6: API Endpoints (if server is running)
    # =============================================================================
    def check_api_endpoints(self) -> bool:
        """Check if FastAPI server is running and endpoints respond"""
        self.print_section("6. API Endpoints (Server Status)")
        
        try:
            import requests
        except ImportError:
            self.print_warning("'requests' library not installed - skipping endpoint checks")
            return True
        
        base_url = "http://localhost:8010"
        
        # Test health endpoint
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            health_ok = response.status_code == 200
            self.print_result("GET /health", health_ok, f"Status {response.status_code}")
            
            if health_ok:
                health_data = response.json()
                self.print_info(f"  Server status: {health_data.get('status', 'unknown')}")
                self.print_info(f"  Database: {health_data.get('components', {}).get('database', {}).get('status', 'unknown')}")
        except requests.exceptions.ConnectionError:
            self.print_result("GET /health", False, "Server not running")
            self.print_warning("Start the server with: cd studio-backend && python main.py")
            return False
        except Exception as e:
            self.print_result("GET /health", False, str(e))
            return False
        
        # Test other critical endpoints
        endpoints = [
            "/",
            "/api/f51/studio/projects",
            "/api/f51/studio/overview"
        ]
        
        all_ok = True
        for endpoint in endpoints:
            try:
                response = requests.get(f"{base_url}{endpoint}", timeout=5)
                ok = response.status_code in [200, 401]  # 401 is OK if auth is required
                self.print_result(f"GET {endpoint}", ok, f"Status {response.status_code}")
                if not ok:
                    all_ok = False
            except Exception as e:
                self.print_result(f"GET {endpoint}", False, str(e))
                all_ok = False
        
        return all_ok

    # =============================================================================
    # CHECK 7: Batch Features A-F
    # =============================================================================
    def check_batch_features(self) -> bool:
        """Verify all batch feature endpoints are present"""
        self.print_section("7. Batch Features A-F Endpoints")
        
        try:
            import requests
        except ImportError:
            self.print_warning("'requests' library not installed - skipping feature checks")
            return True
        
        base_url = "http://localhost:8010"
        
        # Feature endpoints mapping
        features = {
            "A - Projects": "/api/f51/studio/projects",
            "B - Crew Agents": "/api/f51/studio/crew/agents",
            "C - Memory System": "/api/f51/studio/memory",
            "D - Scene Intelligence": "/api/f51/studio/scene-intelligence",
            "E - Render Pipeline": "/api/f51/studio/render/jobs",
            "F - Production Board": "/api/f51/studio/overview"
        }
        
        all_ok = True
        for feature_name, endpoint in features.items():
            try:
                response = requests.get(f"{base_url}{endpoint}", timeout=5)
                ok = response.status_code in [200, 401, 404]  # 404 means endpoint exists but no data
                self.print_result(feature_name, ok, f"{endpoint} - Status {response.status_code}")
                if response.status_code not in [200, 401]:
                    all_ok = False
            except requests.exceptions.ConnectionError:
                self.print_result(feature_name, False, "Server not running")
                all_ok = False
                break
            except Exception as e:
                self.print_result(feature_name, False, str(e))
                all_ok = False
        
        return all_ok

    # =============================================================================
    # Main Execution
    # =============================================================================
    def run_all_checks(self):
        """Run all health checks"""
        self.print_header("AI FILM STUDIO - COMPREHENSIVE HEALTH CHECK")
        
        start_time = time.time()
        
        # Run all checks
        checks = [
            self.check_python_environment,
            self.check_database,
            self.check_backend_config,
            self.check_frontend_config,
            self.check_assets,
            self.check_api_endpoints,
            self.check_batch_features
        ]
        
        for check in checks:
            try:
                check()
            except Exception as e:
                self.print_result(check.__name__, False, f"Exception: {str(e)}")
        
        # Print summary
        self.print_header("HEALTH CHECK SUMMARY")
        
        total = len(self.results)
        passed = sum(1 for _, p, _ in self.results if p)
        failed = total - passed
        
        print(f"Total Checks: {total}")
        print(f"{GREEN}Passed: {passed}{RESET}")
        print(f"{RED}Failed: {failed}{RESET}")
        print(f"\nDuration: {time.time() - start_time:.2f}s")
        
        # Print recommendations
        if failed > 0:
            self.print_section("RECOMMENDATIONS")
            print("\nTo fix issues:")
            print("  1. Install Python dependencies: cd studio-backend && pip install -r requirements.txt")
            print("  2. Install Node dependencies: cd studio-app && npm install")
            print("  3. Start the backend server: cd studio-backend && python main.py")
            print("  4. Start the frontend dev server: cd studio-app && npm run dev")
            print("  5. Configure Runway API key in studio-backend/.env")
        
        return failed == 0


def main():
    checker = HealthChecker()
    success = checker.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
