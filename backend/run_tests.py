"""Eventra test runner.

Uses pytest when it is installed. Otherwise it runs the very same test modules
with a tiny built-in harness (each `tmp_path` argument gets a fresh temporary
directory), so the suite is verifiable with zero dependencies:

    python backend/run_tests.py
"""

from __future__ import annotations

import importlib
import inspect
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_DIR = PROJECT_ROOT / "backend" / "tests"


def discover_modules() -> List[str]:
    return sorted(
        f"backend.tests.{path.stem}"
        for path in TEST_DIR.glob("test_*.py")
    )


def run_with_pytest(argv: List[str]) -> int:
    import pytest

    return pytest.main([str(TEST_DIR), "-q", *argv])


def run_standalone(argv: List[str]) -> int:
    filter_text = argv[0] if argv else ""
    passed = 0
    failures: List[Tuple[str, str]] = []
    started = time.perf_counter()

    for module_name in discover_modules():
        module = importlib.import_module(module_name)
        tests: List[Tuple[str, Callable[..., Any]]] = [
            (name, obj)
            for name, obj in vars(module).items()
            if name.startswith("test_") and callable(obj)
        ]
        if not tests:
            continue
        print(f"\n{module_name}")
        for name, func in sorted(tests, key=lambda item: item[1].__code__.co_firstlineno):
            if filter_text and filter_text not in f"{module_name}.{name}":
                continue
            tmp = Path(tempfile.mkdtemp(prefix="eventra-pytest-"))
            try:
                kwargs = {}
                params = inspect.signature(func).parameters
                if "tmp_path" in params:
                    kwargs["tmp_path"] = tmp
                func(**kwargs)
                passed += 1
                print(f"  PASS  {name}")
            except Exception:
                failures.append((f"{module_name}::{name}", traceback.format_exc()))
                print(f"  FAIL  {name}")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    elapsed = time.perf_counter() - started
    print("\n" + "=" * 68)
    for label, tb in failures:
        print(f"FAILED {label}\n{tb}")
    print(f"{passed} passed, {len(failures)} failed in {elapsed:.2f}s")
    print("=" * 68)
    return 1 if failures else 0


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("[eventra] pytest not installed - using the built-in runner")
        return run_standalone(argv)
    return run_with_pytest(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
