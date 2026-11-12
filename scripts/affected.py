"""Run only the checks and tests that a change affects.

    uv run python scripts/affected.py               # uncommitted changes, untracked files too
    uv run python scripts/affected.py --base main   # everything since the branch left main
    uv run python scripts/affected.py -n            # print the plan, run nothing
    uv run python scripts/affected.py -- --port-backend native   # extra pytest arguments

What runs:

* Python files: ruff (check and format) on the changed files, mypy if ``src/`` changed, and
  pytest on the test files whose imports reach a changed module, followed transitively
  through an ``ast`` import graph of ``src/`` and ``tests/`` (each test also depends on the
  ``conftest.py`` files above it).
* ``rust/``: cargo fmt/clippy/test and the port tests (only ``test_web.py`` if just
  ``crates/web`` changed).
* ``web/``: svelte-check and the production build; ``test_web.py`` if the protocol client or
  the smoke script changed.
* Shared configuration (``pyproject.toml``, ``uv.lock``): everything on the Python side.
* Documentation (``*.md``) and other files: nothing.

Assumption: package ``__init__`` files only re-export. ``from coilcal.x import y`` therefore
depends on ``coilcal.x`` but not on ``coilcal/__init__.py``, while ``import coilcal`` (or
``from coilcal import name``, where ``name`` is not a submodule) depends on the ``__init__``
and through it on everything it re-exports. The full suite stays the final check before a
commit (AGENTS.md).
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
PORT = TESTS / "port"
TEST_WEB = "tests/port/test_web.py"
EVERYTHING = {"pyproject.toml", "uv.lock"}
WEB_CLIENT = {"web/src/lib/protocol.ts", "web/scripts/smoke.ts"}


def changed_files(base: str | None) -> set[str]:
    """Paths relative to the repository root: diff against HEAD (or the merge base with
    ``base``), plus untracked files."""

    def git(*args: str) -> list[str]:
        out = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
        return [line for line in out.stdout.splitlines() if line]

    ref = git("merge-base", base, "HEAD")[0] if base else "HEAD"
    return set(git("diff", "--name-only", ref)) | set(
        git("ls-files", "--others", "--exclude-standard")
    )


# ---- Python import graph ------------------------------------------------------------------


def module_path(name: str) -> Path | None:
    """File of module ``coilcal...`` (the ``.py`` path even if it was deleted), else None."""
    if name != "coilcal" and not name.startswith("coilcal."):
        return None
    base = SRC.joinpath(*name.split("."))
    package = base / "__init__.py"
    return package if package.exists() else base.with_suffix(".py")


def resolve(name: str, importer: Path) -> Path | None:
    """``coilcal...`` modules, or a module next to a test file (conftest, _bem2d, test_app)."""
    found = module_path(name)
    if found is None and "." not in name and importer.is_relative_to(TESTS):
        local = importer.parent / f"{name}.py"
        found = local if local.exists() else None
    return found


@cache
def imports(path: Path) -> frozenset[Path]:
    """Files ``path`` imports directly."""
    if not path.exists():
        return frozenset()
    out: set[Path | None] = set()
    tree = ast.parse(path.read_text(), filename=str(path))
    package: list[str] = []
    if path.is_relative_to(SRC):
        package = list(path.relative_to(SRC).with_suffix("").parts)
        if package[-1] == "__init__":
            package.pop()
        else:
            package = package[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(resolve(a.name, path) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative: only used inside src/
                parts = package[: len(package) - (node.level - 1)]
                base = ".".join(parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            for alias in node.names:
                sub = module_path(f"{base}.{alias.name}")
                if sub is not None and sub.exists():
                    out.add(sub)  # a submodule: from coilcal import mutual
                else:
                    out.add(resolve(base, path))  # a name from the module itself
    if path.name.startswith("test_"):  # pytest loads the conftest files above a test
        out.update(d / "conftest.py" for d in path.parents if d.is_relative_to(TESTS))
    return frozenset(p for p in out if p is not None and p != path)


def closure(path: Path) -> set[Path]:
    seen, todo = {path}, [path]
    while todo:
        for dep in imports(todo.pop()):
            if dep not in seen:
                seen.add(dep)
                todo.append(dep)
    return seen


def affected_tests(changed: set[Path]) -> set[Path]:
    return {t for t in TESTS.rglob("test_*.py") if closure(t) & changed}


# ---- plan ---------------------------------------------------------------------------------


@dataclass
class Plan:
    commands: list[tuple[str, list[str]]] = field(default_factory=list)  # (cwd, argv)
    tests: set[str] = field(default_factory=set)  # test files or directories for pytest

    def add(self, cwd: str, *argv: str) -> None:
        if (cwd, list(argv)) not in self.commands:
            self.commands.append((cwd, list(argv)))


def plan(files: set[str], pytest_args: Sequence[str] = ()) -> Plan:
    p = Plan()
    py = sorted(f for f in files if f.endswith(".py"))
    existing = [f for f in py if (ROOT / f).exists()]
    if files & EVERYTHING:
        p.add(".", "uv", "run", "ruff", "check", "src", "tests", "examples")
        p.add(".", "uv", "run", "ruff", "format", "--check", "src", "tests", "examples")
        p.add(".", "uv", "run", "mypy")
        p.tests.add("tests")
    elif py:
        if existing:
            p.add(".", "uv", "run", "ruff", "check", *existing)
            p.add(".", "uv", "run", "ruff", "format", "--check", *existing)
        if any(f.startswith("src/") for f in py):
            p.add(".", "uv", "run", "mypy")
        changed = {(ROOT / f).resolve() for f in py}
        p.tests.update(str(t.relative_to(ROOT)) for t in affected_tests(changed))
    rust = [f for f in files if f.startswith("rust/")]
    if rust:
        p.add("rust", "cargo", "fmt", "--check")
        p.add("rust", "cargo", "clippy", "--all-targets", "--", "-D", "warnings")
        p.add("rust", "cargo", "test", "-q")
        only_web = all(f.startswith("rust/crates/web/") for f in rust)
        p.tests.add(TEST_WEB if only_web else str(PORT.relative_to(ROOT)))
    web = [f for f in files if f.startswith("web/") and not f.endswith((".py", ".md"))]
    if web:
        p.add("web", "pnpm", "check")
        p.add("web", "pnpm", "build")
        if set(web) & WEB_CLIENT or any(
            f.startswith(("web/package.json", "web/pnpm-")) for f in web
        ):
            p.tests.add(TEST_WEB)
    # a directory covers the files in it
    dirs = {t for t in p.tests if (ROOT / t).is_dir()}
    p.tests = {t for t in p.tests if t in dirs or not any(t.startswith(d + "/") for d in dirs)}
    if p.tests:
        p.add(".", "uv", "run", "pytest", "-q", *sorted(p.tests), *pytest_args)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", help="compare with the merge base of this ref instead of HEAD")
    ap.add_argument("-n", "--dry-run", action="store_true", help="print the plan only")
    ap.add_argument("--files", nargs="+", help="use these paths instead of asking git")
    ap.add_argument("pytest_args", nargs="*", help="after --: extra pytest arguments")
    args = ap.parse_args()
    files = set(args.files) if args.files else changed_files(args.base)
    p = plan(files, args.pytest_args)
    print(f"{len(files)} changed file(s)")
    if not p.commands:
        print("nothing to check")
        return 0
    failed = []
    for cwd, argv in p.commands:
        print(f"\n$ {'' if cwd == '.' else f'(cd {cwd}) '}{' '.join(argv)}", flush=True)
        if not args.dry_run and subprocess.run(argv, check=False, cwd=ROOT / cwd).returncode:
            failed.append(" ".join(argv[:4]))
    if failed:
        print("\nfailed:", *failed, sep="\n  ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
