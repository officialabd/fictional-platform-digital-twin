"""Guards the hard rules that keep the simulator and the twin apart."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN_IMPORTS = {
    "simulator": {"twin"},
    "twin": {"simulator"},
    "shared": {"simulator", "twin"},
}


def python_files(package: str) -> list[Path]:
    return list((SRC / package).rglob("*.py"))


def imported_packages(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("package, forbidden", FORBIDDEN_IMPORTS.items())
def test_packages_never_import_each_other(package, forbidden):
    for path in python_files(package):
        assert not imported_packages(path) & forbidden, path


def test_simulator_does_not_read_the_graph_data():
    for path in python_files("simulator"):
        source = path.read_text(encoding="utf-8")
        assert "nodes.csv" not in source and "edges.csv" not in source, path


def test_only_mqtt_link_knows_about_mqtt():
    for path in python_files("simulator"):
        if path.name != "mqtt_link.py":
            assert "paho" not in imported_packages(path), path


def test_twin_does_not_touch_the_truth_log():
    for path in python_files("twin"):
        assert "truth.db" not in path.read_text(encoding="utf-8"), path
