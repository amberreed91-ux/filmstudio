"""Keep source facts intact while a generation request is being constructed."""
from contextvars import ContextVar
from functools import wraps

collecting_generation_prompt = ContextVar('collecting_generation_prompt', default=False)


def preserve_generation_facts(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        marker = collecting_generation_prompt.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            collecting_generation_prompt.reset(marker)
    return wrapped
