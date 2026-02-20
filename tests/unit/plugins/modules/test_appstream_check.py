"""Unit tests for appstream_check module using ansible-test layout."""

import pytest

from ansible_collections.klaas_.appstream.plugins.modules import appstream_check as module_under_test


class ModuleExitJson(Exception):
    """Raised when fake Ansible module exits successfully."""

    def __init__(self, payload):
        super().__init__("module exited")
        self.payload = payload


class ModuleFailJson(Exception):
    """Raised when fake Ansible module fails."""

    def __init__(self, payload):
        super().__init__("module failed")
        self.payload = payload


def _make_fake_ansible_module(params, run_command_output):
    """Create fake AnsibleModule class with controlled command output."""

    class FakeAnsibleModule:
        """Minimal fake AnsibleModule for unit tests."""

        def __init__(self, argument_spec=None, supports_check_mode=False):
            self.argument_spec = argument_spec
            self.supports_check_mode = supports_check_mode
            self.params = params

        def run_command(self, _command, **_kwargs):
            return run_command_output

        def fail_json(self, **kwargs):
            raise ModuleFailJson(kwargs)

        def exit_json(self, **kwargs):
            raise ModuleExitJson(kwargs)

    return FakeAnsibleModule


SAMPLE_GROUPED_DATA = {
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

SAMPLE_RPM_OUTPUT = (
    "retired-nonmod (none)\n"
    "active-nonmod (none)\n"
    "nodejs (none)\n"
    "nodejs-libs nodejs:18:abc\n"
    "postgresql-libs postgresql:16:def\n"
)


def test_main_exit_json_contains_expected_matches(monkeypatch):
    """Ensure successful execution returns expected matches/removal list."""
    params = {
        "grouped_data": SAMPLE_GROUPED_DATA,
        "fail_on_match": False,
        "target_major": "el9",
        "date": "2026-02-16",
    }

    monkeypatch.setattr(
        module_under_test, "AnsibleModule",
        _make_fake_ansible_module(params, (0, SAMPLE_RPM_OUTPUT, "")),
    )

    with pytest.raises(ModuleExitJson) as exc:
        module_under_test.main()

    payload = exc.value.payload
    assert payload["changed"] is False
    assert payload["date"] == "2026-02-16"
    assert payload["packages_to_remove"] == ["nodejs-libs", "retired-nonmod"]

    result = payload["appstream_check_result"]
    assert result["target_major"] == "el9"
    assert result["matched_packages"] == ["retired-nonmod"]
    assert result["matched_dnf_modules"] == ["nodejs:18"]
    assert result["matched_dnf_modules_packages"] == ["nodejs-libs"]
    assert result["any_match"] is True


def test_main_fail_on_match_returns_fail_json(monkeypatch):
    """Ensure fail_on_match causes fail_json when match exists."""
    grouped_data = {
        "el9": {
            "package": [{"name": "retired-nonmod", "end_date": "2020-01-01"}],
            "dnf_module": [],
        }
    }

    params = {
        "grouped_data": grouped_data,
        "fail_on_match": True,
        "target_major": "el9",
        "date": "2026-02-16",
    }

    rpm_output = "retired-nonmod (none)\n"
    monkeypatch.setattr(
        module_under_test, "AnsibleModule",
        _make_fake_ansible_module(params, (0, rpm_output, "")),
    )

    with pytest.raises(ModuleFailJson) as exc:
        module_under_test.main()

    payload = exc.value.payload
    assert payload["changed"] is False
    assert payload["packages_to_remove"] == ["retired-nonmod"]
    assert payload["appstream_check_result"]["any_match"] is True


def test_main_no_matches_exit_json(monkeypatch):
    """No matches produces exit_json with any_match=False and empty lists."""
    grouped_data = {
        "el9": {
            "package": [{"name": "future-pkg", "end_date": "2999-01-01"}],
            "dnf_module": [],
        }
    }

    params = {
        "grouped_data": grouped_data,
        "fail_on_match": False,
        "target_major": "el9",
        "date": "2026-02-16",
    }

    rpm_output = "unrelated-pkg (none)\n"
    monkeypatch.setattr(
        module_under_test, "AnsibleModule",
        _make_fake_ansible_module(params, (0, rpm_output, "")),
    )

    with pytest.raises(ModuleExitJson) as exc:
        module_under_test.main()

    payload = exc.value.payload
    assert payload["changed"] is False
    assert payload["packages_to_remove"] == []
    assert payload["appstream_check_result"]["any_match"] is False


def test_main_fail_on_match_false_with_no_match(monkeypatch):
    """fail_on_match=True but no matches should still exit_json."""
    grouped_data = {
        "el9": {
            "package": [],
            "dnf_module": [],
        }
    }

    params = {
        "grouped_data": grouped_data,
        "fail_on_match": True,
        "target_major": "el9",
        "date": "2026-02-16",
    }

    rpm_output = "some-pkg (none)\n"
    monkeypatch.setattr(
        module_under_test, "AnsibleModule",
        _make_fake_ansible_module(params, (0, rpm_output, "")),
    )

    with pytest.raises(ModuleExitJson) as exc:
        module_under_test.main()

    assert exc.value.payload["appstream_check_result"]["any_match"] is False


def test_main_missing_target_major_in_grouped_data(monkeypatch):
    """fail_json when target_major key is not in grouped_data."""
    params = {
        "grouped_data": {"el9": {"package": [], "dnf_module": []}},
        "fail_on_match": False,
        "target_major": "el7",
        "date": "2026-02-16",
    }

    rpm_output = "some-pkg (none)\n"
    monkeypatch.setattr(
        module_under_test, "AnsibleModule",
        _make_fake_ansible_module(params, (0, rpm_output, "")),
    )

    with pytest.raises(ModuleFailJson) as exc:
        module_under_test.main()

    assert "el7" in exc.value.payload["msg"]
    assert "not found" in exc.value.payload["msg"]
