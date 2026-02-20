#!/usr/bin/env python

"""Fetch and transform Red Hat AppStream lifecycle data into collection vars format."""

import asyncio
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import aiohttp
import yaml


OFFLINE_ACCESS_TOKEN = os.getenv("OFFLINE_ACCESS_TOKEN", "")
SSO_TOKEN_URL = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
SSO_CLIENT_ID = "rhsm-api"
APPSTREAMS_URL = "https://console.redhat.com/api/roadmap/v1/lifecycle/app-streams"
LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_FILE = REPO_ROOT / "roles" / "appstream_check" / "vars" / "redhat_appstreams.yml"
DEFAULT_OUTPUT_VAR = "appstream_check_grouped"


def parse_args() -> argparse.Namespace:
    """Parse command-line options for fetching and writing AppStream data."""

    parser = argparse.ArgumentParser(
        description="Authenticate with Red Hat SSO using an offline token."
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Set log level (default: WARNING).",
    )
    parser.add_argument(
        "--trust-env",
        action="store_true",
        default=False,
        help="Use environment variables for proxy and auth settings in aiohttp.",
    )
    parser.add_argument(
        "--output-file",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Path to write transformed appstreams output.",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "yaml"],
        default="yaml",
        help="Output format for transformed data (default: yaml).",
    )
    parser.add_argument(
        "--output-var",
        default=DEFAULT_OUTPUT_VAR,
        help="Variable name used for YAML output (default: appstream_check_grouped).",
    )
    parser.add_argument(
        "--print-appstreams-json",
        action="store_true",
        default=False,
        help="Pretty-print raw get_appstreams JSON response and exit.",
    )
    return parser.parse_args()


def configure_logging(log_level: str) -> None:
    """Configure process logging using the requested verbosity level."""

    selected_level = getattr(logging, log_level)
    logging.basicConfig(
        level=selected_level,
        stream=sys.stdout,
        format="%(levelname)s: %(message)s",
    )


async def login(offline_access_token: str, trust_env: bool) -> str:
    """Exchange an offline token for an access token via Red Hat SSO."""

    if not offline_access_token:
        raise ValueError("OFFLINE_ACCESS_TOKEN is empty")

    payload = {
        "grant_type": "refresh_token",
        "client_id": SSO_CLIENT_ID,
        "refresh_token": offline_access_token,
    }

    async with aiohttp.ClientSession(trust_env=trust_env) as session:
        async with session.post(SSO_TOKEN_URL, data=payload) as response:
            body = await response.text()
            if response.status != 200:
                raise RuntimeError(f"Login failed (HTTP {response.status}): {body}")

            data = await response.json()
            access_token = data.get("access_token", "")
            if not access_token:
                raise RuntimeError("Login response missing access_token")
            return access_token


async def get_appstreams(access_token: str, trust_env: bool) -> dict[str, Any]:
    """Fetch raw AppStream lifecycle payload from the Red Hat API."""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(trust_env=trust_env) as session:
        async with session.get(APPSTREAMS_URL, headers=headers) as response:
            body = await response.text()
            if response.status != 200:
                raise RuntimeError(
                    f"AppStreams request failed (HTTP {response.status}): {body}"
                )
            return await response.json()


def transform_appstreams(appstreams: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Transform raw AppStream API response into grouped compact structure by EL major."""

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    items = appstreams.get("data", []) if isinstance(appstreams, dict) else []

    for item in items:
        if not isinstance(item, dict):
            continue

        os_major = int(item.get("os_major", 0))
        impl = str(item.get("impl", "unknown"))
        if impl not in {"package", "dnf_module"}:
            continue

        compact_item: dict[str, Any] = {
            "name": item.get("name"),
            "stream": item.get("stream"),
            "end_date": item.get("end_date"),
            "impl": impl,
            "os_major": os_major,
        }

        grouped.setdefault(f"el{os_major}", {}).setdefault(impl, []).append(compact_item)

    return grouped


def write_output_file(path: str, payload: dict[str, Any], output_format: str, output_var: str) -> None:
    """Write transformed data to JSON or YAML file, creating parent directories as needed."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        if output_format == "json":
            json.dump(payload, handle, indent=2)
            return
        if output_format == "yaml":
            yaml.safe_dump({output_var: payload}, handle, sort_keys=False)
            return
        raise ValueError(f"Unsupported output format: {output_format}")


async def run(
    trust_env: bool,
    output_file: str,
    output_format: str,
    output_var: str,
    print_appstreams_json: bool,
) -> None:
    """Execute login, fetch, optional print, transform, and output write workflow."""

    access_token = await login(OFFLINE_ACCESS_TOKEN, trust_env)
    LOGGER.debug("access_token acquired (prefix): %s...", access_token[:12])
    appstreams = await get_appstreams(access_token, trust_env)
    if print_appstreams_json:
        print(json.dumps(appstreams, indent=2))
        return

    transformed = transform_appstreams(appstreams)
    write_output_file(output_file, transformed, output_format, output_var)

    meta = appstreams.get("meta", {}) if isinstance(appstreams, dict) else {}
    count = meta.get("count", "unknown")
    LOGGER.debug("AppStreams response received (count=%s)", count)
    LOGGER.debug("Transformed output written to %s", output_file)


def main() -> None:
    """Entrypoint for command-line execution with error handling."""

    args = parse_args()
    configure_logging(args.log_level)

    try:
        asyncio.run(
            run(
                args.trust_env,
                args.output_file,
                args.output_format,
                args.output_var,
                args.print_appstreams_json,
            )
        )
    except Exception as exc:
        LOGGER.error("Execution failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
