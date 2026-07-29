"""Configured service singletons for route dependency wiring."""

from app.data.storage import get_storage
from app.services.projects import ProjectService, ReferenceStudyService

_storage = get_storage("sqlite")

project_service = ProjectService(_storage)
reference_study_service = ReferenceStudyService(_storage)
