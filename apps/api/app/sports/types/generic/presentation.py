"""Generic match detail and dashboard sections (spec 043 US5,
contracts/sections-manifest.md §3 `generic`): a score, a result, nothing
else — so only generic section kinds."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.sports.dashboard import (
    DRAWS,
    LOSSES,
    MATCH_WIN_RATE,
    MATCHES,
    WINS,
    MetricDef,
    average,
    empty_dashboard,
    metric_grid,
    my_score,
    opponent_table,
    their_score,
)
from app.sports.plugin import DashboardContext, MatchDetailContext, MatchDetailParts
from app.sports.presentation import Section


async def match_detail(session: AsyncSession, ctx: MatchDetailContext) -> MatchDetailParts:
    match = ctx.match
    started_at = match.started_at
    events = [
        {
            "side": event.side,
            "delta": event.delta,
            "score_a": event.score_a,
            "score_b": event.score_b,
            "elapsed_seconds": (
                int((event.created_at - started_at).total_seconds())
                if started_at is not None
                else None
            ),
            "kind": event.kind,
        }
        for event in ctx.point_events
    ]
    score_line = [
        ("points_for", "sections.metric.points_a", match.score_a),
        ("points_against", "sections.metric.points_b", match.score_b),
        ("margin", "sections.metric.margin", abs(match.score_a - match.score_b)),
    ]
    return MatchDetailParts(
        sections=[
            Section(
                kind="score_timeline",
                title_key="sections.scoreTimeline",
                data={
                    "target_score": match.target_score if match.end_mode == "target" else None,
                    "cap_score": match.cap_score,
                    "events": events,
                },
            ),
            Section(
                kind="metric_grid",
                data={
                    "metrics": [
                        {
                            "key": key,
                            "label_key": label_key,
                            "kind": "count",
                            "value": float(value),
                            "numerator": None,
                            "denominator": None,
                            "better_when": None,
                            "group_average": None,
                            "delta": None,
                        }
                        for key, label_key, value in score_line
                    ]
                },
            ),
        ]
    )


AVG_POINTS_FOR = MetricDef(
    "avg_points_for",
    "sections.metric.avg_points_for",
    "average",
    "higher",
    lambda rows: average(sum(my_score(row) for row in rows), len(rows)),
)
AVG_POINTS_AGAINST = MetricDef(
    "avg_points_against",
    "sections.metric.avg_points_against",
    "average",
    "lower",
    lambda rows: average(sum(their_score(row) for row in rows), len(rows)),
)


async def dashboard_sections(session: AsyncSession, ctx: DashboardContext) -> list[Section]:
    if not ctx.mine:
        return empty_dashboard()
    defs = [MATCH_WIN_RATE, MATCHES, WINS, LOSSES, DRAWS, AVG_POINTS_FOR, AVG_POINTS_AGAINST]
    return [metric_grid(defs, ctx), opponent_table(ctx.mine)]
