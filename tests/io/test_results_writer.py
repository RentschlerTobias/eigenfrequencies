"""Test result writers."""

from eigenfrequencies.io.results import write_result_line


def test_write_result_line_byte_identical():
    """write_result_line output must be byte-identical to the frozen sample."""
    golden_path = "tests/characterization/golden/result_line.json"
    with open(golden_path, "rb") as fh:
        expected = fh.read()

    result = write_result_line([1.0, 2.0, 3.0])
    assert result == expected
