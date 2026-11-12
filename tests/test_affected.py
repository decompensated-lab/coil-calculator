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
    commands, tests = run("src/coilcal/wirepair.py")
    assert {"tests/test_wirepair.py", "tests/port/test_pair.py"} <= tests
    assert "tests/test_coilcal.py" not in tests  # never imports wirepair
    assert ["uv", "run", "mypy"] in commands


def test_package_init_reaches_everything_it_reexports():
    _, tests = run("src/coilcal/loops.py")
    assert "tests/test_coilcal.py" in tests  # through `import coilcal as cc`


def test_conftest_and_deleted_modules():
    _, tests = run("tests/port/conftest.py")
    assert "tests/port/test_wire.py" in tests
    _, tests = run("src/coilcal/gone.py")  # a deleted module nobody imports
    assert tests == set()


def test_non_python_changes():
    assert run("README.md") == ([], set())
    commands, tests = run("rust/crates/web/src/lib.rs")
    assert tests == {"tests/port/test_web.py"} and ["cargo", "test", "-q"] in commands
    _, tests = run("rust/crates/core/src/app.rs")
    assert tests == {"tests/port"}
    commands, tests = run("web/src/App.svelte")
    assert ["pnpm", "build"] in commands and tests == set()
    _, tests = run("pyproject.toml", "tests/test_vna.py")
    assert tests == {"tests"}  # the directory covers the file
