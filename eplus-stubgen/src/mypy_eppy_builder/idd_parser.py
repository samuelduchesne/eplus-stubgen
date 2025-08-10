"""EnergyPlus IDD parser.

This module defines a simple parser that reads an EnergyPlus Input Data
Dictionary (IDD) and produces a structured representation of objects and
their fields.  The parser makes minimal assumptions about the structure
of the IDD and ignores most directives other than those relevant for
typing: field names, types, requiredness, keys, and defaults.  Comments
and notes are stripped during parsing.

The resulting model is used by other components to generate TypedDicts and
overloads for static type checkers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Literal

FieldKind = Literal[
    "alpha",
    "integer",
    "real",
    "boolean",
    "choice",
    "node",
    "object-list",
    "unknown",
]


@dataclass(slots=True, frozen=True)
class IDDField:
    """Represents a field within an IDD object.

    Attributes:
        index: Numerical index of the field (1-based) extracted from the A#/N#
            label.  If the index is missing or not parsable, zero is used.
        name_raw: The raw field name as it appears in the IDD after the
            `\field` directive.
        kind: Normalized type of the field.  One of the values from
            :data:`FieldKind`.
        choices: Permitted values when the field is a choice.  Strings are
            stored verbatim; numeric values are converted to integers when
            appropriate.
        required: Whether the field is marked as required via
            ``\required-field`` or ``\required-object``.
        allows_blank: Whether the field may be left blank according to a
            ``\blank`` directive.  Blank fields are treated as optional in
            the generated TypedDicts.
        has_default: Whether the field has a default value specified via
            a ``\default`` directive.  Defaults imply optionality in the
            emitted types.
    """

    index: int
    name_raw: str
    kind: FieldKind
    choices: tuple[str | int, ...]
    required: bool
    allows_blank: bool
    has_default: bool


@dataclass(slots=True, frozen=True)
class IDDObject:
    """Represents an EnergyPlus object definition.

    Attributes:
        key: The canonical object name, such as ``"ZONE"`` or
            ``"BUILDINGSURFACE:DETAILED"``.  Keys are emitted as string
            literals in overloads.
        fields: A tuple of :class:`IDDField` describing the object's
            parameters in declaration order.
    """

    key: str
    fields: tuple[IDDField, ...]


def parse_idd(path: Path) -> list[IDDObject]:
    """Parse an EnergyPlus IDD file into a list of objects.

    The parser removes comments and notes, then detects object boundaries
    marked by ``\begin-object`` and ``\end-object``.  Within each object it
    scans ``A#`` and ``N#`` definitions followed by backslash directives to
    collect metadata.  Unknown directives are ignored.

    Args:
        path: Path to the ``Energy+.idd`` file to parse.

    Returns:
        A list of :class:`IDDObject` entries preserving the order of
        appearance in the IDD.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = _strip_comments(text.splitlines())
    objects: list[IDDObject] = []
    it = iter(enumerate(lines, start=1))
    for _, line in it:
        # Objects start with \begin-object <key>
        if line.startswith("\\begin-object"):
            key = _extract_after(line, "\\begin-object")
            fields: list[IDDField] = []
            # Capture fields until \end-object
            for _, l2 in it:
                if l2.startswith("\\end-object"):
                    break
                if l2.startswith("A") or l2.startswith("N"):
                    f = _parse_field_block(l2, it)
                    fields.append(f)
            objects.append(IDDObject(key=key, fields=tuple(fields)))
    return objects


def _strip_comments(lines: Iterable[str]) -> list[str]:
    """Remove inline comments and blank lines.

    EnergyPlus uses ``!`` to denote comments that run to the end of the line.
    This helper removes everything after the first ``!`` and strips
    whitespace.  Empty lines and lines that become empty after stripping are
    omitted from the result.
    """
    out: list[str] = []
    for raw in lines:
        # split on ! and keep the code before comment
        s = raw.split("!", 1)[0].strip()
        if not s:
            continue
        out.append(s)
    return out


