#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Standalone CLI to report outdated AppStream packages and module streams."""

import argparse
import json
import subprocess
import sys
from datetime import date as datetime_date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
COLLECTION_ROOT = SCRIPT_DIR.parent
MODULE_UTILS_PATH = COLLECTION_ROOT / "plugins" / "module_utils"

if str(MODULE_UTILS_PATH) not in sys.path:
    sys.path.insert(0, str(MODULE_UTILS_PATH))

import yaml  # noqa: E402
from appstream_check_core import collect_installed_from_rpm, detect_target_major, evaluate_appstream_check, parse_date  # noqa: E402


def _load_grouped_data(path: Path):
    with path.open("r", encoding="utf-8") as file_handle:
        content = yaml.safe_load(file_handle) or {}

    if "appstream_check_grouped" in content and isinstance(content["appstream_check_grouped"], dict):
        return content["appstream_check_grouped"]

    if isinstance(content, dict):
        return content

    raise ValueError(f"Invalid grouped data structure in {path}")


def _run_command(command):
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Check installed RPM packages/modules against AppStream lifecycle data."
    )
    parser.add_argument(
        "--grouped-data-file",
        default="roles/appstream_check/vars/redhat_appstreams.yml",
        help="Path to grouped appstream YAML data file.",
    )
    parser.add_argument(
        "--target-major",
        default=None,
        help="Target major key, e.g. el8/el9. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Comparison date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json", "yaml"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--fail-on-match",
        action="store_true",
        help="Exit with code 2 when outdated packages/modules are detected.",
    )

    return parser.parse_args()


def _resolve_grouped_data_path(grouped_data_file: str) -> Path:
    path = Path(grouped_data_file)
    if not path.is_absolute():
        path = (COLLECTION_ROOT / path).resolve()
    return path


def _collect_payload(args):
    grouped_data_file = _resolve_grouped_data_path(args.grouped_data_file)
    grouped_data = _load_grouped_data(grouped_data_file)

    target_major = args.target_major or detect_target_major()
    selected_date = args.date or datetime_date.today().isoformat()
    parse_date(selected_date)  # validate early
    installed_dnf_modules_raw, installed_packages = collect_installed_from_rpm(_run_command)

    # pylint: disable=duplicate-code
    appstream_check_result, packages_to_remove = evaluate_appstream_check(
        grouped_data=grouped_data,
        target_major=target_major,
        selected_date=selected_date,
        installed_dnf_modules_raw=installed_dnf_modules_raw,
        installed_packages=installed_packages,
    )

    payload = {
        "date": selected_date,
        "appstream_check_result": appstream_check_result,
        "packages_to_remove": packages_to_remove,
    }
    return payload


def _print_text_output(payload):
    appstream_check_result = payload["appstream_check_result"]
    packages_to_remove = payload["packages_to_remove"]

    print(f"Target major: {appstream_check_result['target_major']}")
    print(f"Date: {payload['date']}")

    matched_packages = appstream_check_result["matched_packages"]
    matched_modules = appstream_check_result["matched_dnf_modules"]

    if matched_packages:
        print("\nOutdated packages:")
        for package_name in matched_packages:
            print(f"- {package_name}")
    else:
        print("\nNo outdated packages")

    if matched_modules:
        print("\nOutdated modules:")
        for module_name in matched_modules:
            print(f"- {module_name}")
    else:
        print("\nNo outdated modules")

    if packages_to_remove:
        print("\nPackages to remove:")
        for package_name in packages_to_remove:
            print(f"- {package_name}")
    else:
        print("\nNo packages to remove")


def _print_payload(payload, output_format: str):
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    if output_format == "yaml":
        print(yaml.safe_dump(payload, sort_keys=False), end="")
        return

    _print_text_output(payload)


def main():
    """Run CLI argument handling, lifecycle evaluation, and formatted output."""

    args = _parse_args()

    try:
        payload = _collect_payload(args)
    except KeyError as exc:
        missing_target = exc.args[0] if exc.args else args.target_major
        print(f"target_major '{missing_target}' not found in grouped_data.", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Failed to query installed RPM data: {exc}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print_payload(payload, args.output_format)

    if args.fail_on_match and payload["appstream_check_result"]["any_match"]:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
