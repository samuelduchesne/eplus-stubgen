# eplus-stubgen

This repository contains a small toolset for generating **stub-only** wheels for the
`eppy` and `archetypal` Python libraries from an EnergyPlus IDD file.  The goal
is to provide rich static typing for calls to `IDF.newidfobject()` without
incurring any runtime cost.  To achieve this the build system parses the
EnergyPlus IDD and emits two sets of type stubs:

- **`eppy-stubs`**
  - Contains typed versions of the `IDF.newidfobject` method.  Each EnergyPlus
    object becomes its own `TypedDict` describing the valid keyword arguments,
    and `newidfobject` is overloaded for each object key using
    `Literal[...]` and `Unpack[TypedDict]`.  All returns are typed as
    `EPBunch`.
- **`archetypal-stubs`**
  - Depends on the corresponding `eppy-stubs` release and exposes the same
    overloads on its own `archetypal.IDF` class.  It also bundles a minimal
    `geomeppy` shim so that type checkers can resolve the inheritance
    hierarchy at static analysis time.

The generated wheels are compliant with PEP 561 for stub-only packages:

* The package trees contain only `.pyi` files — no `.py` or `py.typed` files.
* Each wheel includes a short `README.md` and a `generated_by.json` that
  records the EnergyPlus version, the IDD hash, the generator version, and
  options used during generation.

See the `examples/` and `tests/samples/` directories for minimal usage
examples and CI tests.

## Building

To generate stubs, first install the project in a virtual environment with the
development dependencies:

```bash
uv venv
uv pip install -e .[dev]
```

Place your EnergyPlus `.idd` file into a convenient location.  Then run the
build command, specifying the EnergyPlus version (major.minor), the patch
number, and the output directory:

```bash
uv run python -m mypy_eppy_builder.build_cli \
  --idd path/to/Energy+.idd \
  --eplus 23.1 \
  --patch 0 \
  --out generated_package
```

This will create two directories in `generated_package` named
`eppy-stubs-23.1.0` and `archetypal-stubs-23.1.0`.  Each directory contains
a `src/` subdirectory with the stub package, a `pyproject.toml`, a
`README.md`, and a `generated_by.json`.  You can build wheels with
`uv build` inside each of these directories.

## Running tests

The repository includes a small synthetic IDD file under `fixtures/idd/min.idd`.
To run the parser and emitter tests as well as some smoke tests for the
TypedDict and overload generation, run:

```bash
uv run pytest -q
```

The CI workflow builds stubs for the synthetic IDD, verifies that the
package structure is stub-only, and performs simple `mypy` smoke tests on
imported stubs to ensure the overloads catch type errors.
