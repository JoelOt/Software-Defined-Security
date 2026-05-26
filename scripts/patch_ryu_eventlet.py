#!/usr/bin/env python3
"""
Patch Ryu 4.34 for Eventlet releases that removed wsgi.ALREADY_HANDLED.

Run this from the project virtualenv after installing requirements:
    venv/bin/python scripts/patch_ryu_eventlet.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PATCHED_BLOCK = """class _AlreadyHandledResponse(Response):
    # XXX: Eventlet API should not be used directly.
    # Eventlet >= 0.31 removed ALREADY_HANDLED and now expects this
    # thread-local flag to be set by applications that already handled
    # the response, such as websocket handlers.
    from eventlet.wsgi import WSGI_LOCAL
    _WSGI_LOCAL = WSGI_LOCAL

    def __call__(self, environ, start_response):
        self._WSGI_LOCAL.already_handled = True
        return []
"""


def main() -> int:
    spec = importlib.util.find_spec("ryu.app.wsgi")
    if spec is None or spec.origin is None:
        print("ryu.app.wsgi was not found. Install requirements first.", file=sys.stderr)
        return 1

    path = Path(spec.origin)
    source = path.read_text()

    if "eventlet.wsgi import WSGI_LOCAL" in source and "already_handled = True" in source:
        print(f"Ryu/Eventlet compatibility patch already present: {path}")
        return 0

    start = source.find("class _AlreadyHandledResponse(Response):")
    end = source.find("\n\ndef websocket", start)
    if start == -1 or end == -1:
        print(f"Could not locate _AlreadyHandledResponse in {path}", file=sys.stderr)
        return 1

    path.write_text(source[:start] + PATCHED_BLOCK + source[end:])
    print(f"Patched Ryu/Eventlet compatibility in: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
