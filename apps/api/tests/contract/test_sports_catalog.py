"""043 T048: GET /sports (contracts/sports-api.md §1)."""

from httpx import AsyncClient


async def test_catalog_lists_types_and_builtins_in_order(client: AsyncClient) -> None:
    response = await client.get("/sports")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"types", "builtin", "custom"}

    types = {item["type_key"]: item for item in body["types"]}
    assert set(types) == {"net_rally", "frames", "generic"}
    net_rally = types["net_rally"]
    assert net_rally["modules"] == ["serve_tracking", "shot_placement"]
    assert "net_rally.match_detail" in net_rally["section_kinds"]
    assert net_rally["params_schema"]["type"] == "object"
    assert net_rally["team_size_range"] == [1, 2]

    keys = [item["sport_key"] for item in body["builtin"]]
    assert keys == [
        "badminton",
        "table_tennis",
        "pickleball",
        "tennis_tiebreak",
        "billiards",
        "darts",
        "board_game",
        "esports",
        "other",
    ]
    badminton = body["builtin"][0]
    assert badminton["name_key"] == "sports.badminton"
    assert badminton["defaults"]["target_score"] == 21
    assert badminton["defaults"]["cap_score"] == 30
    assert badminton["nouns"] == {"venue": "court", "score": "point", "member": "player"}
    table_tennis = body["builtin"][1]
    assert table_tennis["defaults"]["cap_score"] is None
    assert table_tennis["defaults"]["type_params"] == {
        "modules": {"serve_tracking": False, "shot_placement": False}
    }


async def test_anonymous_callers_get_no_custom_activities(client: AsyncClient) -> None:
    response = await client.get("/sports")
    assert response.json()["custom"] == []
