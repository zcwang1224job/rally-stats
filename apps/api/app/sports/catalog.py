"""Built-in activity catalogue (spec 043 FR-001/FR-002, data-model §6).

Code constants rather than a seeded table (research Decision 5): the test
database's TRUNCATE … members CASCADE would empty a table that also holds
members' custom rows, and built-in names are i18n keys, not data. Members'
own activities live in `member_sports`.

The order of BUILTIN_SPORTS is the order the create-group catalogue shows;
"other" is always last.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from app.sports.presentation import Nouns, SportSummary

EndMode = Literal["target", "manual"]

# sport_key of an activity that is not a built-in.
CUSTOM_SPORT_KEY = "custom"
OTHER_SPORT_KEY = "other"


@dataclass(frozen=True)
class SportDefaults:
    team_size: int
    end_mode: EndMode
    target_score: int
    win_by: int
    cap_score: int | None
    allow_draw: bool
    score_steps: tuple[int, ...]
    type_params: dict[str, Any] = field(default_factory=dict)
    # Only badminton keeps the historical 21pt/15pt presets.
    scoring_mode: str = "custom"

    def as_dict(self) -> dict[str, Any]:
        return {
            "team_size": self.team_size,
            "end_mode": self.end_mode,
            "target_score": self.target_score,
            "win_by": self.win_by,
            "cap_score": self.cap_score,
            "allow_draw": self.allow_draw,
            "score_steps": list(self.score_steps),
            "type_params": dict(self.type_params),
            "scoring_mode": self.scoring_mode,
        }


@dataclass(frozen=True)
class BuiltinSport:
    sport_key: str
    type_key: str
    icon: str
    team_size_options: tuple[int, ...]
    defaults: SportDefaults
    nouns: Nouns

    @property
    def name_key(self) -> str:
        return f"sports.{self.sport_key}"

    def summary(self) -> SportSummary:
        return SportSummary(
            sport_key=self.sport_key,
            type_key=self.type_key,
            name_key=self.name_key,
            name=None,
            icon=self.icon,
            nouns=self.nouns,
        )


_NET_RALLY_OFF = {"modules": {"serve_tracking": False, "shot_placement": False}}
_FRAMES_PLAIN = {"frame_scoring_enabled": False, "frame_target": None, "frame_win_by": 1}


def _frames(target: int, team_sizes: tuple[int, ...]) -> SportDefaults:
    return SportDefaults(
        team_size=team_sizes[0],
        end_mode="target",
        target_score=target,
        win_by=1,
        cap_score=None,
        allow_draw=False,
        score_steps=(1,),
        type_params=dict(_FRAMES_PLAIN),
    )


def _net_rally_open(target: int) -> SportDefaults:
    return SportDefaults(
        team_size=1,
        end_mode="target",
        target_score=target,
        win_by=2,
        cap_score=None,
        allow_draw=False,
        score_steps=(1,),
        type_params={"modules": dict(_NET_RALLY_OFF["modules"])},
    )


BUILTIN_SPORTS: tuple[BuiltinSport, ...] = (
    BuiltinSport(
        sport_key="badminton",
        type_key="net_rally",
        icon="shuttle",
        team_size_options=(1, 2),
        defaults=SportDefaults(
            team_size=1,
            end_mode="target",
            target_score=21,
            win_by=2,
            cap_score=30,
            allow_draw=False,
            score_steps=(1,),
            type_params={"modules": {"serve_tracking": True, "shot_placement": True}},
            scoring_mode="21pt",
        ),
        nouns=Nouns(venue="court", score="point", member="player"),
    ),
    BuiltinSport(
        sport_key="table_tennis",
        type_key="net_rally",
        icon="paddle",
        team_size_options=(1, 2),
        defaults=_net_rally_open(11),
        nouns=Nouns(venue="table", score="point", member="player"),
    ),
    BuiltinSport(
        sport_key="pickleball",
        type_key="net_rally",
        icon="pickleball",
        team_size_options=(1, 2),
        defaults=_net_rally_open(11),
        nouns=Nouns(venue="court", score="point", member="player"),
    ),
    BuiltinSport(
        sport_key="tennis_tiebreak",
        type_key="net_rally",
        icon="tennis",
        team_size_options=(1, 2),
        defaults=_net_rally_open(10),
        nouns=Nouns(venue="court", score="point", member="player"),
    ),
    BuiltinSport(
        sport_key="billiards",
        type_key="frames",
        icon="billiards",
        team_size_options=(1,),
        defaults=_frames(5, (1,)),
        nouns=Nouns(venue="table", score="frame", member="player"),
    ),
    BuiltinSport(
        sport_key="darts",
        type_key="frames",
        icon="darts",
        team_size_options=(1,),
        defaults=_frames(3, (1,)),
        nouns=Nouns(venue="station", score="frame", member="competitor"),
    ),
    BuiltinSport(
        sport_key="board_game",
        type_key="frames",
        icon="board_game",
        team_size_options=(1, 2),
        defaults=_frames(1, (1, 2)),
        nouns=Nouns(venue="board", score="frame", member="player"),
    ),
    BuiltinSport(
        sport_key="esports",
        type_key="frames",
        icon="esports",
        team_size_options=(1, 2),
        defaults=_frames(2, (1, 2)),
        nouns=Nouns(venue="station", score="frame", member="competitor"),
    ),
    BuiltinSport(
        sport_key=OTHER_SPORT_KEY,
        type_key="generic",
        icon="other",
        team_size_options=(1, 2),
        defaults=SportDefaults(
            team_size=1,
            end_mode="manual",
            target_score=1,
            win_by=1,
            cap_score=None,
            allow_draw=True,
            score_steps=(1,),
        ),
        nouns=Nouns(venue="venue", score="point", member="member"),
    ),
)

_BY_KEY = {sport.sport_key: sport for sport in BUILTIN_SPORTS}

DEFAULT_SPORT_KEY = BUILTIN_SPORTS[0].sport_key


def get_builtin(sport_key: str) -> BuiltinSport | None:
    return _BY_KEY.get(sport_key)


def summary_for(
    *, sport_key: str, type_key: str, sport_name: str | None, nouns: Nouns | None = None
) -> SportSummary:
    """The SportSummary of a group/match snapshot. Built-ins come from the
    catalogue; custom and "other" activities show their own name."""
    builtin = get_builtin(sport_key)
    if builtin is not None and sport_key != OTHER_SPORT_KEY:
        return builtin.summary()
    fallback = _BY_KEY[OTHER_SPORT_KEY]
    return SportSummary(
        sport_key=sport_key,
        type_key=type_key,
        name_key=None if sport_name else fallback.name_key,
        name=sport_name,
        icon=fallback.icon,
        nouns=nouns or fallback.nouns,
    )
