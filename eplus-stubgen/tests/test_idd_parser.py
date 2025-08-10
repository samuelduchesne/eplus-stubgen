"""Tests for the IDD parser module."""

from pathlib import Path

from mypy_eppy_builder.idd_parser import parse_idd


def test_parse_minimal_idd(tmp_path: Path) -> None:
    """Parse the synthetic IDD and verify objects and fields."""
    # Use the fixture IDD shipped with the repository
    idd_path = Path(__file__).resolve().parent.parent / "fixtures" / "idd" / "min.idd"
    objects = parse_idd(idd_path)
    # We expect exactly two objects
    assert len(objects) == 2
    keys = [obj.key for obj in objects]
    assert "ZONE" in keys
    assert "BUILDINGSURFACE:DETAILED" in keys
    # Inspect the ZONE object fields
    zone = next(obj for obj in objects if obj.key == "ZONE")
    field_names = [field.name_raw for field in zone.fields]
    assert field_names == [
        "Name",
        "Direction of Relative North",
        "X-Coordinate of Origin",
        "Part of Total Floor Area",
    ]
    # The choice values should be captured
    part_field = zone.fields[-1]
    assert set(part_field.choices) == {"Yes", "No"}