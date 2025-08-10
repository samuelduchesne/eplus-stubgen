"""Smoke tests for the typed emitter."""

from pathlib import Path

from mypy_eppy_builder.idd_parser import parse_idd
from mypy_eppy_builder.typed_emitter import emit_kwarg_typeddicts, emit_idf_overloads


def test_emitter_outputs(tmp_path: Path) -> None:
    """Verify that the emitter writes expected definitions."""
    idd_path = Path(__file__).resolve().parent.parent / "fixtures" / "idd" / "min.idd"
    objects = parse_idd(idd_path)
    # Create temporary output directory
    out_eppy = tmp_path / "eppy"
    out_eppy.mkdir(parents=True, exist_ok=True)
    # Emit files
    emit_kwarg_typeddicts(objects, out_eppy / "_kwargs.pyi", header="test header")
    emit_idf_overloads(objects, out_eppy / "idf_overloads.pyi")
    # Read back _kwargs.pyi
    kwargs_text = (out_eppy / "_kwargs.pyi").read_text(encoding="utf-8")
    assert "class ZONE_Kwargs" in kwargs_text
    assert "name: Required[str]" in kwargs_text
    assert "direction_of_relative_north: NotRequired[float]" in kwargs_text
    assert "part_of_total_floor_area: NotRequired[Literal['Yes', 'No']]" in kwargs_text
    # Read back idf_overloads.pyi
    overloads = (out_eppy / "idf_overloads.pyi").read_text(encoding="utf-8")
    assert "class _IDFOverloads" in overloads
    assert "def newidfobject(self, key: Literal['ZONE'], **kwargs: Unpack[ZONE_Kwargs]) -> EPBunch" in overloads
    assert "def newidfobject(self, key: str, **kwargs) -> EPBunch" in overloads