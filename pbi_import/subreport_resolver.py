"""
Subreport Resolver — build a dependency graph of subreport references
and compute a safe import order.

Ensures parent reports are imported after their subreports so that
references resolve correctly in PBI Online.
"""

import logging
from pathlib import Path
from typing import Any

from pbirs_export.rdl_analyser import RdlAnalyser

logger = logging.getLogger(__name__)


class SubreportResolver:
    """Resolve subreport dependencies and compute import order."""

    def __init__(self, catalog: dict, rdl_dir: str | Path | None = None):
        self.catalog = catalog
        self.rdl_dir = Path(rdl_dir) if rdl_dir else None
        # name → item mapping for fast lookup
        self._item_by_name: dict[str, dict] = {
            item.get("Name", ""): item
            for item in catalog.get("items", [])
        }
        # path → item mapping
        self._item_by_path: dict[str, dict] = {
            item.get("Path", ""): item
            for item in catalog.get("items", [])
        }

    def resolve(self) -> dict[str, Any]:
        """Build dependency graph and compute import order.

        Returns::

            {
                "dependency_graph": {parent_path: [child_path, ...]},
                "import_order": [path, ...],     # leaves first
                "ordered_paths": [path, ...],    # alias for legacy callers
                "circular": [path, ...],         # items in cycles
                "cycle_groups": [[path, ...]],   # strongly connected groups
                "cycle_mitigation": {
                    "strategy": "retry-cycles",
                    "retry_passes": 2,
                    "bootstrap_order": [path, ...],
                    "groups": [[path, ...]],
                },
                "orphan_refs": [{...}],          # references to missing reports
            }
        """
        graph: dict[str, list[str]] = {}
        orphan_refs: list[dict] = []

        for item in self.catalog.get("items", []):
            if item.get("Type") not in ("Report", "LinkedReport"):
                continue

            item_path = item.get("Path", "")
            subreports = self._get_subreport_refs(item)

            deps: list[str] = []
            for ref in subreports:
                resolved = self._resolve_ref(ref, item_path)
                if resolved:
                    deps.append(resolved)
                else:
                    orphan_refs.append({
                        "parent": item_path,
                        "missing_ref": ref,
                    })

            if deps:
                graph[item_path] = deps

        import_order, circular = self._topological_sort(graph)
        cycle_groups = self._group_cycles(graph, circular)
        bootstrap_order = self._build_bootstrap_order(import_order, cycle_groups)

        logger.info(
            "Subreport resolution: %d dependencies, %d import order, %d circular, %d orphan refs",
            len(graph), len(import_order), len(circular), len(orphan_refs),
        )

        return {
            "dependency_graph": graph,
            "import_order": import_order,
            "ordered_paths": import_order,
            "circular": circular,
            "cycle_groups": cycle_groups,
            "cycle_mitigation": {
                "strategy": "retry-cycles",
                "retry_passes": 2,
                "bootstrap_order": bootstrap_order,
                "groups": cycle_groups,
            },
            "orphan_refs": orphan_refs,
        }

    # ------------------------------------------------------------------
    # Subreport reference extraction
    # ------------------------------------------------------------------

    def _get_subreport_refs(self, item: dict) -> list[str]:
        """Get subreport reference names from an item.

        If we have the .rdl file on disk, parse it for accurate references.
        Otherwise fall back to catalog metadata hints.
        """
        refs: list[str] = []

        # Try parsing actual RDL file
        if self.rdl_dir:
            item_path = item.get("Path", "").lstrip("/")
            rdl_path = self.rdl_dir / f"{item_path}.rdl"
            if not rdl_path.exists():
                # Try with sanitised name
                name = item.get("Name", "")
                parent = item.get("Path", "/").rsplit("/", 1)[0]
                rdl_path = self.rdl_dir / parent.lstrip("/") / f"{name}.rdl"

            if rdl_path.exists():
                try:
                    analyser = RdlAnalyser(rdl_path)
                    analysis = analyser.analyse()
                    for sub in analysis.get("subreports", []):
                        report_name = sub.get("report_name", "")
                        if report_name:
                            refs.append(report_name)
                    return refs
                except Exception as e:
                    logger.debug("Could not parse RDL %s: %s", rdl_path, e)

        # Fallback: use catalog-level subreport hints if available
        for sub in item.get("subreports", []):
            name = sub if isinstance(sub, str) else sub.get("report_name", "")
            if name:
                refs.append(name)

        return refs

    # ------------------------------------------------------------------
    # Reference resolution
    # ------------------------------------------------------------------

    def _resolve_ref(self, ref_name: str, parent_path: str) -> str | None:
        """Resolve a subreport name to a catalog item path.

        SSRS subreport references can be:
          - Relative to the parent folder  (e.g. "SubReport1")
          - Absolute path                  (e.g. "/Finance/SubReport1")
        """
        # Try absolute path first
        if ref_name.startswith("/"):
            if ref_name in self._item_by_path:
                return ref_name
            return None

        # Resolve relative to parent's folder
        parent_folder = parent_path.rsplit("/", 1)[0] if "/" in parent_path else ""
        candidate = f"{parent_folder}/{ref_name}"
        if candidate in self._item_by_path:
            return candidate

        # Try by name anywhere
        if ref_name in self._item_by_name:
            return self._item_by_name[ref_name].get("Path", "")

        return None

    # ------------------------------------------------------------------
    # Topological sort (Kahn's algorithm)
    # ------------------------------------------------------------------

    @staticmethod
    def _topological_sort(graph: dict[str, list[str]]) -> tuple[list[str], list[str]]:
        """Topological sort of the dependency graph.

        Returns (ordered_list, circular_nodes).
        ordered_list has leaves (no dependencies) first — safe import order.
        """
        # Collect all nodes
        all_nodes: set[str] = set(graph.keys())
        for deps in graph.values():
            all_nodes.update(deps)

        # Build in-degree map
        in_degree: dict[str, int] = {n: 0 for n in all_nodes}
        for parent, children in graph.items():
            for child in children:
                # parent depends on child → edge from child to parent
                in_degree.setdefault(parent, 0)
                in_degree.setdefault(child, 0)

        # In our graph, parent → [children it depends on]
        # For topological sort: a parent cannot be imported until its children are.
        # Build reverse adjacency: child → parents that depend on it
        reverse: dict[str, list[str]] = {n: [] for n in all_nodes}
        for parent, children in graph.items():
            for child in children:
                reverse.setdefault(child, []).append(parent)
            in_degree[parent] = len(children)

        # Kahn's algorithm
        queue = [n for n in all_nodes if in_degree[n] == 0]
        order: list[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for dependent in reverse.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        circular = [n for n in all_nodes if n not in set(order)]
        return order, circular

    @staticmethod
    def _group_cycles(graph: dict[str, list[str]], circular_nodes: list[str]) -> list[list[str]]:
        """Group circular nodes into strongly connected components."""
        if not circular_nodes:
            return []

        circular_set = set(circular_nodes)
        subgraph: dict[str, list[str]] = {
            node: [child for child in graph.get(node, []) if child in circular_set]
            for node in circular_set
        }
        groups = SubreportResolver._strongly_connected_components(subgraph)

        # Keep only true cycles (>1 node) or explicit self-loops.
        cycle_groups: list[list[str]] = []
        for group in groups:
            if len(group) > 1:
                cycle_groups.append(sorted(group))
                continue
            node = group[0]
            if node in subgraph.get(node, []):
                cycle_groups.append([node])

        cycle_groups.sort(key=lambda g: g[0])
        return cycle_groups

    @staticmethod
    def _build_bootstrap_order(import_order: list[str], cycle_groups: list[list[str]]) -> list[str]:
        """Build a deterministic publish order that appends cycle groups for retry passes."""
        seen: set[str] = set()
        ordered: list[str] = []

        for path in import_order:
            if path not in seen:
                ordered.append(path)
                seen.add(path)

        for group in cycle_groups:
            for path in group:
                if path not in seen:
                    ordered.append(path)
                    seen.add(path)

        return ordered

    @staticmethod
    def _strongly_connected_components(graph: dict[str, list[str]]) -> list[list[str]]:
        """Return strongly connected components using Tarjan's algorithm."""
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        index_map: dict[str, int] = {}
        lowlink_map: dict[str, int] = {}
        components: list[list[str]] = []

        def _visit(node: str) -> None:
            nonlocal index
            index_map[node] = index
            lowlink_map[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbour in graph.get(node, []):
                if neighbour not in index_map:
                    _visit(neighbour)
                    lowlink_map[node] = min(lowlink_map[node], lowlink_map[neighbour])
                elif neighbour in on_stack:
                    lowlink_map[node] = min(lowlink_map[node], index_map[neighbour])

            if lowlink_map[node] == index_map[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)

        for node in graph:
            if node not in index_map:
                _visit(node)

        return components
