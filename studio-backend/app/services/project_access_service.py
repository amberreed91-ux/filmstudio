"""Server-side ownership policy. Unknown/global resource scopes fail closed."""
from urllib.parse import urlsplit

from app.auth import auth_service
from app.services.project_store import project_store


class AccessDenied(Exception):
    def __init__(self, status=403, message='Project access denied'):
        self.status = status
        self.message = message


class ProjectAccessService:
    def __init__(self, storage):
        self.storage = storage

    def authenticate(self, token):
        session = auth_service.get_session(token or '')
        if not session or not auth_service.get_user(session['user_id']):
            raise AccessDenied(401, 'Authentication required')
        return session['user_id']

    def require_projects(self, projects, owned):
        if not projects or not set(projects).issubset(owned):
            raise AccessDenied()

    def owned_listing(self, user_id):
        owned = self.storage.access_owned_projects(user_id)
        return [p for p in project_store.list_projects() if p['project_id'] in owned]

    def authorize(self, user_id, path, method, path_values, query, body):
        owned = self.storage.access_owned_projects(user_id)
        if path.startswith(('/outputs/', '/previs-assets/', '/static/')):
            self.require_projects(self.storage.access_media_projects(path), owned)
            return
        # Administrative/global mutation APIs are never made project APIs merely
        # by adding a caller-controlled project_id query parameter.
        if '/admin/' in path or path.endswith('/admin'):
            raise AccessDenied()
        project_ids = set()
        def inspect(value, key=''):
            if isinstance(value, dict):
                for k, v in value.items():
                    inspect(v, k)
            elif isinstance(value, list):
                for v in value:
                    inspect(v, key)
            elif isinstance(value, str) and value:
                # Some legacy routes accept JSON encoded in query/form fields.
                if value.lstrip().startswith(('{', '[')):
                    import json
                    try:
                        inspect(json.loads(value))
                    except ValueError:
                        raise AccessDenied(400, 'Invalid structured parameter')
                if key in {'owner_user_id', 'access_owner_user_id', 'user_id'}:
                    # Identity/ownership is never selected by a project payload.
                    if value != user_id:
                        raise AccessDenied()
                if key in {'project_id', 'film_id'}:
                    self.require_projects({value}, owned)
                    project_ids.add(value)
                elif key.endswith('_id') or key == 'id':
                    found = self.storage.access_resource_projects(value)
                    # Scene/shot labels are reused within many projects.
                    if key in {'scene_id', 'shot_id'} and project_ids:
                        if found and not found.intersection(project_ids):
                            raise AccessDenied()
                    elif found:
                        self.require_projects(found, owned)
                elif key.endswith('_path') or key in {'local_path', 'path'}:
                    raise AccessDenied(403, 'Local filesystem inputs require explicit local mode')
                elif key.endswith('_url') or key in {'url', 'reference_assets', 'referenceAssets'}:
                    media_path = urlsplit(value).path
                    if media_path.startswith(('/outputs/', '/static/', '/previs-assets/')):
                        self.require_projects(self.storage.access_media_projects(media_path), owned)
        # Resolve project scope before checking project-local scene/shot labels.
        for values in (path_values, query, body if isinstance(body, dict) else {}):
            for key in ('project_id', 'film_id'):
                if values.get(key):
                    inspect(values[key], key)
        inspect(path_values)
        inspect(query)
        inspect(body)
        if path_values.get('project_id') or path_values.get('film_id'):
            return
        # Opaque globally addressed resources must resolve to owned projects.
        resource_ids = [v for k, v in path_values.items() if k == 'id' or k.endswith('_id')]
        if resource_ids:
            for value in resource_ids:
                self.require_projects(self.storage.access_resource_projects(value), owned)
            return
        allowed_scoped = {
            ('POST', '/api/f51/studio/render/jobs'),
            ('GET', '/api/f51/studio/render/jobs'),
            ('POST', '/api/f51/studio/video-assets/upload'),
        }
        if (method, path) in allowed_scoped and project_ids:
            return
        raise AccessDenied(403, 'This endpoint has no authorized project scope')
