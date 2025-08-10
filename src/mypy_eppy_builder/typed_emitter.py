"""TypedDict and overload emitter for EnergyPlus stubs.

This module provides functions that take a sequence of parsed
EnergyPlus objects (:class:`~mypy_eppy_builder.idd_parser.IDDObject`) and
emit two `.pyi` modules:

* ``_kwargs.pyi``
    Defines a :class:`TypedDict` for each object, describing the keyword
    arguments accepted by ``IDF.newidfobject``.  Each key in the
    ``TypedDict`` corresponds to a field in the IDD, normalized to
    snake_case.  Required fields are annotated with
    :class:`~typing.Required`, optional fields with
    :class:`~typing.NotRequired`.  When a field may be blank or has a
    default value, its type is wrapped in ``Optional``.

* ``idf_overloads.pyi``
    Defines a private mixin ``_IDFOverloads`` with an
    :func:`overload <typing.overload>` for each EnergyPlus object key.  The
    overloads accept a ``key`` parameter typed as a ``Literal`` of the
    object key and ``**kwargs`` typed as an ``Unpack`` of the
    corresponding ``TypedDict``.  A catch-all overload covers all other
    keys.  Consumers mix this class into their ``IDF`` stubs to expose
    strongly typed versions of ``newidfobject``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .idd_parser import IDDObject, IDDField

__all__ = [
    "emit_kwarg_typeddicts",
    "emit_idf_overloads",
]


def emit_kwarg_typeddicts(objs: Iterable[IDDObject], out_file: Path, header: str) -> None:
    """Write a ``_kwargs.pyi`` module containing ``TypedDict`` definitions.

    Args:
        objs: Iterable of parsed EnergyPlus objects.  Each object's key and
            fields are used to construct a corresponding ``TypedDict``.
        out_file: Path to the output file (typically ``src/eppy/_kwargs.pyi``).
        header: A short description written as a comment at the top of the
            file; use this to record provenance (EnergyPlus version, IDD hash).
    """
    out_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("from typing import TypedDict, Required, NotRequired, Literal")
    lines.append("")
    if header:
        lines.append(f"# {header}")
        lines.append("")
    for obj in sorted(objs, key=lambda o: o.key):
        td_name = _kwargs_typeddict_name(obj.key)
        lines.append(f"class {td_name}(TypedDict, total=False):")
        if not obj.fields:
            lines.append("    pass")
            lines.append("")
            continue
        for field in obj.fields:
            key = _snake_case(field.name_raw)
            typ = _py_type(field)
            req = "Required" if field.required else "NotRequired"
            # If the field allows blank or has default and isn't required, allow None
            if (field.allows_blank or field.has_default) and not field.required:
                if "None" not in typ:
                    typ = f"{typ} | None"
            # Write a one-line comment with the original field name
            lines.append(f"    # {field.name_raw}")
            lines.append(f"    {key}: {req}[{typ}]")
        lines.append("")
    out_file.write_text("\n".join(lines), encoding="utf-8")


def emit_idf_overloads(objs: Iterable[IDDObject], out_file: Path) -> None:
    """Write an ``idf_overloads.pyi`` module defining typed overloads.

    Each EnergyPlus object key results in a separate overload for
    ``newidfobject``.  The overloads live on a private mixin class named
    ``_IDFOverloads``.  A final catch-all implementation accepts any
    ``str`` key and untyped ``kwargs``.  Consumers import and mix in this
    class to extend their ``IDF`` stubs.

    Args:
        objs: Iterable of parsed EnergyPlus objects.
        out_file: Path to the output file (e.g., ``src/eppy/idf_overloads.pyi``).
    """
    out_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("from typing import overload, Unpack, Literal")
    lines.append("from .bunch import EPBunch")
    lines.append("from ._kwargs import *")
    lines.append("")
    lines.append("class _IDFOverloads:")
    for obj in sorted(objs, key=lambda o: o.key):
        td = _kwargs_typeddict_name(obj.key)
        key_literal = obj.key
        lines.append("    @overload")
        lines.append(
            f"    def newidfobject(self, key: Literal['{key_literal}'], **kwargs: Unpack[{td}]) -> EPBunch: ..."
        )
    # Catch-all overload at the end
    lines.append(
        "    def newidfobject(self, key: str, **kwargs) -> EPBunch: ..."
    )
    lines.append("")
    out_file.write_text("\n".join(lines), encoding="utf-8")


# Helper functions

def _kwargs_typeddict_name(key: str) -> str:
    """Return a valid ``TypedDict`` name for a given EnergyPlus object key.

    Non-alphanumeric characters are replaced with underscores, repeated
    underscores are collapsed, and a ``_Kwargs`` suffix is added.
    """
    key_norm = "".join(ch if ch.isalnum() else "_" for ch in key)
    key_norm = "_".join(filter(None, key_norm.split("_")))
    return f"{key_norm}_Kwargs"


def _snake_case(label: str) -> str:
    """Convert a human-readable field label to snake_case.

    Converts letters to lowercase, replaces non-alphanumeric characters with
    underscores, collapses multiple underscores, and prefixes a leading
    underscore if the first character is numeric.
    """
    s = "".join(ch.lower() if ch.isalnum() else "_" for ch in label)
    s = "_".join(filter(None, s.split("_")))
    if s and s[0].isdigit():
        s = f"_{s}"
    return s


def _py_type(field: IDDField) -> str:
    """Map an IDD field to a Python type annotation as a string.

    The mapping follows these rules:

    * ``alpha``, ``node`` and ``object-list`` map to ``str``.
    * ``integer`` maps to ``int``.
    * ``real`` maps to ``float``.
    * ``boolean`` maps to ``bool``.
    * ``choice`` maps to a ``Literal`` containing the exact keys.
    * Unknown kinds fall back to ``str | float | int``.
    """
    if field.kind in {"alpha", "node", "object-list"}:
        return "str"
    if field.kind == "integer":
        return "int"
    if field.kind == "real":
        return "float"
    if field.kind == "boolean":
        return "bool"
    if field.kind == "choice" and field.choices:
        # Quote string literals; numeric values remain bare
        elems: list[str] = []
        for c in field.choices:
            if isinstance(c, str):
                elems.append(repr(c))
            else:
                elems.append(str(c))
        inner = ", ".join(elems)
        return f"Literal[{inner}]"
    # Unknown or unspecified type: accept common scalars
    return "str | float | int"