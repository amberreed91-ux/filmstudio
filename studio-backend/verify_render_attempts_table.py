#!/usr/bin/env python3
"""
Verification script for render_attempts table schema.

Run this after starting the backend to verify migration 26 was applied.
"""

import sqlite3
import sys
from pathlib import Path

def verify_render_attempts_table():
    """Verify the render_attempts table exists with correct schema."""
    
    db_path = Path(__file__).parent / "studio.db"
    
    if not db_path.exists():
        print("❌ studio.db not found. Start the backend first to initialize the database.")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check current schema version
        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        version = cursor.fetchone()[0]
        print(f"✅ Current schema version: {version}")
        
        if version < 26:
            print(f"⚠️  Schema version {version} is less than 26. Migration not yet applied.")
            return False
        
        # Check table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='render_attempts'
        """)
        table = cursor.fetchone()
        
        if not table:
            print("❌ render_attempts table does not exist")
            return False
        
        print("✅ render_attempts table exists")
        
        # Check columns
        cursor.execute("PRAGMA table_info(render_attempts)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        expected_columns = {
            "shot_id": "TEXT",
            "attempt_n": "INTEGER",
            "prompt_text": "TEXT",
            "provider": "TEXT",
            "adherence_score": "REAL",
            "score_json": "TEXT",
            "diff_json": "TEXT",
            "created_at": "TEXT",
        }
        
        for col, col_type in expected_columns.items():
            if col not in columns:
                print(f"❌ Missing column: {col}")
                return False
            print(f"✅ Column exists: {col} ({columns[col]})")
        
        # Check indexes
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='render_attempts'
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        
        print(f"✅ Indexes: {indexes}")
        
        expected_indexes = ["idx_render_attempts_shot", "idx_render_attempts_created"]
        for idx in expected_indexes:
            if idx in indexes:
                print(f"✅ Index exists: {idx}")
            else:
                print(f"⚠️  Index missing: {idx}")
        
        # Check primary key
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='render_attempts'
        """)
        schema = cursor.fetchone()[0]
        
        if "PRIMARY KEY (shot_id, attempt_n)" in schema:
            print("✅ Primary key constraint exists: (shot_id, attempt_n)")
        else:
            print("⚠️  Primary key constraint not found")
        
        # Test insert
        test_shot_id = "__test_verification__"
        cursor.execute("DELETE FROM render_attempts WHERE shot_id = ?", (test_shot_id,))
        
        cursor.execute("""
            INSERT INTO render_attempts 
            (shot_id, attempt_n, prompt_text, provider, adherence_score)
            VALUES (?, ?, ?, ?, ?)
        """, (test_shot_id, 1, "test prompt", "runway", 0.95))
        
        cursor.execute("""
            SELECT shot_id, attempt_n, adherence_score 
            FROM render_attempts 
            WHERE shot_id = ?
        """, (test_shot_id,))
        
        row = cursor.fetchone()
        if row and row[0] == test_shot_id and row[2] == 0.95:
            print("✅ Insert and retrieval test passed")
        else:
            print("❌ Insert and retrieval test failed")
            return False
        
        # Clean up test data
        cursor.execute("DELETE FROM render_attempts WHERE shot_id = ?", (test_shot_id,))
        conn.commit()
        conn.close()
        
        print("\n✅ All verifications passed! render_attempts table is ready.")
        return True
        
    except Exception as e:
        print(f"❌ Error during verification: {e}")
        return False


if __name__ == "__main__":
    success = verify_render_attempts_table()
    sys.exit(0 if success else 1)
