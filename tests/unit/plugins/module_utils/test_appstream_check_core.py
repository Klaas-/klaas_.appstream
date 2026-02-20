"""Unit tests for appstream_check_core module_utils helpers."""

from datetime import date

import pytest

from ansible_collections.klaas_.appstream.plugins.module_utils import appstream_check_core as core


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

def test_parse_date_iso_string():
    """Standard YYYY-MM-DD string is parsed correctly."""
    assert core.parse_date("2026-02-17") == date(2026, 2, 17)


def test_parse_date_date_object():
    """A date object is returned as-is."""
    d = date(2026, 1, 1)
    assert core.parse_date(d) is d


def test_parse_date_non_zero_padded():
    """Non-zero-padded dates like 2026-2-1 are accepted by fromisoformat."""
    assert core.parse_date("2026-2-1") == date(2026, 2, 1)


def test_parse_date_invalid_string():
    """Raises ValueError for garbage input."""
    with pytest.raises(ValueError, match="Invalid date format"):
        core.parse_date("not-a-date")


def test_parse_date_empty_string():
    """Raises ValueError for empty string."""
    with pytest.raises(ValueError, match="Invalid date format"):
        core.parse_date("")


# ---------------------------------------------------------------------------
# detect_target_major
# ---------------------------------------------------------------------------

def test_detect_target_major_from_os_release(tmp_path):
    """Ensure major version is parsed from VERSION_ID."""
    os_release = tmp_path / "os-release"
    os_release.write_text('NAME="RHEL"\nVERSION_ID="9.4"\n', encoding="utf-8")

    assert core.detect_target_major(str(os_release)) == "el9"


def test_detect_target_major_el8(tmp_path):
    """Ensure el8 is returned for VERSION_ID 8.x."""
    os_release = tmp_path / "os-release"
    os_release.write_text('VERSION_ID="8.10"\n', encoding="utf-8")

    assert core.detect_target_major(str(os_release)) == "el8"


def test_detect_target_major_unquoted(tmp_path):
    """Ensure unquoted VERSION_ID is handled."""
    os_release = tmp_path / "os-release"
    os_release.write_text("VERSION_ID=9.2\n", encoding="utf-8")

    assert core.detect_target_major(str(os_release)) == "el9"


def test_detect_target_major_missing_file(tmp_path):
    """Raise ValueError when os-release file does not exist."""
    with pytest.raises(ValueError, match="Unable to detect VERSION_ID"):
        core.detect_target_major(str(tmp_path / "nonexistent"))


def test_detect_target_major_missing_version_id(tmp_path):
    """Raise ValueError when VERSION_ID line is absent."""
    os_release = tmp_path / "os-release"
    os_release.write_text('NAME="RHEL"\nID=rhel\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to detect VERSION_ID"):
        core.detect_target_major(str(os_release))


def test_detect_target_major_non_numeric(tmp_path):
    """Raise ValueError when VERSION_ID major is not a digit."""
    os_release = tmp_path / "os-release"
    os_release.write_text('VERSION_ID="abc"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to parse major version"):
        core.detect_target_major(str(os_release))


# ---------------------------------------------------------------------------
# parse_rpm_modularity_output
# ---------------------------------------------------------------------------

def test_parse_rpm_modularity_output_parses_expected_structures():
    """Ensure parser separates module packages and non-modular packages."""
    rpm_output = """pkg-a (none)\npkg-b nodejs:18:ctx\npkg-c nodejs:18:ctx\n"""

    modules_raw, installed_packages = core.parse_rpm_modularity_output(rpm_output)

    assert installed_packages == ["pkg-a"]
    assert modules_raw == {"nodejs:18": ["pkg-b", "pkg-c"]}


def test_parse_rpm_modularity_output_empty():
    """Empty input returns empty structures."""
    modules_raw, installed_packages = core.parse_rpm_modularity_output("")

    assert not modules_raw
    assert installed_packages == []


def test_parse_rpm_modularity_output_only_blank_lines():
    """Blank lines are skipped gracefully."""
    modules_raw, installed_packages = core.parse_rpm_modularity_output("\n\n  \n")

    assert not modules_raw
    assert installed_packages == []


def test_parse_rpm_modularity_output_deduplicates_packages():
    """Duplicate non-modular package names are deduplicated and sorted."""
    rpm_output = "pkg-z (none)\npkg-a (none)\npkg-z (none)\n"

    _modules_raw, installed_packages = core.parse_rpm_modularity_output(rpm_output)

    assert installed_packages == ["pkg-a", "pkg-z"]


def test_parse_rpm_modularity_output_malformed_single_column():
    """Raise ValueError for lines with only one column."""
    with pytest.raises(ValueError, match="Unexpected rpm output line"):
        core.parse_rpm_modularity_output("badline\n")


def test_parse_rpm_modularity_output_bad_modularitylabel():
    """Raise ValueError for invalid MODULARITYLABEL format."""
    with pytest.raises(ValueError, match="Invalid MODULARITYLABEL format"):
        core.parse_rpm_modularity_output("pkg-a badlabel\n")


# ---------------------------------------------------------------------------
# evaluate_appstream_check
# ---------------------------------------------------------------------------

def test_evaluate_appstream_check_returns_expected_matches():
    """Ensure evaluator returns expected match payload and removal list."""
    grouped_data = {
        "el9": {
            "package": [
                {"name": "retired-nonmod", "end_date": "2020-01-01"},
                {"name": "active-nonmod", "end_date": "2999-01-01"},
            ],
            "dnf_module": [
                {"name": "nodejs", "stream": "18", "end_date": "2020-01-01"},
                {"name": "postgresql", "stream": "16", "end_date": "2999-01-01"},
            ],
        }
    }

    installed_dnf_modules_raw = {
        "nodejs:18": ["nodejs-libs"],
        "postgresql:16": ["postgresql-libs"],
    }
    installed_packages = ["retired-nonmod", "active-nonmod"]

    result, packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date="2026-02-17",
        installed_dnf_modules_raw=installed_dnf_modules_raw,
        installed_packages=installed_packages,
    )

    assert result["target_major"] == "el9"
    assert result["matched_packages"] == ["retired-nonmod"]
    assert result["matched_dnf_modules"] == ["nodejs:18"]
    assert result["matched_dnf_modules_packages"] == ["nodejs-libs"]
    assert result["any_match"] is True
    assert packages_to_remove == ["nodejs-libs", "retired-nonmod"]


def test_evaluate_appstream_check_no_matches():
    """No matches returns empty lists and any_match=False."""
    grouped_data = {
        "el9": {
            "package": [{"name": "future-pkg", "end_date": "2999-01-01"}],
            "dnf_module": [{"name": "nodejs", "stream": "22", "end_date": "2999-01-01"}],
        }
    }

    result, packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date="2026-02-17",
        installed_dnf_modules_raw={"nodejs:22": ["nodejs-libs"]},
        installed_packages=["future-pkg"],
    )

    assert result["matched_packages"] == []
    assert result["matched_dnf_modules"] == []
    assert result["any_match"] is False
    assert packages_to_remove == []


