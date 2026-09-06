"""Request identity propagated into synchronous service calls by Starlette."""
from contextvars import ContextVar

access_user_id: ContextVar[str | None] = ContextVar('access_user_id', default=None)
