from __future__ import annotations

from ai_risk_manager.collectors.plugins.base import CollectorPlugin, StackId
from ai_risk_manager.collectors.plugins.django import DjangoCollectorPlugin
from ai_risk_manager.collectors.plugins.fastapi import FastAPICollectorPlugin
from ai_risk_manager.collectors.plugins.sdk import CapabilitySignalPlugin

_FASTAPI_PLUGIN = FastAPICollectorPlugin()
_DJANGO_PLUGIN = DjangoCollectorPlugin()
_PLUGINS: dict[StackId, CollectorPlugin] = {
    "fastapi_pytest": _FASTAPI_PLUGIN,
    "django_drf": _DJANGO_PLUGIN,
}


def get_plugin_for_stack(stack_id: StackId) -> CollectorPlugin | None:
    return _PLUGINS.get(stack_id)


def get_signal_plugin_for_stack(stack_id: StackId) -> CapabilitySignalPlugin | None:
    plugin = _PLUGINS.get(stack_id)
    if isinstance(plugin, CapabilitySignalPlugin):
        return plugin
    return None


def get_default_plugin() -> CollectorPlugin:
    return _FASTAPI_PLUGIN


def list_registered_stacks() -> tuple[StackId, ...]:
    return tuple(_PLUGINS.keys())


def list_plugins() -> tuple[CollectorPlugin, ...]:
    return tuple(_PLUGINS.values())


def list_signal_plugins() -> tuple[CapabilitySignalPlugin, ...]:
    return tuple(plugin for plugin in _PLUGINS.values() if isinstance(plugin, CapabilitySignalPlugin))
