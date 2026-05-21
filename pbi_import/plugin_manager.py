"""
Plugin Manager — extensible plugin architecture for migration customisation.

Allows users to register custom plugins (Python modules) that hook into
the migration pipeline at defined extension points (pre/post each phase).
"""

import importlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Extension points where plugins can hook
EXTENSION_POINTS = [
    "pre_assessment",
    "post_assessment",
    "pre_export",
    "post_export",
    "pre_conversion",
    "post_conversion",
    "pre_import",
    "post_import",
    "pre_validation",
    "post_validation",
]


class PluginManager:
    """Manage and execute migration pipeline plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, dict] = {}
        self._hooks: dict[str, list[Callable[..., Any]]] = {
            ep: [] for ep in EXTENSION_POINTS
        }

    def register_module(self, name: str, module_path: str) -> dict:
        """Register a plugin from a Python module file.

        The module must define a ``register(manager)`` function that calls
        ``manager.add_hook(extension_point, callback)``.
        """
        path = Path(module_path)
        if not path.exists():
            logger.error("Plugin file not found: %s", module_path)
            return {"name": name, "status": "error", "error": "File not found"}

        try:
            spec = importlib.util.spec_from_file_location(name, str(path))
            if spec is None or spec.loader is None:
                return {"name": name, "status": "error", "error": "Invalid module"}

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Call register function if it exists
            register_fn = getattr(module, "register", None)
            if register_fn:
                register_fn(self)

            self._plugins[name] = {
                "name": name,
                "path": str(path),
                "status": "loaded",
                "hooks": self._get_plugin_hooks(name),
            }
            logger.info("Plugin loaded: %s from %s", name, path)
            return self._plugins[name]

        except Exception as e:
            logger.error("Failed to load plugin %s: %s", name, e)
            return {"name": name, "status": "error", "error": str(e)}

    def add_hook(self, extension_point: str, callback: Callable[..., Any], name: str = "") -> None:
        """Add a hook to an extension point.

        Args:
            extension_point: one of ``EXTENSION_POINTS``.
            callback: function to call at this extension point.
            name: optional hook name for identification.
        """
        if extension_point not in self._hooks:
            logger.warning("Unknown extension point: %s", extension_point)
            return

        # Tag the callback for identification
        if name:
            callback._plugin_name = name  # type: ignore[attr-defined]

        self._hooks[extension_point].append(callback)
        logger.debug("Hook added: %s → %s", extension_point, name or callback.__name__)

    def execute_hooks(self, extension_point: str, context: dict) -> dict:
        """Execute all hooks for an extension point.

        Args:
            extension_point: the extension point to trigger.
            context: migration context dict (passed to each hook).
        """
        hooks = self._hooks.get(extension_point, [])
        if not hooks:
            return {"extension_point": extension_point, "hooks_executed": 0}

        results: list[dict] = []
        for hook in hooks:
            hook_name = getattr(hook, "_plugin_name", hook.__name__)
            try:
                result = hook(context)
                results.append({"hook": hook_name, "status": "ok", "result": str(result)})
            except Exception as e:
                results.append({"hook": hook_name, "status": "error", "error": str(e)})
                logger.error("Hook %s failed: %s", hook_name, e)

        return {
            "extension_point": extension_point,
            "hooks_executed": len(results),
            "results": results,
        }

    def list_plugins(self) -> list[dict]:
        """List all registered plugins."""
        return list(self._plugins.values())

    def list_hooks(self) -> dict[str, int]:
        """List extension points and hook counts."""
        return {ep: len(hooks) for ep, hooks in self._hooks.items()}

    def unregister(self, name: str) -> None:
        """Unregister a plugin and remove its hooks."""
        self._plugins.pop(name, None)
        for ep in self._hooks:
            self._hooks[ep] = [
                h for h in self._hooks[ep]
                if getattr(h, "_plugin_name", "") != name
            ]
        logger.info("Plugin unregistered: %s", name)

    def save_status(self, output_dir: str) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "plugin_status.json"
        data = {
            "plugins": self.list_plugins(),
            "hooks": self.list_hooks(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    def _get_plugin_hooks(self, name: str) -> list[str]:
        """Get extension points where a plugin has hooks."""
        result: list[str] = []
        for ep, hooks in self._hooks.items():
            for h in hooks:
                if getattr(h, "_plugin_name", "") == name:
                    result.append(ep)
        return result
