#!/usr/bin/env python3
"""
One-time migration script to backfill orphaned study references.

This script queries for orphaned StudyReference records and links them to the active project.

NOTE: After analysis, StudyReference objects are stored within the project's 
reference_study_library.studies array in the project JSON. There is no separate 
table for study references. The upload bug prevented references from being saved 
at all (they were created but never linked to any project), so there are no 
orphaned records to backfill from the database.

Previously uploaded references were lost due to the bug and will need to be 
re-uploaded after the fix.
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.storage import SQLiteStorage
from app.models import StudioProject, StudyReference, ReferenceStudyLibrary


def main():
    """Main migration function."""
    storage = SQLiteStorage()
    
    # Get all project IDs
    project_ids = storage.list_project_ids()
    
    if not project_ids:
        print("No projects found in database.")
        return
    
    # Use the first/only project ID
    target_project_id = project_ids[0]
    print(f"Using project ID: {target_project_id}")
    
    # Load the project
    project = storage.get_project(target_project_id)
    if not project:
        print(f"Project {target_project_id} not found.")
        return
    
    # Initialize reference_study_library if needed
    if project.reference_study_library is None:
        project.reference_study_library = ReferenceStudyLibrary(studies=[])
    
    existing_study_ids = {s.reference_id for s in project.reference_study_library.studies}
    
    print(f"Project has {len(project.reference_study_library.studies)} existing study references.")
    print(f"Existing study IDs: {existing_study_ids}")
    
    # StudyReference objects are stored within the project's reference_study_library.studies array.
    # There is no separate table for orphaned references. The upload bug prevented uploaded references
    # from being saved at all (they were created but never linked to any project), so there are no
    # orphaned records to backfill from the database.
    
    print("\n" + "="*60)
    print("BACKFILL RESULT")
    print("="*60)
    print("Linked 0 orphaned references to project [{}].".format(target_project_id))
    print("\nREASON:")
    print("StudyReference objects are stored in the project's reference_study_library.studies array.")
    print("The upload bug prevented references from being saved to the project at all.")
    print("Previously uploaded references were lost and will need to be re-uploaded.")
    print("Future uploads will be correctly linked after the fix.")
    print("="*60)


if __name__ == "__main__":
    main()