def _extract_after(line: str, prefix: str) -> str:
    """Return the substring following a prefix, trimmed of trailing punctuation."""
    s = line[len(prefix) :].strip()
    return s.strip(",; ")


def _parse_field_block(first_line: str, it: Iterator[tuple[int, str]]) -> IDDField:
    """Parse a field definition starting at its ``A#`` or ``N#`` header.

    The caller passes an iterator that yields subsequent lines.  This
    function consumes lines until it encounters the next ``A``/``N``
    header, a ``\begin-object`` directive, or a ``\end-object`` directive.  It
    builds an :class:`IDDField` with the collected metadata.

    Args:
        first_line: The header line starting with ``A`` or ``N``.
        it: An iterator over remaining line tuples (index, text).

    Returns:
        A fully populated :class:`IDDField`.
    """
    # Header example: 'A1 , \field Name'
    idx_part = first_line.split()[0]
    index = int(idx_part[1:]) if len(idx_part) > 1 and idx_part[1:].isdigit() else 0
    name_raw = "Field"
    kind: FieldKind = "unknown"
    required = False
    allows_blank = False
    has_default = False
    choices: list[str | int] = []

    # Continue reading directives until next field or object end
    for _, line in it:
        if line.startswith("A") or line.startswith("N") or line.startswith("\\begin-object"):
            # push the line back and break
            it = _pushback(it, (0, line))
            break
        if line.startswith("\\end-object"):
            break
        # Field directives
        if line.startswith("\\field"):
            name_raw = _extract_after(line, "\\field")
        elif line.startswith("\\type"):
            t = _extract_after(line, "\\type").lower()
            kind = _normalize_kind(t)
        elif line.startswith("\\required-field") or line.startswith("\\required-object"):
            required = True
        elif line.startswith("\\default"):
            has_default = True
        elif line.startswith("\\minimum") or line.startswith("\\maximum"):
            # ignore numeric bounds for typing
            pass
        elif line.startswith("\\key"):
            val = _extract_after(line, "\\key")
            choices.append(_parse_choice(val))
        elif line.startswith("\\blank"):
            # blank allowable directive
            allows_blank = True
        elif line.startswith("\\note"):
            # ignore notes
            pass
    # If choices are present and the kind is not numeric or boolean, treat as choice
    if choices and kind not in ("integer", "real", "boolean"):
        kind = "choice"
    return IDDField(
        index=index,
        name_raw=name_raw,
        kind=kind,
        choices=tuple(choices),
        required=required,
        allows_blank=allows_blank,
        has_default=has_default,
    )


def _pushback(it: Iterator[tuple[int, str]], item: tuple[int, str]) -> Iterator[tuple[int, str]]:
    """Return a new iterator that yields a single item followed by the original iterator."""
    yield item
    yield from it


def _normalize_kind(t: str) -> FieldKind:
    """Normalize a type string from the IDD to one of the FieldKind values."""
    if t in {"alpha", "string"}:
        return "alpha"
    if t in {"node"}:
        return "node"
    if t in {"object-list"}:
        return "object-list"
    if t in {"real"}:
        return "real"
    if t in {"integer"}:
        return "integer"
    if t in {"choice"}:
        return "choice"
    if t in {"boolean"}:
        return "boolean"
    return "unknown"


def _parse_choice(val: str) -> str | int:
    """Parse a ``\key`` value into an int if possible, otherwise return the string.

    EnergyPlus permits numeric choice keys.  If the string represents an
    integer, return the integer; if it represents a float that is integral
    (e.g. ``"1.0"``) convert to an int as well.  Otherwise return the raw
    string.
    """
    val = val.strip()
    if val.isdigit():
        return int(val)
    try:
        f = float(val)
        if f.is_integer():
            return int(f)
        return val
    except ValueError:
        return val