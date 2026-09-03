#!/usr/bin/env python3
"""Obtain a production Clerk session JWT via sign-in ticket + Playwright."""

from __future__ import annotations

import base64
import os
import sys

import httpx
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get("E2E_USER_EMAIL", "markdooling25@gmail.com")
FRONTEND = os.environ.get("E2E_FRONTEND_URL", "https://www.kastree.ie").rstrip("/")
CLERK_SECRET = os.environ["CLERK_SECRET_KEY"]
CLERK_PK = os.environ["CLERK_PUBLISHABLE_KEY"]


def clerk_host_from_pk(pk: str) -> str:
    raw = pk.split("_", 2)[-1]
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode().rstrip("$")


def get_sign_in_ticket(user_id: str) -> str:
    headers = {"Authorization": f"Bearer {CLERK_SECRET}"}
    resp = httpx.post(
        "https://api.clerk.com/v1/sign_in_tokens",
        json={"user_id": user_id, "expires_in_seconds": 600},
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def get_user_id(email: str) -> str:
    headers = {"Authorization": f"Bearer {CLERK_SECRET}"}
    resp = httpx.get(
        "https://api.clerk.com/v1/users",
        params={"email_address": [email]},
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    users = resp.json()
    if not users:
        raise RuntimeError(f"No Clerk user for {email}")
    return users[0]["id"]


def main() -> None:
    user_id = get_user_id(EMAIL)
    ticket = get_sign_in_ticket(user_id)
    ticket_url = f"{FRONTEND}/sign-in?__clerk_ticket={ticket}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(ticket_url, wait_until="networkidle", timeout=60000)
        # Wait for Clerk to finish sign-in and redirect into the app.
        page.wait_for_timeout(5000)
        token = page.evaluate(
            """async () => {
                const clerk = window.Clerk;
                if (!clerk) throw new Error('Clerk not loaded');
                await clerk.load();
                if (!clerk.session) throw new Error('No active Clerk session');
                return await clerk.session.getToken();
            }"""
        )
        browser.close()

    if not token:
        print("FAIL: empty token", file=sys.stderr)
        sys.exit(1)
    # Print token to stdout for shell capture — caller must not log this in CI artifacts.
    print(token)


if __name__ == "__main__":
    main()
