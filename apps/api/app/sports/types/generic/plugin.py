"""Generic sport type: only a score and a result — the fallback for any
activity the catalogue does not cover (spec 043 US5)."""

from typing import ClassVar

from app.sports.plugin import BasePlugin


class GenericPlugin(BasePlugin):
    type_key: ClassVar[str] = "generic"