def test_evaluate_appstream_check_missing_target_major():
    """KeyError raised when target_major is not in grouped_data."""
    with pytest.raises(KeyError):
        core.evaluate_appstream_check(
            grouped_data={"el9": {"package": [], "dnf_module": []}},
            target_major="el8",
            selected_date="2026-02-17",
            installed_dnf_modules_raw={},
            installed_packages=[],
        )


def test_evaluate_appstream_check_empty_reference_data():
    """Empty package/dnf_module lists produce no matches."""
    grouped_data = {"el9": {"package": [], "dnf_module": []}}

    result, packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date="2026-02-17",
        installed_dnf_modules_raw={"nodejs:22": ["nodejs-libs"]},
        installed_packages=["some-pkg"],
    )

    assert result["any_match"] is False
    assert packages_to_remove == []


def test_evaluate_appstream_check_missing_keys_in_data():
    """Missing package/dnf_module keys are handled gracefully."""
    grouped_data = {"el9": {}}

    result, packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date="2026-02-17",
        installed_dnf_modules_raw={},
        installed_packages=[],
    )

    assert result["any_match"] is False
    assert packages_to_remove == []


def test_evaluate_appstream_check_null_end_date_ignored():
    """Entries with null or empty end_date are not treated as retired."""
    grouped_data = {
        "el9": {
            "package": [
                {"name": "pkg-null", "end_date": None},
                {"name": "pkg-empty", "end_date": ""},
            ],
            "dnf_module": [],
        }
    }

    result, _packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date="2026-02-17",
        installed_dnf_modules_raw={},
        installed_packages=["pkg-null", "pkg-empty"],
    )

    assert result["matched_packages"] == []
    assert result["any_match"] is False


def test_evaluate_appstream_check_non_iso_padded_dates():
    """Date comparison works with non-zero-padded date strings that would break string comparison."""
    grouped_data = {
        "el9": {
            "package": [
                # end_date "2026-2-1" would sort AFTER "2026-02-17" with string compare
                {"name": "retired-pkg", "end_date": "2026-2-1"},
            ],
            "dnf_module": [],
        }
    }

    result, packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date="2026-02-17",
        installed_dnf_modules_raw={},
        installed_packages=["retired-pkg"],
    )

    # 2026-02-01 < 2026-02-17 => retired
    assert result["matched_packages"] == ["retired-pkg"]
    assert result["any_match"] is True
    assert packages_to_remove == ["retired-pkg"]


def test_evaluate_appstream_check_accepts_date_object():
    """selected_date can be a datetime.date object, not just a string."""
    grouped_data = {
        "el9": {
            "package": [{"name": "old-pkg", "end_date": "2020-01-01"}],
            "dnf_module": [],
        }
    }

    result, _packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date=date(2026, 2, 17),
        installed_dnf_modules_raw={},
        installed_packages=["old-pkg"],
    )

    assert result["matched_packages"] == ["old-pkg"]
    assert result["any_match"] is True


def test_evaluate_appstream_check_invalid_date_raises():
    """ValueError raised when selected_date is not a valid date."""
    with pytest.raises(ValueError, match="Invalid date format"):
        core.evaluate_appstream_check(
            grouped_data={"el9": {"package": [], "dnf_module": []}},
            target_major="el9",
            selected_date="not-a-date",
            installed_dnf_modules_raw={},
            installed_packages=[],
        )


def test_evaluate_appstream_check_malformed_end_date_ignored():
    """Entries with unparseable end_date are silently skipped, not treated as retired."""
    grouped_data = {
        "el9": {
            "package": [{"name": "bad-date-pkg", "end_date": "garbage"}],
            "dnf_module": [],
        }
    }

    result, _packages_to_remove = core.evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major="el9",
        selected_date="2026-02-17",
        installed_dnf_modules_raw={},
        installed_packages=["bad-date-pkg"],
    )

    assert result["matched_packages"] == []
    assert result["any_match"] is False
