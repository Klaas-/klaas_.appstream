# Scripts

Utility scripts for generating AppStream lifecycle data and checking installed packages/modules outside Ansible.

These scripts are only tested with python 3.12.

## Requirements

Install dependencies from repo root:

```bash
pip install -r scripts/requirements.txt
```

## `redhat_get_appstreams.py`

Fetches AppStream lifecycle data from Red Hat APIs and writes transformed output that is used in this collection.

### Required environment variable

- `OFFLINE_ACCESS_TOKEN`: Red Hat SSO offline token. This token can be generated at Red Hat if you have a proper subscription: https://access.redhat.com/management/api

### Common usage

```bash
OFFLINE_ACCESS_TOKEN="<token>" python scripts/redhat_get_appstreams.py
```

With debug logging and proxy/env support:

```bash
OFFLINE_ACCESS_TOKEN="<token>" python scripts/redhat_get_appstreams.py --trust-env --log-level DEBUG
```

Write JSON output to a custom file:

```bash
OFFLINE_ACCESS_TOKEN="<token>" python scripts/redhat_get_appstreams.py \
  --output-format json \
  --output-file /tmp/appstreams.json
```

Print raw API response JSON (no transformed file write):

```bash
OFFLINE_ACCESS_TOKEN="<token>" python scripts/redhat_get_appstreams.py --print-appstreams-json
```

### Key options

- `--log-level {DEBUG,INFO,WARNING,ERROR}`
- `--trust-env`
- `--output-file <path>`
- `--output-format {yaml,json}`
- `--output-var <name>` (for YAML wrapping key)
- `--print-appstreams-json`

## `appstream_check_standalone.py`

Checks installed RPM packages and modular streams against lifecycle data.

### Common usage

Default text output:

```bash
python scripts/appstream_check_standalone.py
```

YAML output:

```bash
python scripts/appstream_check_standalone.py --output-format yaml
```

JSON output:

```bash
python scripts/appstream_check_standalone.py --output-format json
```

Fail with exit code `2` when matches are found:

```bash
python scripts/appstream_check_standalone.py --fail-on-match
```

Override data file and target major:

```bash
python scripts/appstream_check_standalone.py \
  --grouped-data-file roles/appstream_check/vars/redhat_appstreams.yml \
  --target-major el9 \
  --date 2026-02-17
```

### Key options

- `--grouped-data-file <path>`
- `--target-major <elX>`
- `--date YYYY-MM-DD`
- `--output-format {text,json,yaml}`
- `--fail-on-match`
