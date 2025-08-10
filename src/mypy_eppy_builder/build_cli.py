"""Command-line interface for stub generation.

This module exposes a CLI entry point that reads an EnergyPlus IDD file,
parses it into a structured representation, and then emits two stub-only
packages: ``eppy-stubs`` and ``archetypal-stubs``.  Each package lives
under ``generated_package/`` with a version derived from the EnergyPlus
``major.minor`` and an optional patch number.

The generated packages contain:

* ``src/eppy`` or ``src/archetypal`` directories with only ``.pyi`` files
  (and a minimal ``src/geomeppy`` shim for the archetypal package).
* A ``pyproject.toml`` describing the stub-only wheel.
* A short ``README.md`` explaining how to install the package.
* A ``generated_by.json`` recording provenance data.

Example invocation::

    uv run python -m mypy_eppy_builder.build_cli \
        --idd /path/to/Energy+.idd \
        --eplus 23.1 \
        --patch 0 \
        --out generated_package

This will write ``generated_package/eppy-stubs-23.1.0`` and
``generated_package/archetypal-stubs-23.1.0``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from jinja2 import Environment, FileSystemLoader

from .idd_parser import parse_idd
from .typed_emitter import emit_kwarg_typeddicts, emit_idf_overloads


def _compute_sha256(path: Path) -> str:
    """Return the SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Generate stub-only wheels from an EnergyPlus IDD.")
    parser.add_argument(
        "--idd",
        required=True,
        help="Path to the EnergyPlus IDD file (Energy+.idd)",
    )
    parser.add_argument(
        "--eplus",
        required=True,
        help="EnergyPlus version (major.minor), e.g. 23.1",
    )
    parser.add_argument(
        "--patch",
        type=int,
        default=0,
        help="Patch version number for the stubs (default: 0)",
    )
    parser.add_argument(
        "--out",
        default="generated_package",
        help="Output directory into which the packages will be written",
    )
    args = parser.parse_args()
    idd_path = Path(args.idd)
    if not idd_path.exists():
        raise SystemExit(f"IDD file not found: {idd_path}")
    eplus_minor = args.eplus
    # Compose full version with patch; patch may be zero
    eplus_full = f"{eplus_minor}.{args.patch}"
    out_root = Path(args.out)
    # Parse IDD objects
    objs = parse_idd(idd_path)
    idd_sha = _compute_sha256(idd_path)
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    header = f"EnergyPlus {eplus_minor} | idd sha256: {idd_sha}"
    # Set up Jinja environment
    template_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=False,
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
    )
    # Write eppy-stubs package
    eppy_pkg = out_root / f"eppy-stubs-{eplus_full}"
    eppy_src = eppy_pkg / "src" / "eppy"
    eppy_src.mkdir(parents=True, exist_ok=True)
    # Emit kwargs TypedDicts and overloads
    emit_kwarg_typeddicts(objs, eppy_src / "_kwargs.pyi", header)
    emit_idf_overloads(objs, eppy_src / "idf_overloads.pyi")
    # Generate minimal idf.pyi mixing in overloads
    idf_content = (
        "from __future__ import annotations\n"
        "from .idf_overloads import _IDFOverloads\n\n"
        "class IDF(_IDFOverloads):\n"
        "    ...\n"
    )
    (eppy_src / "idf.pyi").write_text(idf_content, encoding="utf-8")
    # Render eppy __init__.pyi and README.md
    ctx = {
        "eplus_minor": eplus_minor,
        "idd_sha256": idd_sha,
        "timestamp_utc": timestamp,
    }
    init_template = env.get_template("eppy/__init__.pyi.j2")
    (eppy_src / "__init__.pyi").write_text(init_template.render(ctx), encoding="utf-8")
    readme_template = env.get_template("eppy/README.md.j2")
    (eppy_pkg / "README.md").write_text(readme_template.render(ctx), encoding="utf-8")
    # Write pyproject.toml for eppy-stubs
    # Build the pyproject for eppy-stubs.  Escape braces for f-string literal.
    pyproject_eppy = (
        f"""[build-system]\n"
        "requires = [\"hatchling>=1.25\"]\n"
        "build-backend = \"hatchling.build\"\n\n"
        "[project]\n"
        "name = \"eppy-stubs\"\n"
        f"version = \"{eplus_full}\"\n"
        f"description = \"PEP 561 stub-only package for eppy; EnergyPlus {eplus_minor}\"\n"
        "readme = \"README.md\"\n"
        "requires-python = \">=3.10\"\n"
        "classifiers = [\n"
        "  \"Typing :: Stubs Only\",\n"
        "  \"Programming Language :: Python :: 3\",\n"
        "]\n"
        "dependencies = []\n\n"
        "[tool.hatch.build.targets.wheel]\n"
        # braces doubled to escape inside f-string
        "packages = [{{ include = \"src/eppy\" }}]\n"
        "only-include = [\"src/eppy\"]\n\n"
        "[tool.hatch.build]\n"
        "artifacts = [\"generated_by.json\"]\n"""
    )
    (eppy_pkg / "pyproject.toml").write_text(pyproject_eppy, encoding="utf-8")
    # Write generated_by.json for eppy
    provenance = {
        "energyplus_version": eplus_full,
        "idd_sha256": idd_sha,
        "generator_version": "0.1.0",
        "timestamp_utc": timestamp,
        "options": {
            "enum_style": "Literal",
            "docstrings": True,
        },
    }
    (eppy_pkg / "generated_by.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    # Write archetypal-stubs package
    arch_pkg = out_root / f"archetypal-stubs-{eplus_full}"
    arch_src = arch_pkg / "src" / "archetypal"
    gm_src = arch_pkg / "src" / "geomeppy"
    arch_src.mkdir(parents=True, exist_ok=True)
    gm_src.mkdir(parents=True, exist_ok=True)
    # archetypal idf stub mixing in overloads
    arch_idf_content = (
        "from __future__ import annotations\n"
        "from geomeppy import IDF as _GmIDF\n"
        "from eppy.idf_overloads import _IDFOverloads\n\n"
        "class IDF(_GmIDF, _IDFOverloads):\n"
        "    ...\n"
    )
    (arch_src / "idf.pyi").write_text(arch_idf_content, encoding="utf-8")
    # geomeppy shim
    gm_content = "class IDF:\n    ...\n"
    (gm_src / "__init__.pyi").write_text(gm_content, encoding="utf-8")
    # archetypal __init__ and README
    init_arch_template = env.get_template("archetypal/__init__.pyi.j2")
    (arch_src / "__init__.pyi").write_text(init_arch_template.render(ctx), encoding="utf-8")
    readme_arch_template = env.get_template("archetypal/README.md.j2")
    (arch_pkg / "README.md").write_text(readme_arch_template.render(ctx), encoding="utf-8")
    # pyproject.toml for archetypal-stubs
    pyproject_arch = (
        f"""[build-system]\n"
        "requires = [\"hatchling>=1.25\"]\n"
        "build-backend = \"hatchling.build\"\n\n"
        "[project]\n"
        "name = \"archetypal-stubs\"\n"
        f"version = \"{eplus_full}\"\n"
        f"description = \"PEP 561 stub-only package for archetypal; EnergyPlus {eplus_minor}\"\n"
        "readme = \"README.md\"\n"
        "requires-python = \">=3.10\"\n"
        "classifiers = [\n"
        "  \"Typing :: Stubs Only\",\n"
        "  \"Programming Language :: Python :: 3\",\n"
        "]\n"
        f"dependencies = [\"eppy-stubs=={eplus_minor}.*\"]\n\n"
        "[tool.hatch.build.targets.wheel]\n"
        # braces doubled for f-string literal
        "packages = [\n"
        "  {{ include = \"src/archetypal\" }},\n"
        "  {{ include = \"src/geomeppy\" }},\n"
        "]\n"
        "only-include = [\"src/archetypal\", \"src/geomeppy\"]\n\n"
        "[tool.hatch.build]\n"
        "artifacts = [\"generated_by.json\"]\n"""
    )
    (arch_pkg / "pyproject.toml").write_text(pyproject_arch, encoding="utf-8")
    # generated_by.json for archetypal
    (arch_pkg / "generated_by.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    # Done
    raise SystemExit(0)


if __name__ == "__main__":
    main()