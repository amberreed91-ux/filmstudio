"""R4.3K test-only helper: Runway-unavailable + network-blocked evidence plugin.

Usage (from studio-backend/):
    .venv/bin/python -m pytest -p r43k_network_block_plugin <suites> -q

What it does (test process only, no source/config edits):
- Blocks all TCP connects: socket.socket.connect raises OSError (any test
  reaching the live network fails loudly instead of hanging).
- Patches the Runway router provider transport
  (app.services.providers.runway_router_provider._runway_router_request)
  to raise ProviderError("runway_unavailable_r43k").
- Patches adapter-registry Runway entries (runway/runway_direct/runway_router)
  so any adapter-level execution raises ProviderError instead of HTTP.

If any test reaches the network, the OSError fails the test and the suite
stops per the R4.3K stop rule (report, do not work around).
"""

from __future__ import annotations

import socket

import pytest

_REAL_CONNECT = socket.socket.connect


def _blocked_connect(self, *args, **kwargs):
    raise OSError("R4.3K network blocked: no live network access permitted")


def _provider_unavailable(*args, **kwargs):
    from app.services.stability import ProviderError

    raise ProviderError(
        "R4.3K Runway adapter patched unavailable",
        stage="r43k_runway_unavailable",
        metadata={"provider": "runway_router"},
    )


@pytest.fixture(autouse=True)
def _r43k_runway_unavailable_and_network_blocked(monkeypatch):
    import os

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    if os.getenv("R43K_SOCKET_ONLY") == "1":
        # Socket block only: provider fakes in provider-wire suites keep
        # working; any real network attempt still fails loudly.
        yield
        return
    try:
        import app.services.providers.runway_router_provider as router_mod

        monkeypatch.setattr(
            router_mod, "_runway_router_request", _provider_unavailable, raising=False
        )
        for _name in (
            "submit_runway_router_video_render",
            "submit_runway_router_image_render",
            "fetch_runway_router_task_status",
        ):
            if hasattr(router_mod, _name):
                monkeypatch.setattr(router_mod, _name, _provider_unavailable, raising=False)
    except Exception:
        pass
    try:
        import app.adapters as adapters_mod

        for _provider_id in ("runway", "runway_direct", "runway_router"):
            _cls = adapters_mod.ADAPTER_REGISTRY.get(_provider_id)
            if _cls is not None:
                monkeypatch.setattr(_cls, "submit", _provider_unavailable, raising=False)
                monkeypatch.setattr(_cls, "render", _provider_unavailable, raising=False)
                monkeypatch.setattr(_cls, "poll", _provider_unavailable, raising=False)
    except Exception:
        pass
    yield
