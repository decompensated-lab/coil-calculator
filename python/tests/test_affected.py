"""scripts/affected.py: which checks and tests a change selects."""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "affected", Path(__file__).parents[1] / "scripts/affected.py"
)
assert spec is not None and spec.loader is not None
affected = importlib.util.module_from_spec(spec)
sys.modules["affected"] = affected  # dataclasses look their module up there
spec.loader.exec_module(affected)


def run(*files: str) -> tuple[list[list[str]], set[str]]:
    p = affected.plan(set(files))
    return [argv for _, argv in p.commands], p.tests


def test_python_module_selects_its_importers_only():
    commands, tests = run("python/src/coilcal/wirepair.py")
    assert {"python/tests/test_wirepair.py", "python/tests/port/test_pair.py"} <= tests
    assert "python/tests/test_coilcal.py" not in tests  # never imports wirepair
    assert ["uv", "run", "mypy"] in commands
    # the Python commands run in python/, with paths relative to it
    assert ["uv", "run", "ruff", "check", "src/coilcal/wirepair.py"] in commands
    pytest = next(c for c in commands if c[2] == "pytest")
    assert "tests/test_wirepair.py" in pytest


def test_package_init_reaches_everything_it_reexports():
    _, tests = run("python/src/coilcal/loops.py")
    assert "python/tests/test_coilcal.py" in tests  # through `import coilcal as cc`


def test_conftest_and_deleted_modules():
    _, tests = run("python/tests/port/conftest.py")
    assert "python/tests/port/test_wire.py" in tests
    _, tests = run("python/src/coilcal/gone.py")  # a deleted module nobody imports
    assert tests == set()


def test_non_python_changes():
    assert run("README.md") == ([], set())
    commands, tests = run("web/rust/crates/web/src/lib.rs")
    assert tests == {"python/tests/port/test_web.py"} and ["cargo", "test", "-q"] in commands
    assert ["pnpm", "build"] not in commands  # the Rust workspace is not the Svelte app
    _, tests = run("web/rust/crates/core/src/app.rs")
    assert tests == {"python/tests/port"}
    commands, tests = run("web/src/App.svelte")
    assert ["pnpm", "build"] in commands and tests == set()
    commands, tests = run("python/pyproject.toml", "python/tests/test_vna.py")
    assert tests == {"python/tests"}  # the directory covers the file
    assert ["uv", "run", "pytest", "-q", "tests"] in commands
