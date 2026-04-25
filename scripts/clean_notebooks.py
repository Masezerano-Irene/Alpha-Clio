"""
Strip outputs and normalize Jupyter notebooks so they always pass nbformat.validate().

Use this whenever a notebook shows "file is corrupted / cannot be opened" in
Cursor or Jupyter — the usual cause is one malformed output object (e.g. a
``stream`` output missing the required ``name`` field). Clearing outputs always
fixes that, makes the file small, and the outputs regenerate on Run All.

Usage
-----
    python scripts/clean_notebooks.py                  # clean every .ipynb under repo
    python scripts/clean_notebooks.py path/to.ipynb    # clean specific files
"""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat

_REPO_ROOT = Path(__file__).resolve().parents[1]


def clean(p: Path) -> None:
    nb = nbformat.read(p, as_version=4)

    n_outputs = 0
    for cell in nb.cells:
        if cell.get("metadata") is None:
            cell["metadata"] = {}
        if cell.cell_type == "code":
            n_outputs += len(getattr(cell, "outputs", []) or [])
            cell.outputs = []
            cell["execution_count"] = None

    nbformat.write(nb, p)
    nbformat.validate(nbformat.read(p, as_version=4))
    size_kb = p.stat().st_size / 1024
    print(f"  ✓ {p.relative_to(_REPO_ROOT) if p.is_relative_to(_REPO_ROOT) else p}"
          f"  ({n_outputs} outputs cleared, {size_kb:.1f} KB)")


def main() -> None:
    if len(sys.argv) > 1:
        targets = [Path(a) for a in sys.argv[1:]]
    else:
        targets = [
            p for p in _REPO_ROOT.rglob("*.ipynb")
            if ".ipynb_checkpoints" not in p.parts
            and ".venv" not in p.parts
        ]

    if not targets:
        print("No notebooks found.")
        return

    print(f"Cleaning {len(targets)} notebook(s):")
    for p in targets:
        try:
            clean(p)
        except Exception as exc:
            print(f"  ✗ {p}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
