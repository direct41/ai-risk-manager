from __future__ import annotations

from ai_risk_manager.collectors.plugins.base import CollectorPlugin, StackId
from ai_risk_manager.collectors.plugins.fastapi import FastAPICollectorPlugin

_FASTAPI_PLUGIN = FastAPICollectorPlugin()
_PLUGINS: dict[StackId, CollectorPlugin] = {
    "fastapi_pytest": _FASTAPI_PLUGIN,
}


def get_plugin_for_stack(stack_id: StackId) -> CollectorPlugin | None:
    return _PLUGINS.get(stack_id)


def get_default_plugin() -> CollectorPlugin:
    return _FASTAPI_PLUGIN


def list_registered_stacks() -> tuple[StackId, ...]:
    return tuple(_PLUGINS.keys())


def list_plugins() -> tuple[CollectorPlugin, ...]:
    return tuple(_PLUGINS.values())
