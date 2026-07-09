#!/usr/bin/env python3
"""
Diagnostic script for Runway provider status
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Load .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from app.services.render import RenderService

def main():
    print("=" * 80)
    print("RUNWAY PROVIDER DIAGNOSTIC")
    print("=" * 80)
    
    # Check environment variables
    print("\n1. ENVIRONMENT VARIABLES:")
    print(f"   RUNWAYML_API_SECRET: {'SET' if os.getenv('RUNWAYML_API_SECRET') else 'NOT SET'}")
    if os.getenv('RUNWAYML_API_SECRET'):
        key = os.getenv('RUNWAYML_API_SECRET', '')
        print(f"   Key length: {len(key)}")
        print(f"   Key first 4: {key[:4]}")
        print(f"   Key last 4: {key[-4:]}")
    print(f"   RUNWAY_API_KEY: {'SET' if os.getenv('RUNWAY_API_KEY') else 'NOT SET'}")
    print(f"   RENDER_PROVIDER_TEST_MODE: {os.getenv('RENDER_PROVIDER_TEST_MODE', 'NOT SET')}")
    print(f"   APP_ENV: {os.getenv('APP_ENV', 'NOT SET')}")
    
    # Initialize render service
    print("\n2. RENDER SERVICE INITIALIZATION:")
    render_service = RenderService()
    
    # Get provider configs
    print("\n3. PROVIDER CONFIGURATIONS:")
    for provider_id, config in render_service._provider_configs.items():
        if provider_id == "runway":
            print(f"\n   Provider: {provider_id}")
            print(f"   - name: {config.name}")
            print(f"   - enabled: {config.enabled}")
            print(f"   - is_simulated: {config.is_simulated}")
            print(f"   - api_key present: {bool(config.api_key)}")
            if config.api_key:
                print(f"   - api_key length: {len(config.api_key)}")
            print(f"   - api_endpoint: {config.api_endpoint}")
            print(f"   - requires: {config.requires}")
            print(f"   - capabilities: {config.capabilities}")
    
    # Get provider status
    print("\n4. PROVIDER STATUS:")
    statuses = render_service.list_providers()
    for status in statuses:
        if status.provider_key == "runway":
            print(f"\n   Provider: {status.provider_key}")
            print(f"   - status: {status.status}")
            print(f"   - enabled: {status.enabled}")
            print(f"   - is_simulated: {status.is_simulated}")
            print(f"   - is_mock: {status.is_mock}")
            print(f"   - provider_mode: {status.provider_mode}")
            print(f"   - ready_for_hosted_generation: {status.ready_for_hosted_generation}")
            print(f"   - missing_requirements: {status.missing_requirements}")
            print(f"   - display_label: {status.display_label}")
    
    # Check conditions for ready_for_hosted_generation
    print("\n5. CONDITIONS FOR ready_for_hosted_generation = True:")
    print("   ALL of the following must be True:")
    
    runway_config = render_service._provider_configs.get("runway")
    test_mode = str(os.getenv("RENDER_PROVIDER_TEST_MODE", "")).strip().lower()
    
    if runway_config:
        missing_requirements = []
        if "api_key" in runway_config.requires and not (runway_config.api_key or "").strip():
            missing_requirements.append("api_key")
        if "api_endpoint" in runway_config.requires and not (runway_config.api_endpoint or "").strip():
            missing_requirements.append("api_endpoint")
        
        print(f"   ✓ config.enabled = {runway_config.enabled}")
        print(f"   ✓ not config.is_simulated = {not runway_config.is_simulated}")
        print(f"   ✓ not missing_requirements = {not missing_requirements} (missing: {missing_requirements})")
        print(f"   ✓ not (provider_id == 'runway' and test_mode == 'mock_success') = {not (test_mode == 'mock_success')}")
        
        all_conditions_met = (
            runway_config.enabled
            and not runway_config.is_simulated
            and not missing_requirements
            and not (test_mode == "mock_success")
        )
        
        print(f"\n   RESULT: ready_for_hosted_generation = {all_conditions_met}")
        
        if not all_conditions_met:
            print("\n   BLOCKING ISSUES:")
            if not runway_config.enabled:
                print("   ❌ Provider is not enabled")
            if runway_config.is_simulated:
                print("   ❌ Provider is marked as simulated")
            if missing_requirements:
                print(f"   ❌ Missing requirements: {missing_requirements}")
            if test_mode == "mock_success":
                print(f"   ❌ RENDER_PROVIDER_TEST_MODE is set to 'mock_success'")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
