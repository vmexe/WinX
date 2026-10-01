#!/usr/bin/env python3
"""Static check that every intra-package import in ``winx`` resolves.

The GUI layer cannot be imported on a headless CI box without the Qt runtime
libraries, so a typo such as ``from .config import Settings`` inside
``winx/app.py`` (the module actually lives at ``winx/core/config.py``) survived
both the self-test and the PyInstaller build and only blew up on a user's
machine.

This script reads every module in the package with ``ast`` — no imports, no Qt
— and verifies that:

* ``import winx.x.y`` / ``from .x import …`` point at a module that exists;
* each name in ``from <winx module> import a, b`` is either a submodule of that
  package or a top-level binding (def/class/assignment/import/__all__ entry) of
  the target module.

Run it directly:  ``python tools/check_imports.py``
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "winx"


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def module_path(name: str) -> Path | None:
    """File backing a dotted module name, or None when it does not exist."""
    base = ROOT.joinpath(*name.split("."))
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    return None


def top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Try):  # try/except ImportError fallbacks
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for alias in sub.names:
                        if alias.name != "*":
                            names.add(alias.asname or alias.name.split(".")[0])
    return names


def resolve(node: ast.ImportFrom, current: str, is_package: bool) -> str | None:
    """Absolute module name a ``from … import`` statement refers to."""
    if node.level == 0:
        return node.module
    parts = current.split(".")
    if not is_package:
        parts = parts[:-1]
    up = node.level - 1
    if up:
        if up > len(parts):
            return None
        parts = parts[: len(parts) - up]
    if node.module:
        parts += node.module.split(".")
    return ".".join(parts)


def main() -> int:
    errors: list[str] = []
    files = sorted((ROOT / PACKAGE).rglob("*.py")) + [ROOT / "main.py"]
    cache: dict[str, tuple[ast.Module, set[str]]] = {}

    def load(name: str) -> tuple[ast.Module, set[str]] | None:
        if name not in cache:
            path = module_path(name)
            if path is None:
                return None
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            cache[name] = (tree, top_level_names(tree))
        return cache[name]

    for path in files:
        name = module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        is_package = path.name == "__init__.py"
        where = path.relative_to(ROOT).as_posix()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == PACKAGE or alias.name.startswith(PACKAGE + "."):
                        if module_path(alias.name) is None:
                            errors.append(
                                f"{where}:{node.lineno}: no module named {alias.name!r}"
                            )
            elif isinstance(node, ast.ImportFrom):
                target = resolve(node, name, is_package)
                if not target or not (
                    target == PACKAGE or target.startswith(PACKAGE + ".")
                ):
                    continue  # third-party / stdlib: not our business
                loaded = load(target)
                if loaded is None:
                    errors.append(
                        f"{where}:{node.lineno}: no module named {target!r}"
                    )
                    continue
                _, bindings = loaded
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if alias.name in bindings:
                        continue
                    if module_path(f"{target}.{alias.name}") is not None:
                        continue
                    errors.append(
                        f"{where}:{node.lineno}: "
                        f"{target!r} has no attribute or submodule {alias.name!r}"
                    )

    for message in errors:
        print(f"FAIL  {message}")
    checked = len(files)
    if errors:
        print(f"\n{len(errors)} broken import(s) across {checked} modules")
        return 1
    print(f"ok    every intra-package import resolves ({checked} modules checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
