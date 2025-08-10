"""Sample script that type checks successfully with generated stubs.

This file is not executed during the test suite; it is used by CI to
exercise the stubs with mypy.  See the GitHub workflow for details.
"""

from eppy.idf import IDF


def use_idf(i: IDF) -> None:
    # Correct usage: valid key and correct argument names/types
    i.newidfobject("ZONE", name="Z1", direction_of_relative_north=0.0)