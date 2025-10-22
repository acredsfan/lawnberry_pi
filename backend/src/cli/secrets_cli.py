from __future__ import annotations

import argparse
import sys

from ..core.secrets_manager import SecretsManager


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LawnBerry Secrets Manager CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_get = sub.add_parser("get", help="Get a secret (prints to stdout)")
    p_get.add_argument("key")

    p_set = sub.add_parser("set", help="Set a secret (creates or updates)")
    p_set.add_argument("key")
    p_set.add_argument("value")

    p_rotate = sub.add_parser("rotate", help="Rotate a secret (bumps version)")
    p_rotate.add_argument("key")
    p_rotate.add_argument("value")

    p_validate = sub.add_parser("validate", help="Validate required secrets are present")

    args = parser.parse_args(argv)
    sm = SecretsManager()

    if args.cmd == "get":
        val = sm.get(args.key, default="", purpose="cli")
        print(val or "")
        return 0 if val is not None else 1
    if args.cmd == "set":
        sm.set(args.key, args.value)
        return 0
    if args.cmd == "rotate":
        sm.rotate(args.key, args.value)
        return 0
    if args.cmd == "validate":
        missing = sm.validate_required(["JWT_SECRET"])  # baseline
        return 0 if not missing else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
