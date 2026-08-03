"""Build baseline: every production module compiles (no syntax errors).

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    The cheapest, broadest safety net. Compiling every .py under Automation/
    (excluding tests and bytecode caches) catches syntax errors introduced by a
    refactor even for modules that can't be imported headlessly (they need
    tkinter / a real arm). This is the "build is green" gate that must pass
    after every refactor step.
"""

import os
import py_compile

import pytest

AUTOMATION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _production_py_files():
    skip = {"__pycache__", "tests"}
    for root, dirs, files in os.walk(AUTOMATION_ROOT):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


@pytest.mark.parametrize(
    "path",
    sorted(_production_py_files()),
    ids=lambda p: os.path.relpath(p, AUTOMATION_ROOT),
)
def test_module_compiles(path):
    py_compile.compile(path, doraise=True)
