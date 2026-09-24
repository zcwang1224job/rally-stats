"""Frames match detail and dashboard sections (spec 043 FR-023,
contracts/sections-manifest.md §3)."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.sports.dashboard import (
    LOSSES,
    MATCH_WIN_RATE,
    MATCHES,
    WINS,
    MetricDef,
    Value,
    average,
    empty_dashboard,
    metric_grid,
    my_score,
    opponent_table,
    rate,
    their_score,
)
from app.sports.plugin import DashboardContext, DashboardRow, MatchDetailContext, MatchDetailParts
from app.sports.presentation import Section
from app.sports.types.frames.events import frame_results


async def match_detail(session: AsyncSession, ctx: MatchDetailContext) -> MatchDetailParts:
    match = ctx.match
    frames = (await frame_results(session, [match.id]))[match.id]
    started_at = match.started_at
    rows = []
    trend = []
    frames_a = frames_b = 0
    for frame in frames:
        frames_a += frame.winner_team == "A"
        frames_b += frame.winner_team == "B"
        rows.append(
            {
                "frame_no": frame.frame_no,
                "winner_team": frame.winner_team,
                "score_a": frame.score_a,
                "score_b": frame.score_b,
                "ended_by": frame.ended_by,
                "elapsed_seconds": (
                    int((frame.created_at - started_at).total_seconds())
                    if started_at is not None
                    else None
                ),
            }
        )
        trend.append({"frame_no": frame.frame_no, "frames_a": frames_a, "frames_b": frames_b})
    return MatchDetailParts(
        sections=[
            Section(
                kind="frames.frame_list",
                title_key="frames.sections.frameList",
                data={"frames": rows},
            ),
            Section(
                kind="frames.frame_trend",
                title_key="frames.sections.frameTrend",
                data={"points": trend},
            ),
        ]
    )


def _frames_played(rows: Sequence[DashboardRow]) -> tuple[int, int]:
    won = sum(my_score(row) for row in rows)
    played = sum(my_score(row) + their_score(row) for row in rows)
    return won, played


def _first_frame_rows(
    rows: Sequence[DashboardRow], first_frames: dict[str, str]
) -> list[DashboardRow]:
    return [row for row in rows if first_frames.get(str(row.match.id)) == row.my_team]


async def dashboard_sections(session: AsyncSession, ctx: DashboardContext) -> list[Section]:
    if not ctx.mine:
        return empty_dashboard()
    match_ids = {row.match.id for rows in (ctx.mine, *ctx.peers.values()) for row in rows}
    results = await frame_results(session, sorted(match_ids))
    first_frames = {
        str(match_id): frames[0].winner_team for match_id, frames in results.items() if frames
    }

    def after_first_frame(rows: Sequence[DashboardRow]) -> Value:
        took_first = _first_frame_rows(rows, first_frames)
        return rate(sum(1 for row in took_first if row.result == "win"), len(took_first))

    defs = [
        MATCH_WIN_RATE,
        MetricDef(
            "frame_win_rate",
            "frames.metric.frame_win_rate",
            "rate",
            "higher",
            lambda rows: rate(*_frames_played(rows)),
        ),
        MetricDef(
            "win_rate_after_first_frame",
            "frames.metric.win_rate_after_first_frame",
            "rate",
            "higher",
            after_first_frame,
        ),
        MetricDef(
            "avg_frames_per_match",
            "frames.metric.avg_frames_per_match",
            "average",
            None,
            lambda rows: average(sum(my_score(r) + their_score(r) for r in rows), len(rows)),
        ),
        MATCHES,
        WINS,
        LOSSES,
    ]

    deciders = [
        row
        for row in ctx.mine
        if min(my_score(row), their_score(row)) == row.match.target_score - 1
        and row.match.target_score > 1
    ]
    summary = Section(
        kind="frames.dashboard_summary",
        title_key="frames.sections.summary",
        data={
            "decider_record": {
                "played": len(deciders),
                "won": sum(1 for row in deciders if row.result == "win"),
            },
            "longest_match_frames": max(
                (my_score(row) + their_score(row) for row in ctx.mine), default=0
            ),
        },
    )
    return [metric_grid(defs, ctx), summary, opponent_table(ctx.mine)]
