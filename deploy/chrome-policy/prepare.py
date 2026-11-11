"""Prepare (but NEVER install) a Swangz one-profile Chrome enterprise policy.

This fills the manually maintained policy template for an administrator. It does
not authenticate to Google/provider sites, create a browser profile, start
Chrome, configure DNS, contact the server, or modify system Chrome policy.
"""

import argparse
import ipaddress
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

TEMPLATE = Path(__file__).with_name("swangz-company-chrome.json")
EXTENSION_ID = re.compile(r"[a-p]{32}\Z")
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
REQUIRED = {
    "BrowserSignin": 0,
    "SyncDisabled": True,
    "BrowserAddPersonEnabled": False,
    "BrowserGuestModeEnabled": False,
    "IncognitoModeAvailability": 1,
    "DeveloperToolsAvailability": 2,
    "RemoteDebuggingAllowed": False,
    "PasswordManagerEnabled": False,
}


class PolicyPreparationError(ValueError):
    """The configuration is not safe or is not complete enough to prepare."""


def hostname(value):
    """A public-looking DNS host, not an IP, URL, wildcard or local hostname.

    This is syntax checking, NOT a DNS/ownership verification.
    """
    if not isinstance(value, str) or not value or value != value.strip() or value.lower() != value:
        raise PolicyPreparationError("Use a lower-case DNS hostname, without a scheme or spaces")
    if value in ("example.com", "example.net", "example.org") or any(
            value.endswith("." + item) for item in ("example.com", "example.net", "example.org")):
        raise PolicyPreparationError("Use a real owned Hub DNS hostname, not a documentation example")
    parts = value.split(".")
    if len(value) > 253 or len(parts) < 2 or any(not LABEL.fullmatch(p) for p in parts):
        raise PolicyPreparationError("Invalid DNS hostname")
    if parts[-1] in ("local", "localhost", "internal", "test", "invalid", "example"):
        raise PolicyPreparationError("Use the actual production DNS domain, not a test/local domain")
    if not any(c.isalpha() for c in parts[-1]):
        raise PolicyPreparationError("Invalid DNS top-level domain")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise PolicyPreparationError("IP addresses are not accepted as the Hub hostname")


def update_address(value):
    if not isinstance(value, str) or value != value.strip() or re.search(r"[\x00-\x20\\]", value):
        raise PolicyPreparationError("Invalid extension update URL")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port is not None or parsed.query or parsed.fragment
                or not parsed.path or parsed.path == "/" or not value.startswith("https://")):
            raise ValueError
        if parsed.hostname != parsed.hostname.lower():
            raise ValueError
        hostname(parsed.hostname)
    except ValueError:
        raise PolicyPreparationError("Update URL must be an HTTPS endpoint on a DNS host; no credentials, port, query or fragment") from None
    return value


def prepare(template, hub_host, extension_id, extension_update_url):
    host = hostname(hub_host)
    if not isinstance(extension_id, str) or not EXTENSION_ID.fullmatch(extension_id):
        raise PolicyPreparationError("Extension ID must be 32 lowercase letters a through p")
    url = update_address(extension_update_url)
    if not isinstance(template, dict):
        raise PolicyPreparationError("Invalid policy template")
    for key, expected in REQUIRED.items():
        if key not in template or type(template[key]) is not type(expected) or template[key] != expected:
            raise PolicyPreparationError("Template lacks required single-profile control: " + key)
    if template.get("URLBlocklist") is None or "*" not in template["URLBlocklist"]:
        raise PolicyPreparationError("Template is not default-deny")
    if template.get("ExtensionInstallBlocklist") != ["*"]:
        raise PolicyPreparationError("Template does not block non-Swangz extensions")
    if (template.get("ExtensionInstallAllowlist") != ["SWANGZ_EXTENSION_ID"]
            or template.get("ExtensionInstallForcelist") != ["SWANGZ_EXTENSION_ID;SWANGZ_EXTENSION_UPDATE_URL"]):
        raise PolicyPreparationError("The extension template was modified unexpectedly")
    if not isinstance(template.get("URLAllowlist"), list) or template["URLAllowlist"].count("SWANGZ_HUB_HOST") != 1:
        raise PolicyPreparationError("The Hub host placeholder is missing or duplicated")
    if not all(isinstance(v, str) for v in template["URLAllowlist"]):
        raise PolicyPreparationError("Invalid navigation entries")
    # Preserve all vetted vendor and login exceptions from the checked-in template.
    rendered = json.loads(json.dumps(template))
    rendered["URLAllowlist"] = [host if item == "SWANGZ_HUB_HOST" else item for item in rendered["URLAllowlist"]]
    rendered["ExtensionInstallAllowlist"] = [extension_id]
    rendered["ExtensionInstallForcelist"] = [extension_id + ";" + url]
    if any("SWANGZ_" in str(v) for v in rendered.values()):
        raise PolicyPreparationError("Unresolved template placeholder")
    return rendered


def write_new(path, policy):
    """Write a private, exclusive output; never overwrite active system policies."""
    path = Path(path)
    if path.suffix.lower() != ".json" or path.resolve() == TEMPLATE.resolve():
        raise PolicyPreparationError("Select a NEW .json output file, not the checked-in template")
    for folder in ("/etc/opt/chrome/policies/managed", "/etc/chromium/policies/managed",
                   "/Library/Managed Preferences"):
        if path.resolve().is_relative_to(Path(folder)):
            raise PolicyPreparationError("Refusing direct writes to active system Chrome policy locations")
    encoded = (json.dumps(policy, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-host", required=True, help="Existing Swangz Hub DNS hostname (no https://)")
    parser.add_argument("--extension-id", required=True, help="Published extension's 32-letter ID")
    parser.add_argument("--update-url", required=True, help="Approved HTTPS Chrome extension update endpoint")
    parser.add_argument("--output", required=True, help="New JSON file outside Chrome's managed-policy path")
    args = parser.parse_args(argv)
    try:
        with TEMPLATE.open(encoding="utf-8") as f:
            template = json.load(f)
        policy = prepare(template, args.hub_host, args.extension_id, args.update_url)
        write_new(args.output, policy)
    except (PolicyPreparationError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, "Cannot prepare Chrome policy: " + str(exc) + "\n")
    print("Prepared a Chrome policy FILE only. No browser or system policy was changed.")
    print("Admin must deploy with Chrome Enterprise/MDM or OS policy, verify chrome://policy and test a separate OS account per employee.")
    print("Provider sign-in is still performed by the authorized person via the provider's approved login; no remote session injection is provided.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
