"""HTTP and WebSocket authorization ahead of routes, including mounted media."""
import json
import os
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import compile_path

from app.access_context import access_user_id
from app.config import settings
from app.services.project_access_service import AccessDenied, ProjectAccessService


class ProjectAccessMiddleware:
    def __init__(self, app, storage, schema):
        self.app = app
        self.service = ProjectAccessService(storage)
        self.schema = schema
        self.routes = None

    def local(self, scope):
        if settings.studio_access_mode != 'local' or os.getenv('APP_ENV', '').lower() in {'production', 'prod'}:
            return False
        headers = dict(scope.get('headers', []))
        host = headers.get(b'host', b'').decode().split(':')[0]
        client = (scope.get('client') or ('', 0))[0]
        allowed = {'127.0.0.1', 'localhost', '::1', '[::1]'}
        if os.getenv('PYTEST_CURRENT_TEST'):
            allowed.update({'testclient', 'testserver'})
        origin = headers.get(b'origin', b'').decode()
        forwarded = headers.get(b'x-forwarded-for', b'').decode()
        return client in allowed and host in allowed and (not origin or urlsplit(origin).hostname in allowed) and (not forwarded or all(x.strip() in allowed for x in forwarded.split(',')))

    async def __call__(self, scope, receive, send):
        local_access = self.local(scope)
        scope.setdefault('state', {})['local_access'] = local_access
        if scope['type'] not in {'http', 'websocket'} or local_access:
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            # Existing broadcasts include all projects. Close until subscriptions
            # and broadcasts are both explicitly scoped; polling remains available.
            await send({'type': 'websocket.close', 'code': 1008})
            return
        request = Request(scope, receive)
        path = request.url.path.rstrip('/') or '/'
        if request.method == 'OPTIONS' or path in {'/', '/ready', '/build-info'} or path.startswith('/api/f51/studio/auth/'):
            return await self.app(scope, receive, send)
        if path == '/health':
            return await JSONResponse({'status': 'online'})(scope, receive, send)
        marker = None
        try:
            authorization = request.headers.get('authorization', '')
            token = request.cookies.get('session_id') or request.headers.get('x-session-token')
            if authorization.startswith('Bearer '):
                token = authorization[7:]
            origin = request.headers.get('origin')
            if request.cookies.get('session_id') and request.method not in {'GET', 'HEAD'} and origin:
                allowed_origins = {str(request.base_url).rstrip('/')} | {x.strip() for x in settings.cors_origins.split(',') if x.strip()}
                if origin not in allowed_origins:
                    raise AccessDenied(403, 'Cross-origin session mutation denied')
            user_id = self.service.authenticate(token)
            marker = access_user_id.set(user_id)
            if request.method == 'GET' and path in {'/api/f51/studio/projects', '/api/f51/studio/overview'}:
                projects = self.service.owned_listing(user_id)
                result = {'projects': projects}
                if path.endswith('/overview'):
                    result['latest_project'] = projects[0] if projects else None
                return await JSONResponse(result)(scope, receive, send)
            if request.method == 'GET' and path == '/api/f51/studio/render/providers':
                return await self.app(scope, receive, send)
            chunks = []
            async for chunk in request.stream():
                chunks.append(chunk)
                if sum(map(len, chunks)) > 25 * 1024 * 1024:
                    raise AccessDenied(413, 'Request exceeds access-validation size limit')
            raw = b''.join(chunks)
            body = {}
            if raw:
                content_type = request.headers.get('content-type', '')
                if 'application/json' in content_type:
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        raise AccessDenied(400, 'Invalid JSON')
                elif 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
                    request._body = raw
                    form = await request.form()
                    body = {key: value for key, value in form.multi_items() if isinstance(value, str)}
                    await form.close()
                else:
                    raise AccessDenied(415, 'Unsupported request content type')
            values = {}
            if self.routes is None:
                self.routes = [(compile_path(template)[0], methods) for template, methods in self.schema()['paths'].items()]
            for regex, methods in self.routes:
                matched = regex.fullmatch(path)
                if matched and request.method.lower() in methods:
                    values = matched.groupdict()
                    break
            if request.method == 'POST' and path == '/api/f51/studio/projects':
                if not isinstance(body, dict) or set(body) - {'title'}:
                    raise AccessDenied(422, 'New projects accept a title; identifiers and ownership are server assigned')
            else:
                self.service.authorize(user_id, path, request.method, values, dict(request.query_params), body)
            delivered = False
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': raw, 'more_body': False}
                return await receive()
            await self.app(scope, replay, send)
        except AccessDenied as exc:
            await JSONResponse({'detail': exc.message}, status_code=exc.status)(scope, receive, send)
        finally:
            if marker is not None:
                access_user_id.reset(marker)
