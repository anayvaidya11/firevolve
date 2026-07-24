"""Vercel serverless entrypoint for Firevolv (PRD §7).

Vercel's @vercel/python builder serves the module-level ``app`` (an ASGI
application) directly. All routes are rewritten to this function by
``vercel.json``, so FastAPI serves both the single-page UI (at ``/``) and the
JSON API (``/analyze``, ``/label``, ``/corpus``, ``/reset``, ``/health``) from
one origin — the same wiring proven locally, just packaged for Vercel.

The repo root (which holds the ``backend`` and ``frontend`` packages, pulled
into the bundle via ``includeFiles``) is put on ``sys.path`` so the import
resolves regardless of the function's working directory.
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.main import app  # noqa: E402  (ASGI app served by @vercel/python)

# Re-export so the builder can find it by name.
__all__ = ["app"]
