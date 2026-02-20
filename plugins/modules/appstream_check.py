#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Ansible module to check installed RPMs/modules against AppStream lifecycle data."""

# Copyright: Klaas Weyermann (c) 2026
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

DOCUMENTATION = r"""
---
module: appstream_check
short_description: Check installed RPMs/modules against retired AppStream entries
version_added: "0.1.0"
description:
  - Compares installed RPM packages and installed modular RPMs against AppStream lifecycle data.
  - Returns matches and an aggregated package removal list.
  - Optionally fails when matches are found.
  - This module is read-only and fully supports check mode.
options:
  grouped_data:
    description:
      - Grouped AppStream data (for example loaded from vars/redhat_appstreams.yml).
      - Expected shape example keys are grouped_data -> el8/el9 -> package/dnf_module.
      - package entries use fields name and end_date.
      - dnf_module entries use fields name, stream and end_date.
    type: dict
    required: true
  fail_on_match:
    description:
      - Fail the module when any retired package/module match is detected.
    type: bool
    default: false
  target_major:
    description:
      - Target key in C(grouped_data), for example C(el8).
      - If omitted, it is auto-detected from C(/etc/os-release) VERSION_ID major.
    type: str
  date:
    description:
      - Date used for lifecycle comparison in C(YYYY-MM-DD).
      - If omitted, current local date is used.
    type: str
author:
  - Klaas Weyermann (@Klaas-)
"""

EXAMPLES = r"""
- name: Load grouped appstream vars
  ansible.builtin.include_vars:
    file: redhat_appstreams.yml

- name: Run appstream check
  klaas_.appstream.appstream_check:
    grouped_data: "{{ appstream_check_grouped }}"
    fail_on_match: "{{ appstream_check_fail_on_match }}"
  register: appstream_check_run
"""

RETURN = r"""
appstream_check_result:
  description: Details of the check results
  type: dict
  returned: always
  contains:
    target_major:
      description: Target OS major key used for lookup in grouped data.
      type: str
      sample: el9
    matched_packages:
      description: Installed non-modular package names that are past end-of-life.
      type: list
      elements: str
      sample:
        - retired-nonmod
    matched_dnf_modules:
      description: Installed modular streams that are past end-of-life.
      type: list
      elements: str
      sample:
        - nodejs:18
    matched_dnf_modules_packages:
      description: Installed package names belonging to matched retired module streams.
      type: list
      elements: str
      sample:
        - nodejs-libs
    any_match:
      description: Whether any retired package or module match was found.
      type: bool
      sample: true
packages_to_remove:
  description: Combined retired package names and packages from matched retired modules.
  type: list
  elements: str
  returned: always
  sample:
    - retired-nonmod
    - nodejs-libs
"""


from typing import Tuple, Dict, List

from datetime import date as datetime_date
from ansible.module_utils.basic import AnsibleModule

from ansible_collections.klaas_.appstream.plugins.module_utils.appstream_check_core import (
    collect_installed_from_rpm,
    detect_target_major,
    evaluate_appstream_check,
    parse_date,
)


def _detect_target_major(module: AnsibleModule) -> str:
    try:
        return detect_target_major()
    except ValueError as exc:
        module.fail_json(msg=str(exc))
        raise


def _run_rpm_modularity(module: AnsibleModule) -> Tuple[Dict[str, List[str]], List[str]]:
    try:
        return collect_installed_from_rpm(lambda command: module.run_command(command, check_rc=True))
    except ValueError as exc:
        module.fail_json(msg=str(exc))
        raise


def main():
    """Execute Ansible module argument parsing and AppStream lifecycle checks."""

    module = AnsibleModule(
        argument_spec={
            "grouped_data": {"type": "dict", "required": True},
            "fail_on_match": {"type": "bool", "default": False},
            "target_major": {"type": "str", "required": False, "default": None},
            "date": {"type": "str", "required": False, "default": None},
        },
        supports_check_mode=True,
    )

    grouped_data = module.params["grouped_data"] or {}
    fail_on_match = module.params["fail_on_match"]
    target_major = module.params["target_major"] or _detect_target_major(module)
    selected_date = module.params["date"] or datetime_date.today().isoformat()

    try:
        parse_date(selected_date)
    except ValueError as exc:
        module.fail_json(msg=str(exc))

    installed_dnf_modules_raw, installed_packages = _run_rpm_modularity(module)
    try:
        # pylint: disable=duplicate-code
        appstream_check_result, packages_to_remove = evaluate_appstream_check(
            grouped_data=grouped_data,
            target_major=target_major,
            selected_date=selected_date,
            installed_dnf_modules_raw=installed_dnf_modules_raw,
            installed_packages=installed_packages,
        )
    except KeyError:
        module.fail_json(msg=f"target_major '{target_major}' not found in grouped_data.")

    any_match = appstream_check_result["any_match"]
    retired_installed_packages = appstream_check_result["matched_packages"]
    installed_dnf_modules = appstream_check_result["matched_dnf_modules"]

    if fail_on_match and any_match:
        module.fail_json(
            msg=(
                "Detected matching AppStream entries on target. "
                f"packages={retired_installed_packages} "
                f"dnf_modules={installed_dnf_modules} "
                f"packages_including_modules={packages_to_remove}"
            ),
            changed=False,
            appstream_check_result=appstream_check_result,
            packages_to_remove=packages_to_remove,
            date=selected_date,
        )

    module.exit_json(
        changed=False,
        appstream_check_result=appstream_check_result,
        packages_to_remove=packages_to_remove,
        date=selected_date,
    )


if __name__ == "__main__":
    main()
