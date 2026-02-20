# appstream_cleanup role

Removes retired packages identified by the `appstream_check` role/module.

## What this role does

1. Checks whether `appstream_check_packages_to_remove` is already available.
2. If missing, runs role `appstream_check` to generate it.
3. Removes all packages in `appstream_check_packages_to_remove` using `ansible.builtin.package` with `state: absent`.
4. Skips removal when the list is empty.

## Requirements

- Package manager supported by `ansible.builtin.package` on the target host.
- Privilege escalation (`become`) available for package removal.
- Role `appstream_check` available in the same collection/workspace.

## Inputs

- `appstream_check_packages_to_remove` (optional, list)
  - If provided, this role removes exactly these packages.
  - If not provided, role `appstream_check` is included to compute it.

## Behavior details

- Task file: `roles/appstream_cleanup/tasks/main.yml`
- Conditional include:
  - `appstream_check` runs only when `appstream_check_packages_to_remove` is not defined.
- Conditional removal:
  - Package removal runs only when the variable is defined and has at least one entry.

## Example usage

Run cleanup directly (auto-runs `appstream_check` when needed):

```yaml
- hosts: all
  roles:
    - role: appstream_cleanup
```

Run cleanup with a precomputed package list:

```yaml
- hosts: all
  vars:
    appstream_check_packages_to_remove:
      - nodejs
      - perl
  roles:
    - role: appstream_cleanup
```

## Notes

- This role performs removal only; matching logic is handled by `appstream_check`.
- Review package lists in change-controlled environments before removal.
