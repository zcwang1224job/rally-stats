"""Sport type plugins (spec 043).

Every sub-package here is one sport type. Core code never imports this package;
only the composition roots do (``app.main`` and ``alembic/env.py``, plus the
test suite), through :func:`register_all`.
"""

from app.sports import registry
from app.sports.types.frames.plugin import FramesPlugin
from app.sports.types.generic.plugin import GenericPlugin
from app.sports.types.net_rally.plugin import NetRallyPlugin


def register_all() -> None:
    """Register every built-in sport type plugin with the core registry.

    Idempotent: calling it again (app start-up, then the test suite) is a
    no-op."""
    registry.register(NetRallyPlugin())
    registry.register(FramesPlugin())
    registry.register(GenericPlugin())
