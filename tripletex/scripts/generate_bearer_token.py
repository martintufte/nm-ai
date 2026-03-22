"""Generate a random bearer token for the Tripletex server."""

import secrets
import sys


def main() -> None:
    sys.stdout.write(secrets.token_urlsafe(32) + "\n")


if __name__ == "__main__":
    main()
