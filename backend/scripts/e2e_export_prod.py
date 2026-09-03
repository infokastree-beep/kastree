#!/usr/bin/env python3
"""One-shot production export E2E — uses Railway env vars, prints no secrets."""

from __future__ import annotations

import json
import os
import sys
import time
import zipfile
from io import BytesIO

import httpx

API = os.environ.get("E2E_API_BASE", "https://kastree-production.up.railway.app").rstrip("/")
CLERK_SECRET = os.environ.get("CLERK_SECRET_KEY", "")
POLL_INTERVAL = 2.0
MAX_POLLS = 45


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def clerk_session_jwt(email: str) -> str:
    if not CLERK_SECRET:
        fail("CLERK_SECRET_KEY not set")
    # Production Clerk blocks POST /sessions; use sign-in ticket + Playwright.
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parent / "clerk_prod_jwt.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "E2E_USER_EMAIL": email},
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        fail(f"clerk_prod_jwt failed: {proc.stderr[:500]}")
    token = proc.stdout.strip()
    if not token:
        fail("clerk_prod_jwt returned empty token")
    return token


def api_get(path: str, token: str) -> httpx.Response:
    return httpx.get(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
        follow_redirects=True,
    )


def api_post(path: str, token: str, body: dict | None = None) -> httpx.Response:
    return httpx.post(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body or {},
        timeout=120.0,
    )


def find_tb_with_statements(token: str) -> str:
    clients = api_get("/clients", token)
    clients.raise_for_status()
    client_list = clients.json().get("items") or []

    for client in client_list:
        cid = client["id"]
        companies = api_get(f"/clients/{cid}/companies", token)
        if companies.status_code != 200:
            continue
        for company in companies.json().get("items") or []:
            co_id = company["id"]
            tbs = api_get(f"/trial-balances?company_id={co_id}", token)
            if tbs.status_code != 200:
                continue
            for tb in tbs.json().get("items") or []:
                tb_id = tb["id"]
                stmts = api_get(f"/trial-balances/{tb_id}/statements", token)
                if stmts.status_code == 200:
                    body = stmts.json()
                    if body.get("statements"):
                        print(
                            f"FOUND_TB: {tb_id} "
                            f"(client={client.get('name')}, company={company.get('name')})"
                        )
                        return tb_id
    fail("No trial balance with existing statements found")


def ensure_statements(tb_id: str, token: str) -> None:
    resp = api_get(f"/trial-balances/{tb_id}/statements", token)
    if resp.status_code == 200 and resp.json().get("statements"):
        print(f"STATEMENTS: already present ({len(resp.json()['statements'])} blocks)")
        return
    print("STATEMENTS: generating via POST …")
    gen = api_post(f"/trial-balances/{tb_id}/statements", token)
    if gen.status_code not in (200, 201):
        fail(f"POST statements → {gen.status_code}: {gen.text[:500]}")
    body = gen.json()
    if not body.get("statements"):
        fail("POST statements returned no statement blocks")
    print(f"STATEMENTS: generated ({len(body['statements'])} blocks)")


def poll_export(export_id: str, token: str) -> dict:
    for i in range(MAX_POLLS):
        resp = api_get(f"/exports/{export_id}", token)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        print(f"POLL {i + 1}: status={status}")
        if status == "complete":
            return data
        if status == "failed":
            fail(f"Export failed: {data.get('error_message')}")
        time.sleep(POLL_INTERVAL)
    fail("Export timed out")


def verify_r2_object(export_id: str, fmt: str) -> dict:
    import boto3
    from botocore.exceptions import ClientError

    bucket = os.environ["S3_BUCKET"]
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if endpoint and endpoint.rstrip("/").endswith(f"/{bucket}"):
        endpoint = endpoint.rstrip("/")[: -(len(bucket) + 1)]
    region = os.environ.get("S3_REGION", "auto")
    if endpoint and "r2.cloudflarestorage.com" in endpoint:
        r2_ok = {"wnam", "enam", "weur", "eeur", "apac", "oc", "auto"}
        if region not in r2_ok:
            region = "auto"
    key = f"exports/{export_id}.{fmt}"
    kwargs: dict = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        kwargs["aws_access_key_id"] = os.environ["AWS_ACCESS_KEY_ID"]
        kwargs["aws_secret_access_key"] = os.environ["AWS_SECRET_ACCESS_KEY"]
    client = boto3.client("s3", **kwargs)
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        fail(f"R2 head_object failed for {key}: {exc}")
    return {"bucket": bucket, "key": key, "size": head["ContentLength"], "etag": head["ETag"]}


def main() -> None:
    email = os.environ.get("E2E_USER_EMAIL", "markdooling25@gmail.com")
    fmt = os.environ.get("E2E_EXPORT_FORMAT", "xlsx")

    print("=== Health ===")
    health = httpx.get(f"{API}/health", timeout=15.0)
    print(f"GET /health → {health.status_code} {health.text}")
    if health.status_code != 200:
        fail("Health check failed")

    print("=== Auth ===")
    token = clerk_session_jwt(email)
    print(f"Clerk JWT obtained for {email} (len={len(token)})")

    tb_id = find_tb_with_statements(token)
    ensure_statements(tb_id, token)

    print("=== Export POST ===")
    create = api_post(f"/trial-balances/{tb_id}/export", token, {"format": fmt})
    print(f"POST /trial-balances/{tb_id}/export → {create.status_code}")
    if create.status_code not in (200, 202):
        fail(create.text[:500])
    accepted = create.json()
    export_id = accepted["export_id"]
    print(f"EXPORT_ID: {export_id}")

    print("=== Poll export status ===")
    final = poll_export(export_id, token)
    print(f"EXPORT_COMPLETE: {json.dumps({k: final.get(k) for k in ('id', 'status', 'format', 'file_url')})}")

    print("=== Download via API ===")
    dl = httpx.get(
        f"{API}/exports/{export_id}/download",
        headers={"Authorization": f"Bearer {token}"},
        timeout=120.0,
        follow_redirects=True,
    )
    print(f"GET /exports/{export_id}/download → {dl.status_code}, bytes={len(dl.content)}")
    if dl.status_code != 200 or len(dl.content) < 100:
        fail(f"Download failed or too small: {dl.status_code}")

    if fmt == "xlsx":
        with zipfile.ZipFile(BytesIO(dl.content)) as zf:
            names = zf.namelist()[:5]
        print(f"XLSX_ZIP_ENTRIES: {names}")
        if not names:
            fail("Downloaded xlsx is not a valid zip")
    elif fmt == "pdf":
        if not dl.content.startswith(b"%PDF"):
            fail("Downloaded file is not a PDF")
        print("PDF_MAGIC: %PDF OK")
    else:
        preview = dl.content[:80].decode("utf-8", errors="replace")
        print(f"CSV_PREVIEW: {preview!r}")

    print("=== R2 head_object ===")
    r2 = verify_r2_object(export_id, fmt)
    print(f"R2_OBJECT: {json.dumps(r2)}")

    print("=== PASS: end-to-end export verified ===")


if __name__ == "__main__":
    main()
