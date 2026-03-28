from __future__ import annotations

import argparse
from getpass import getpass

from .admin_access import set_admin_pin


def _prompt_pin() -> str:
    pin = getpass("Admin PIN: ").strip()
    confirm = getpass("Confirm Admin PIN: ").strip()
    if not pin:
        raise ValueError("Admin PIN cannot be empty.")
    if not pin.isdigit():
        raise ValueError("Admin PIN must contain digits only.")
    if pin != confirm:
        raise ValueError("Admin PIN confirmation does not match.")
    return pin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure local Admin PIN protection.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    subparsers.add_parser("set-pin", help="Create or replace the local Admin PIN.")
    args = parser.parse_args(argv)

    if args.command != "set-pin":
        parser.print_help()
        return 1

    try:
        pin = _prompt_pin()
        path = set_admin_pin(pin)
    except ValueError as exc:
        print(str(exc))
        return 1

    print(f"Admin PIN stored at {path}. The file contains only a salted hash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
