"""Vercel serverless entrypoint for Firevolv (PRD §7).

Placed at the repo-root ``/api`` directory — Vercel's convention for Python
serverless functions — so the platform auto-detects it. Vercel serves the
module-level ``app`` (an ASGI application) directly, and ``vercel.json``
rewrites every route to it, so FastAPI serves both the single-page UI (at ``/``)
and the JSON API (``/analyze``, ``/label``, ``/corpus``, ``/reset``,
``/health``) from one origin.

The repo root (which holds the ``backend`` and ``frontend`` packages, bundled
via ``functions.includeFiles`` in vercel.json) is put on ``sys.path`` so the
import resolves regardless of the function's working directory.
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.main import app  # noqa: E402  (ASGI app served by Vercel's Python runtime)

__all__ = ["app"]
