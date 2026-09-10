"""Mechanism Isolation and Authority Boundary Invariant Tests.

Guarantees Invariant 12:
"LLMs may draft envelopes, plan carts, rank eligible recoveries, and explain
decisions. They may not activate authority, define trusted catalog facts, decide
envelope membership, widen policy, mint grants, or dispatch actions."

Specifically verifies:
1. AST import graph: No module in the authorization, dispatch, or service layer
   transitively imports app.baselines.
2. Invariant: No authorization module ever reads product["description"].
"""
from __future__ import annotations

import ast
from pathlib import Path
import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Root entrypoints of the authorization and execution surface
AUTHORIZATION_SURFACE_ROOTS = [
    "agent.py",
    "agent_commerce.py",
    "autopilot.py",
    "commerce_service.py",
    "commerce_mcp.py",
    "envelope.py",
    "mandate.py",
]


def _get_module_imports(py_file: Path) -> set[str]:
    """Parse a python file with AST and return all imported module names."""
    content = py_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(py_file))
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                if node.level > 0:
                    # Relative import within app package
                    # level 1 from app/sub.py -> app
                    dots = "." * (node.level - 1)
                    imports.add(f".{dots}{node.module}")
                else:
                    imports.add(node.module)
            elif node.level > 0:
                imports.add("." * node.level)
    return imports


def test_no_authorization_module_transitively_imports_baselines():
    """Assert none of the authorization surface modules transitively imports app.baselines.

    Fails with the exact import path if an isolation breach occurs.
    """
    visited: set[str] = set()

    def resolve_app_module(current_file: Path, import_name: str) -> Path | None:
        """Resolve an import statement to a file within app/ if applicable."""
        if import_name.startswith("app.baselines") or import_name == "baselines":
            return APP_DIR / "baselines" / "semantic_entailment.py"

        if import_name.startswith("app."):
            rel = import_name.replace("app.", "").replace(".", "/")
            candidate = APP_DIR / f"{rel}.py"
            if candidate.exists():
                return candidate
            candidate_dir = APP_DIR / rel / "__init__.py"
            if candidate_dir.exists():
                return candidate_dir

        if import_name.startswith("."):
            # Relative import from current_file
            level = len(import_name) - len(import_name.lstrip("."))
            module_part = import_name.lstrip(".")
            base = current_file.parent
            for _ in range(level - 1):
                base = base.parent
            if module_part:
                candidate = base / f"{module_part.replace('.', '/')}.py"
                if candidate.exists():
                    return candidate
                candidate_dir = base / module_part.replace(".", "/") / "__init__.py"
                if candidate_dir.exists():
                    return candidate_dir
            else:
                return base / "__init__.py"

        # Check if it's a top-level module in app
        candidate = APP_DIR / f"{import_name}.py"
        if candidate.exists():
            return candidate

        return None

    for root_name in AUTHORIZATION_SURFACE_ROOTS:
        root_path = APP_DIR / root_name
        assert root_path.exists(), f"Root file {root_path} does not exist"

        # DFS traversal tracking the import chain
        stack: list[tuple[Path, list[str]]] = [(root_path, [root_name])]
        local_visited: set[Path] = {root_path}

        while stack:
            curr_file, path_chain = stack.pop()
            imported_names = _get_module_imports(curr_file)

            for imp in imported_names:
                if "baselines" in imp or imp.startswith("app.baselines"):
                    chain_str = " -> ".join(path_chain + [imp])
                    pytest.fail(
                        f"Invariant 12 breach! Transitively imported baseline module:\n"
                        f"Chain: {chain_str}\n"
                        f"Baselines must remain isolated from authorization paths."
                    )

                resolved = resolve_app_module(curr_file, imp)
                if resolved and resolved.exists() and resolved not in local_visited:
                    local_visited.add(resolved)
                    stack.append((resolved, path_chain + [resolved.name]))


def test_no_authorization_module_reads_product_description():
    """Assert that authorization modules never read product['description'] or item description.

    The deterministic action firewall evaluates quotes against envelopes strictly using
    server-resolved facts: category, tags, sku, price_paise, and quantity.
    Free-text descriptions are never part of authorization decisions.
    """
    auth_files = [
        APP_DIR / "envelope.py",
        APP_DIR / "channel_policy.py",
        APP_DIR / "authorization.py",
        APP_DIR / "approval_tokens.py",
    ]

    for auth_file in auth_files:
        assert auth_file.exists(), f"{auth_file} not found"
        content = auth_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(auth_file))

        for node in ast.walk(tree):
            # Check for dict subscript: x["description"]
            if isinstance(node, ast.Subscript):
                if isinstance(node.slice, ast.Constant) and node.slice.value == "description":
                    pytest.fail(
                        f"{auth_file.name}:{node.lineno} accesses ['description']. "
                        f"Authorization must never inspect product description text."
                    )
            # Check for dict.get("description")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "get":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and arg.value == "description":
                            pytest.fail(
                                f"{auth_file.name}:{node.lineno} accesses .get('description'). "
                                f"Authorization must never inspect product description text."
                            )
