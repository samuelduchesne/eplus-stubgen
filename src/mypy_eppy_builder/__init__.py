"""mypy-eppy-builder: stub generator for EnergyPlus-based libraries.

This package provides a small set of utilities to parse EnergyPlus IDD files
and emit type stubs for the `eppy` and `archetypal` libraries.  See
`build_cli.py` for the command-line interface.
"""

__all__ = [
    "idd_parser",
    "typed_emitter",
]