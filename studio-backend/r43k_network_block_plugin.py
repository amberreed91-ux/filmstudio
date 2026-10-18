"""R4.3K test-only helper: socket-isolation evidence plugin (socket-only).

Usage (from studio-backend/):
    .venv/bin/python -m pytest -p r43k_network_block_plugin <suites> -q
    R43K_SOCKET_ONLY=1 .venv/bin/python -m pytest -p r43k_network_block_plugin <suites> -q

What it does (test process only, no source/config edits):
- Blocks all TCP connects: socket.socket.connect raises OSError (any test
  reaching the live network fails loudly instead of hanging).
- Deliberately does NOT patch internal mock provider transports, adapter
  registry entries, or router request helpers. Provider-wire suites drive
  mocked transports below the socket layer and must keep working under
  isolation; only real external sockets are blocked.

R43K_SOCKET_ONLY is accepted as a legacy no-op (socket-only is now the
only mode). If any test reaches the network, the OSError fails the test
and the suite stops per the R4.3K stop rule (report, do not work around).
"""

from __future__ import annotations

import socket

import pytest

_REAL_CONNECT = socket.socket.connect


def _blocked_connect(self, *args, **kwargs):
    raise OSError("R4.3K network blocked: no live network access permitted")


@pytest.fixture(autouse=True)
def _r43k_runway_unavailable_and_network_blocked(monkeypatch):
    # Socket isolation only. Never patch mock provider transports:
    # mocked router/adapter doubles operate in-process and must pass
    # cleanly under isolation. Any real external socket still fails loudly.
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    yield
