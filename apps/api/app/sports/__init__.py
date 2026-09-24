"""Sport type plugin foundation (spec 043).

Core modules here (registry, plugin, presentation, scoring, catalog) MUST NOT
import ``app.sports.types``; plugins live under ``app.sports.types`` and are
wired only by the composition roots (``app.main``, ``alembic/env.py``).
"""
