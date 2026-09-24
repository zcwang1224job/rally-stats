"""034-clutch-points-player-dashboard: demo / performance data for the
technique dashboard. Writes ONLY to the database named on the command line,
and refuses anything that isn't a throwaway one.

    python -m scripts.seed_dashboard_demo rally_stats_test

Creates two verified members (password `abc12345`):

- demo@example.com  — 16 doubles matches, oldest to newest getting better
  (heavy losses -> narrow losses -> wins), one deuce thriller, serve records,
  and landings recorded both as team A and as team B, with point endings
  (035) on about four fifths of the recorded points;
- heavy@example.com — 300 matches with full point logs, for timing the
  dashboard against SC-007 (quickstart scenario 12).

036-match-insights-benchmarks adds, for its quickstart scenarios:

- around demo@example.com: a partner they clearly do better with (阿強, 8
  matches), one they have only played twice with (小新), and a pair they keep
  losing to (高手/老手, 6 matches); a second group, 週末球友, where
  friend@example.com — 阿凱 in the first group — plays as Kai (one member, two
  nicknames), where another 小美 turns up (two players, one nickname), and
  which demo left and rejoined (two roster rows);
- friend@example.com — a friend of demo's who shares their records, and has
  been both demo's opponent and demo's partner;
- 效能比較團 — 40 players and 1,000 fully logged doubles matches, heavy among
  them, for timing the group benchmark against 036 SC-008."""

import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domains.friend.models import FriendRequest
from app.domains.member.service import register
from tests.unit.domains._match_history import (
    Shot,
    make_entry,
    make_group,
    make_played_match,
)

ALLOWED_DATABASES = {"rally_stats_test"}
NOW = datetime.now(UTC).replace(microsecond=0)


def play(rng: random.Random, my_strength: float, target: int = 21, cap: int = 30) -> str:
    """A legal point sequence; `my_strength` is team A's chance per point."""
    a = b = 0
    sides = []
    while not (a >= cap or b >= cap or (max(a, b) >= target and abs(a - b) >= 2)):
        if rng.random() < my_strength:
            a += 1
            sides.append("A")
        else:
            b += 1
            sides.append("B")
    return "".join(sides)


def swap(sides: str) -> str:
    return sides.translate(str.maketrans("AB", "BA"))


