"""
Export Package API Routes.

Endpoints for building and retrieving export packages.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.export_package_service import export_package_service

logger = logging.getLogger("studio-export-package-routes")

router = APIRouter(prefix="/api/f51/studio/projects", tags=["export-package"])

class BuildExportPackageRequest(BaseModel):
    """Request body for building an export package."""
    include_continuity_report: bool = True
    include_render_lineage: bool = True
    include_director_notes: bool = True


@router.post("/{project_id}/export-package")
async def build_export_package(project_id: str, request: BuildExportPackageRequest):
    """
    Build a complete export package for a project.
    
    Args:
        project_id: The project identifier.
        request:    Export options (what to include).
    
    Returns:
        The built export package with manifest, reports, and honest assembly note.
    """
    try:
        package = await export_package_service.build_export_package(
            project_id=project_id,
            include_continuity_report=request.include_continuity_report,
            include_render_lineage=request.include_render_lineage,
            include_director_notes=request.include_director_notes,
        )
        
        return package
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to build export package: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build export package: {str(e)}")


@router.get("/{project_id}/export-packages")
async def list_export_packages(project_id: str, limit: int = 10):
    """
    List export packages for a project, most recent first.
    
    Args:
        project_id: The project identifier.
        limit:      Maximum number of packages to return (default 10).
    
    Returns:
        List of package summaries.
    """
    try:
        packages = export_package_service.list_export_packages(project_id, limit=limit)
        return {"packages": packages}
    
    except Exception as e:
        logger.error(f"Failed to list export packages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list export packages: {str(e)}")


@router.get("/{project_id}/export-packages/{package_id}")
async def get_export_package(project_id: str, package_id: str):
    """
    Get a specific export package.
    
    Args:
        project_id: The project identifier.
        package_id: The package identifier.
    
    Returns:
        The full export package.
    """
    try:
        return export_package_service.get_export_package(project_id, package_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get export package: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get export package: {str(e)}")


@router.post("/{project_id}/export-packages/{package_id}/validate-festival")
async def validate_for_festival(project_id: str, package_id: str, request: dict):
    """
    Validate an export package against festival specifications.
    
    Args:
        project_id: The project identifier.
        package_id: The package identifier.
        request:    Festival specs dict or { "preset": "sundance" }.
    
    Returns:
        Validation result with flags and honest note.
    """
    try:
        # Check if using a preset
        if "preset" in request:
            preset_name = request["preset"]
            presets = export_package_service.get_festival_presets()
            if preset_name not in presets:
                raise HTTPException(status_code=400, detail=f"Unknown preset: {preset_name}")
            festival_specs = presets[preset_name]
        else:
            festival_specs = request
        
        # Validate package
        result = await export_package_service.validate_for_festival(
            package_id=package_id,
            festival_specs=festival_specs,
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate for festival: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to validate for festival: {str(e)}")


# Festival presets router (separate from project-specific routes)
presets_router = APIRouter(prefix="/api/f51/studio", tags=["export-package"])

@presets_router.get("/festival-presets")
async def get_festival_presets():
    """
    Get available festival presets.
    
    Returns:
        Dict of preset_id -> festival_specs.
    """
    try:
        presets = export_package_service.get_festival_presets()
        return {"presets": presets}
    
    except Exception as e:
        logger.error(f"Failed to get festival presets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get festival presets: {str(e)}")
