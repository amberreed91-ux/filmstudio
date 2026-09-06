from app.models import StudioProject
from app.services.projects import ReferenceStudyService


class _MemoryStorage:
    def __init__(self, project: StudioProject):
        self.project = project

    def get_project(self, project_id: str):
        if project_id == self.project.project_id:
            return self.project
        return None

    def save_project(self, project: StudioProject):
        self.project = project


def test_studio_brain_library_lists_and_attaches_markdown(tmp_path):
    library_file = tmp_path / "visual-language.md"
    library_file.write_text(
        "# Visual Language\n\nCamera distance should track emotional access.",
        encoding="utf-8",
    )
    project = StudioProject(project_id="studio-brain-project", title="Studio Brain Film")
    service = ReferenceStudyService(_MemoryStorage(project))
    service.studio_brain_library_dir = tmp_path

    listed = service.list_studio_brain_library(lambda title, content: "visual")

    assert listed["files"] == [
        {
            "filename": "visual-language.md",
            "title": "Visual Language",
            "summary": "Camera distance should track emotional access.",
            "study_focus": "visual",
        }
    ]

    attached = service.attach_studio_brain_references(
        "studio-brain-project",
        ["visual-language.md"],
        lambda title, content: "visual",
    )

    assert attached["total_attached"] == 1
    assert project.reference_study_library is not None
    study = project.reference_study_library.studies[0]
    assert study.filename == "Visual Language"
    assert study.content_type == "text/markdown"
    assert study.source_stats["studio_brain_filename"] == "visual-language.md"

    duplicate = service.attach_studio_brain_references(
        "studio-brain-project",
        ["visual-language.md"],
        lambda title, content: "visual",
    )

    assert duplicate["total_attached"] == 0
    assert duplicate["skipped"] == [
        {"filename": "visual-language.md", "reason": "already_attached"}
    ]
