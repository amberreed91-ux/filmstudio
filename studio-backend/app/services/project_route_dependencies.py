"""Dependency wiring for project-domain services used by the route layer."""

from app.data.storage import get_storage
from app.services.cinematic_memory_service import cinematic_memory_service
from app.services.cinematic_timeline_intelligence_service import (
    cinematic_timeline_intelligence_service,
)
from app.services.continuity_intelligence_service import continuity_intelligence_service
from app.services.director_commentary_service import director_commentary_service
from app.services.editorial_revision_intelligence_service import (
    editorial_revision_intelligence_service,
)
from app.services.frame_analysis_service import frame_analysis_service
from app.services.keyframe_extraction_service import keyframe_extraction_service
from app.services.semantic_memory_service import semantic_memory_service
from app.services.semantic_retrieval_service import semantic_retrieval_service
from app.services.semantic_search_service import semantic_search_service
from app.services.shot_detection_service import shot_detection_service
from app.services.style_intelligence_service import style_intelligence_service
from app.services.style_learning_service import style_learning_service
from app.services.video_asset_service import video_asset_service
from app.services.video_metadata_matching_service import video_metadata_matching_service
from app.services.visual_embedding_service import visual_embedding_service


def configure_project_route_dependencies() -> None:
    storage = get_storage("sqlite")
    storage_consumers = (
        video_asset_service,
        keyframe_extraction_service,
        shot_detection_service,
        semantic_memory_service,
        continuity_intelligence_service,
        director_commentary_service,
        semantic_search_service,
        frame_analysis_service,
        visual_embedding_service,
        cinematic_memory_service,
        semantic_retrieval_service,
        style_learning_service,
        style_intelligence_service,
        video_metadata_matching_service,
        cinematic_timeline_intelligence_service,
        editorial_revision_intelligence_service,
    )
    for service in storage_consumers:
        if getattr(service, "_storage", None) is None:
            service._storage = storage

    keyframe_extraction_service._video_asset_service = (
        keyframe_extraction_service._video_asset_service or video_asset_service
    )
    shot_detection_service._video_asset_service = (
        shot_detection_service._video_asset_service or video_asset_service
    )
    shot_detection_service._keyframe_service = (
        shot_detection_service._keyframe_service or keyframe_extraction_service
    )
    semantic_memory_service._video_asset_service = (
        semantic_memory_service._video_asset_service or video_asset_service
    )
    semantic_memory_service._shot_detection_service = (
        semantic_memory_service._shot_detection_service or shot_detection_service
    )
    continuity_intelligence_service._frame_analysis_service = (
        continuity_intelligence_service._frame_analysis_service or frame_analysis_service
    )
    continuity_intelligence_service._visual_embedding_service = (
        continuity_intelligence_service._visual_embedding_service or visual_embedding_service
    )
    continuity_intelligence_service._cinematic_memory_service = (
        continuity_intelligence_service._cinematic_memory_service or cinematic_memory_service
    )
    director_commentary_service._video_asset_service = (
        director_commentary_service._video_asset_service or video_asset_service
    )
    director_commentary_service._keyframe_service = (
        director_commentary_service._keyframe_service or keyframe_extraction_service
    )
    director_commentary_service._shot_detection_service = (
        director_commentary_service._shot_detection_service or shot_detection_service
    )
    director_commentary_service._semantic_memory_service = (
        director_commentary_service._semantic_memory_service or semantic_memory_service
    )
    semantic_search_service._semantic_memory_service = (
        semantic_search_service._semantic_memory_service or semantic_memory_service
    )
    frame_analysis_service._keyframe_service = (
        frame_analysis_service._keyframe_service or keyframe_extraction_service
    )
    frame_analysis_service._video_asset_service = (
        frame_analysis_service._video_asset_service or video_asset_service
    )
    visual_embedding_service._keyframe_service = (
        visual_embedding_service._keyframe_service or keyframe_extraction_service
    )
    visual_embedding_service._video_asset_service = (
        visual_embedding_service._video_asset_service or video_asset_service
    )
    cinematic_memory_service._frame_analysis_service = (
        cinematic_memory_service._frame_analysis_service or frame_analysis_service
    )
    cinematic_memory_service._visual_embedding_service = (
        cinematic_memory_service._visual_embedding_service or visual_embedding_service
    )
    cinematic_memory_service._keyframe_service = (
        cinematic_memory_service._keyframe_service or keyframe_extraction_service
    )
    cinematic_memory_service._video_asset_service = (
        cinematic_memory_service._video_asset_service or video_asset_service
    )
    semantic_retrieval_service._cinematic_memory_service = (
        semantic_retrieval_service._cinematic_memory_service or cinematic_memory_service
    )
    semantic_retrieval_service._visual_embedding_service = (
        semantic_retrieval_service._visual_embedding_service or visual_embedding_service
    )
    semantic_retrieval_service._keyframe_service = (
        semantic_retrieval_service._keyframe_service or keyframe_extraction_service
    )
    style_intelligence_service._frame_analysis_service = (
        style_intelligence_service._frame_analysis_service or frame_analysis_service
    )
    style_intelligence_service._visual_embedding_service = (
        style_intelligence_service._visual_embedding_service or visual_embedding_service
    )
    style_intelligence_service._cinematic_memory_service = (
        style_intelligence_service._cinematic_memory_service or cinematic_memory_service
    )
    style_intelligence_service._video_asset_service = (
        style_intelligence_service._video_asset_service or video_asset_service
    )
    style_intelligence_service._keyframe_service = (
        style_intelligence_service._keyframe_service or keyframe_extraction_service
    )
    video_metadata_matching_service._video_asset_service = (
        video_metadata_matching_service._video_asset_service or video_asset_service
    )
