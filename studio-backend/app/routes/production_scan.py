from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any

from app.models.production_scan import ProductionScanReport
from app.services.production_scan_service import production_scan_service

router = APIRouter(
    prefix="/api/f51/studio/projects/{project_id}/scan",
    tags=["production-scan"]
)

@router.post("", response_model=ProductionScanReport)
async def run_production_scan(project_id: str):
    """
    Run a full production readiness scan for the specified project.
    """
    try:
        report = await production_scan_service.run_scan(project_id)
        return report
    except Exception as e:
        import logging
        logging.getLogger("studio-api").error(f"Production scan failed for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{scan_id}", response_model=ProductionScanReport)
async def get_production_scan_report(project_id: str, scan_id: str):
    """
    Retrieve a specific production scan report.
    (Note: Current implementation regenerates or would fetch from history if implemented)
    """
    # For now, we'll just run a new one since we don't have persistence for scans yet
    return await run_production_scan(project_id)
