"""Core registry of sport type plugins (spec 043, constitution XII).

Core code looks a plugin up by the `type_key` snapshotted on a group or match
and never imports `app.sports.types` itself; the composition roots fill this
registry through `app.sports.types.register_all()`.
"""

from app.sports.plugin import BasePlugin, UnknownSportType

_PLUGINS: dict[str, BasePlugin] = {}


def register(plugin: BasePlugin) -> None:
    """Add a plugin. Re-registering the same class is a no-op, so the
    composition roots can call `register_all()` more than once."""
    existing = _PLUGINS.get(plugin.type_key)
    if existing is not None:
        if type(existing) is type(plugin):
            return
        raise ValueError(f"sport type {plugin.type_key!r} is already registered")
    _PLUGINS[plugin.type_key] = plugin


def get(type_key: str) -> BasePlugin:
    try:
        return _PLUGINS[type_key]
    except KeyError:
        raise UnknownSportType(type_key) from None


def type_keys() -> tuple[str, ...]:
    return tuple(_PLUGINS)


def plugins() -> tuple[BasePlugin, ...]:
    return tuple(_PLUGINS.values())


def snapshot() -> dict[str, BasePlugin]:
    """For tests: capture the registry to restore afterwards."""
    return dict(_PLUGINS)


def restore(saved: dict[str, BasePlugin]) -> None:
    _PLUGINS.clear()
    _PLUGINS.update(saved)
