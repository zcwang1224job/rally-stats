"""Frames sport type (billiards, darts, board games, esports): a match is
first to N frames; each frame only has a winner, optionally with an in-frame
score kept point by point (spec 043 US3)."""

from typing import ClassVar

from app.sports.plugin import BasePlugin


class FramesPlugin(BasePlugin):
    type_key: ClassVar[str] = "frames"
    section_kinds: ClassVar[frozenset[str]] = frozenset(
        {"frames.frame_list", "frames.frame_trend", "frames.dashboard_summary"}
    )
