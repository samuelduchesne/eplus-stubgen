"""Sample script that should fail type checking with generated stubs.

This file is not executed during the test suite; it is used by CI to
exercise the stubs with mypy.  See the GitHub workflow for details.
"""

from eppy.idf import IDF


def misuse_idf(i: IDF) -> None:
    # Incorrect usage: invalid keyword argument and wrong type for name
    i.newidfobject("ZONE", namez="Z1")  # type: ignore[attr-defined]
    i.newidfobject("ZONE", name=1)  # type: ignore[arg-type]