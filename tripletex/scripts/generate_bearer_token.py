#!/usr/bin/env python3
"""Generate a random bearer token for the Tripletex server."""

import secrets

print(secrets.token_urlsafe(32))
