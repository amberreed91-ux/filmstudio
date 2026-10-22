#!/usr/bin/env python3
"""
Verify that previs_images and surfaced_disagreements tables were created successfully.
"""
from pathlib import Path
from app.data.db_guard import open_db_readonly, open_db_readwrite, resolve_db_file

DB_PATH = resolve_db_file()  # guarded: live needs both opt-in flags

def verify_tables():
    """Verify both new tables exist with correct schema"""
    print("Verifying New Database Tables")
    print("="*60)
    
    if not DB_PATH.exists():
        print(f"❌ FAIL: Database not found at {DB_PATH}")
        return False
    
    conn = open_db_readonly(DB_PATH)
    cursor = conn.cursor()
    
    # Check if tables exist
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN ('previs_images', 'surfaced_disagreements')
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]
    
    print("\n1. Table Existence Check:")
    if 'previs_images' in tables:
        print("   ✅ previs_images table exists")
    else:
        print("   ❌ previs_images table MISSING")
        conn.close()
        return False
    
    if 'surfaced_disagreements' in tables:
        print("   ✅ surfaced_disagreements table exists")
    else:
        print("   ❌ surfaced_disagreements table MISSING")
        conn.close()
        return False
    
    # Check previs_images schema
    print("\n2. previs_images Schema:")
    cursor.execute("PRAGMA table_info(previs_images)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    expected_columns = {
        'id': 'TEXT',
        'project_id': 'TEXT',
        'scene_id': 'TEXT',
        'shot_id': 'TEXT',
        'image_path': 'TEXT',
        'job_id': 'TEXT',
        'status': 'TEXT',
        'prompt_used': 'TEXT',
        'fallback': 'INTEGER',
        'created_at': 'TEXT'
    }
    
    all_present = True
    for col, col_type in expected_columns.items():
        if col in columns:
            print(f"   ✅ {col} ({col_type})")
        else:
            print(f"   ❌ {col} MISSING")
            all_present = False
    
    if not all_present:
        conn.close()
        return False
    
    # Check surfaced_disagreements schema
    print("\n3. surfaced_disagreements Schema:")
    cursor.execute("PRAGMA table_info(surfaced_disagreements)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    expected_columns = {
        'id': 'TEXT',
        'project_id': 'TEXT',
        'disagreement_id': 'TEXT',
        'decision_type': 'TEXT',
        'surfaced_at': 'TEXT',
        'dismissed_at': 'TEXT'
    }
    
    all_present = True
    for col, col_type in expected_columns.items():
        if col in columns:
            print(f"   ✅ {col} ({col_type})")
        else:
            print(f"   ❌ {col} MISSING")
            all_present = False
    
    if not all_present:
        conn.close()
        return False
    
    # Check indexes
    print("\n4. Index Verification:")
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND tbl_name='previs_images'
        ORDER BY name
    """)
    previs_indexes = [row[0] for row in cursor.fetchall()]
    print(f"   previs_images indexes: {len(previs_indexes)} found")
    for idx in previs_indexes:
        print(f"      - {idx}")
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND tbl_name='surfaced_disagreements'
        ORDER BY name
    """)
    disagreement_indexes = [row[0] for row in cursor.fetchall()]
    print(f"   surfaced_disagreements indexes: {len(disagreement_indexes)} found")
    for idx in disagreement_indexes:
        print(f"      - {idx}")
    
    # Check migration was recorded
    print("\n5. Migration Record:")
    cursor.execute("""
        SELECT version, description, applied_at 
        FROM schema_migrations 
        WHERE version = 17
    """)
    migration = cursor.fetchone()
    if migration:
        print(f"   ✅ Migration 17 applied")
        print(f"      Description: {migration[1]}")
        print(f"      Applied at: {migration[2]}")
    else:
        print("   ❌ Migration 17 NOT recorded")
        conn.close()
        return False
    
    conn.close()
    
    print("\n" + "="*60)
    print("✅ ALL CHECKS PASSED - Both tables created successfully")
    print("="*60)
    return True

if __name__ == "__main__":
    success = verify_tables()
    exit(0 if success else 1)