async def seed(database: str) -> None:
    if database not in ALLOWED_DATABASES:
        raise SystemExit(f"refusing to seed {database!r}; allowed: {sorted(ALLOWED_DATABASES)}")
    engine = create_async_engine(f"postgresql+asyncpg://rally:rally_dev@localhost:5432/{database}")
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        rng = random.Random(34)

        demo = await register(session, "demo@example.com", "abc12345")
        demo.verification_status = "verified"
        demo.nickname = "小明"
        await session.commit()
        group = await make_group(session, "週三羽球團", match_mode="doubles")
        me = await make_entry(session, group, "小明", demo.id)
        partner = await make_entry(session, group, "阿哲")
        opp1 = await make_entry(session, group, "小美")
        opp2 = await make_entry(session, group, "大雄")
        mine, theirs = [me.id, partner.id], [opp1.id, opp2.id]

        for index in range(16):
            strength = 0.36 + index * 0.014  # 0.36 -> 0.57
            sides = "AB" * 20 + "ABABAA" if index == 13 else play(rng, strength)
            as_team_b = index % 2 == 1
            shots = {}
            for point, side in enumerate(sides):
                if rng.random() > 0.55:
                    continue
                won_by_me = side == "A"
                # my scoring shots land in the opponents' half, mostly deep;
                # my lost points land in my own half, mostly my backhand rear
                x = rng.uniform(0.62, 1.04) if won_by_me else rng.uniform(-0.03, 0.4)
                y = rng.uniform(0.05, 0.95) if won_by_me else rng.betavariate(2, 5)
                if as_team_b:
                    x, y = 1 - x, 1 - y
                # 035: how the rally ended — what the picker would have
                # auto-filled (out of bounds -> out), a coin flip between a
                # winner and a net shot in bounds, and about a fifth of the
                # points left unrecorded, as real scorers do.
                in_bounds = 0 <= x <= 1 and 0 <= y <= 1
                ending: str | None
                if rng.random() < 0.2:
                    ending = None
                elif not in_bounds:
                    ending = "out"
                else:
                    ending = "winner" if rng.random() < 0.55 else "net"
                shots[point] = Shot(
                    scorer=(me.id if rng.random() < 0.5 else partner.id) if won_by_me else opp1.id,
                    loser=opp2.id if won_by_me else (me.id if rng.random() < 0.6 else partner.id),
                    landing=(round(x, 3), round(y, 3)),
                    ending=ending,
                )
            await make_played_match(
                session,
                group,
                team_a=theirs if as_team_b else mine,
                team_b=mine if as_team_b else theirs,
                sides=swap(sides) if as_team_b else sides,
                ended_at=NOW - timedelta(days=(16 - index) * 3),
                round_number=index + 1,
                shots=shots,
            )

        # ---- 036: partners, opponents, a second group, a friend ----------
        strong_partner = await make_entry(session, group, "阿強")
        rare_partner = await make_entry(session, group, "小新")
        walls = [(await make_entry(session, group, name)).id for name in ("高手", "老手")]
        for index in range(8):  # clearly better with 阿強…
            await make_played_match(
                session,
                group,
                team_a=[me.id, strong_partner.id],
                team_b=theirs,
                sides=play(rng, 0.62),
                ended_at=NOW - timedelta(days=60 + index),
            )
        for index in range(2):  # …barely played with 小新…
            await make_played_match(
                session,
                group,
                team_a=[me.id, rare_partner.id],
                team_b=theirs,
                sides=play(rng, 0.5),
                ended_at=NOW - timedelta(days=70 + index),
            )
        for index in range(6):  # …and keeps losing to 高手/老手.
            await make_played_match(
                session,
                group,
                team_a=mine,
                team_b=walls,
                sides=play(rng, 0.36),
                ended_at=NOW - timedelta(days=80 + index),
            )

        friend = await register(session, "friend@example.com", "abc12345")
        friend.verification_status = "verified"
        friend.nickname = "阿凱"
        session.add(FriendRequest(requester_id=demo.id, addressee_id=friend.id, status="accepted"))
        await session.commit()
        friend_here = await make_entry(session, group, "阿凱", friend.id)
        for index in range(3):  # the friend as an opponent, in the first group
            await make_played_match(
                session,
                group,
                team_a=mine,
                team_b=[friend_here.id, opp1.id],
                sides=play(rng, 0.5),
                ended_at=NOW - timedelta(days=90 + index),
            )

        weekend = await make_group(session, "週末球友", match_mode="doubles")
        first_stint = await make_entry(
            session, weekend, "小明", demo.id, status="left", joined_at=NOW - timedelta(days=200)
        )
        me_again = await make_entry(session, weekend, "小明回來了", demo.id)
        kai = await make_entry(session, weekend, "Kai", friend.id)  # same member, other nickname
        namesake = await make_entry(session, weekend, "小美")  # another 小美 altogether
        regular = await make_entry(session, weekend, "老王")
        for index in range(3):  # first stint: the friend as an opponent again
            await make_played_match(
                session,
                weekend,
                team_a=[first_stint.id, regular.id],
                team_b=[kai.id, namesake.id],
                sides=play(rng, 0.5),
                ended_at=NOW - timedelta(days=150 + index),
            )
        for index in range(4):  # second stint: the friend as a partner
            await make_played_match(
                session,
                weekend,
                team_a=[me_again.id, kai.id],
                team_b=[namesake.id, regular.id],
                sides=play(rng, 0.55),
                ended_at=NOW - timedelta(days=20 + index),
            )

        heavy = await register(session, "heavy@example.com", "abc12345")
        heavy.verification_status = "verified"
        await session.commit()
        big = await make_group(session, "效能測試團", match_mode="doubles")
        h_me = await make_entry(session, big, "重度球友", heavy.id)
        others = [(await make_entry(session, big, f"球友{n}")).id for n in range(3)]
        for index in range(300):
            await make_played_match(
                session,
                big,
                team_a=[h_me.id, others[0]],
                team_b=others[1:],
                sides=play(rng, 0.5),
                ended_at=NOW - timedelta(hours=index * 5),
                round_number=index % 8 + 1,
            )

        # ---- 036 SC-008: 40 players, 1,000 fully logged doubles matches ----
        league = await make_group(session, "效能比較團", match_mode="doubles")
        players = [(await make_entry(session, league, "重度球友", heavy.id)).id]
        players += [(await make_entry(session, league, f"團友{n:02d}")).id for n in range(39)]
        skill = {player: rng.uniform(0.4, 0.6) for player in players}
        for index in range(1000):
            four = rng.sample(players, 4)
            if index % 4 == 0 and players[0] not in four:
                four[0] = players[0]  # heavy plays about a quarter of them
            edge = (skill[four[0]] + skill[four[1]] - skill[four[2]] - skill[four[3]]) / 2
            await make_played_match(
                session,
                league,
                team_a=four[:2],
                team_b=four[2:],
                sides=play(rng, 0.5 + edge),
                ended_at=NOW - timedelta(hours=index * 3),
                round_number=index % 8 + 1,
            )
    await engine.dispose()
    print(
        "seeded demo@example.com, friend@example.com, heavy@example.com (300 matches) "
        "and 效能比較團 (40 players, 1,000 matches)"
    )


if __name__ == "__main__":
    asyncio.run(seed(sys.argv[1] if len(sys.argv) > 1 else ""))
