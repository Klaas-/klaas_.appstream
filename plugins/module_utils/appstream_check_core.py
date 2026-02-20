"""Core AppStream lifecycle check logic shared by Ansible module and standalone CLI."""

from datetime import date as _date
from typing import Any, Callable, Dict, List, Tuple, Union
from pathlib import Path


def parse_date(value: Union[str, _date]) -> _date:
    """Parse a date string in YYYY-MM-DD format or return an existing date object.

    Raises ValueError for invalid or unparseable date values.
    """
    if isinstance(value, _date):
        return value
    text = str(value).strip()
    try:
        return _date.fromisoformat(text)
    except ValueError:
        pass
    # Fallback for Python < 3.11 which requires zero-padded YYYY-MM-DD
    try:
        parts = text.split("-")
        if len(parts) == 3:
            return _date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError, TypeError):
        pass
    raise ValueError(f"Invalid date format {value!r}, expected YYYY-MM-DD")


def detect_target_major(os_release_path: str = "/etc/os-release") -> str:
    """Detect and return the target major key (for example `el9`) from os-release."""

    version_id = None
    path = Path(os_release_path)

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as file_handle:
                for line in file_handle:
                    line = line.strip()
                    if line.startswith("VERSION_ID="):
                        version_id = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except OSError:
            pass

    if not version_id:
        raise ValueError("Unable to detect VERSION_ID from /etc/os-release; pass target_major explicitly.")

    major = version_id.split(".", 1)[0]
    if not major.isdigit():
        raise ValueError(
            f"Unable to parse major version from VERSION_ID={version_id!r}; pass target_major explicitly."
        )

    return f"el{int(major)}"


def parse_rpm_modularity_output(output: str) -> Tuple[Dict[str, List[str]], List[str]]:
    """Parse `rpm -qa` modularity output into module map and non-modular package list."""

    modules_raw: dict[str, list[str]] = {}
    installed_packages: list[str] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(" ", 1)
        if len(parts) != 2:
            raise ValueError(f"Unexpected rpm output line (expected 2 columns): '{line}'")

        package_name, label = parts[0].strip(), parts[1].strip()

        if label == "(none)":
            installed_packages.append(package_name)
            continue

        label_parts = label.split(":")
        if len(label_parts) < 2 or not label_parts[0] or not label_parts[1]:
            raise ValueError(f"Invalid MODULARITYLABEL format for package '{package_name}': '{label}'")

        key = f"{label_parts[0]}:{label_parts[1]}"
        modules_raw.setdefault(key, []).append(package_name)

    return modules_raw, sorted(set(installed_packages))


def collect_installed_from_rpm(
    run_command: Callable[[List[str]], Tuple[int, str, str]],
) -> Tuple[Dict[str, List[str]], List[str]]:
    """Collect installed package/module data by invoking `rpm -qa` via provided runner."""

    _return_code, output, _error = run_command(["rpm", "-qa", "--qf", "%{NAME} %{MODULARITYLABEL}\\n"])
    return parse_rpm_modularity_output(output)


def _is_retired(end_date_raw: Any, cutoff: _date) -> bool:
    """Return True if *end_date_raw* represents a date strictly before *cutoff*."""
    if end_date_raw in (None, ""):
        return False
    try:
        return parse_date(end_date_raw) < cutoff
    except ValueError:
        return False


def evaluate_appstream_check(
    grouped_data: Dict[str, Any],
    target_major: str,
    selected_date: Union[str, _date],
    installed_dnf_modules_raw: Dict[str, List[str]],
    installed_packages: List[str],
) -> Tuple[Dict[str, Any], List[str]]:
    """Evaluate installed data against lifecycle references and build result payloads."""

    cutoff = parse_date(selected_date)

    major_data = grouped_data.get(target_major)
    if major_data is None:
        raise KeyError(target_major)

    packages_data = major_data.get("package", []) or []
    modules_data = major_data.get("dnf_module", []) or []

    reference_package_names = sorted(
        set(
            str(item.get("name"))
            for item in packages_data
            if _is_retired(item.get("end_date"), cutoff) and item.get("name")
        )
    )

    reference_module_names = sorted(
        set(
            f"{item.get('name')}:{item.get('stream')}"
            for item in modules_data
            if _is_retired(item.get("end_date"), cutoff)
            and item.get("name") not in (None, "")
            and item.get("stream") not in (None, "")
        )
    )

    retired_installed_packages = sorted(set(installed_packages).intersection(reference_package_names))
    installed_dnf_modules = sorted(set(installed_dnf_modules_raw.keys()).intersection(reference_module_names))

    matched_dnf_modules_packages = sorted(
        set(
            package_name
            for module_name in installed_dnf_modules
            for package_name in installed_dnf_modules_raw.get(module_name, [])
        )
    )

    any_match = bool(retired_installed_packages or installed_dnf_modules)
    packages_to_remove = sorted(set(retired_installed_packages + matched_dnf_modules_packages))

    appstream_check_result = {
        "target_major": target_major,
        "matched_packages": retired_installed_packages,
        "matched_dnf_modules": installed_dnf_modules,
        "matched_dnf_modules_packages": matched_dnf_modules_packages,
        "any_match": any_match,
    }

    return appstream_check_result, packages_to_remove
