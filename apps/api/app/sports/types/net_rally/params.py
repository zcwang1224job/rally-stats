"""`type_params` of the net rally sport type (spec 043 data-model §6/§8)."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict


class NetRallyModules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Both default on: every pre-043 group was badminton with `{}` params.
    serve_tracking: bool = True
    shot_placement: bool = True


class NetRallyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modules: NetRallyModules = NetRallyModules()


def parse_params(raw: Mapping[str, Any]) -> NetRallyParams:
    return NetRallyParams.model_validate(dict(raw))
