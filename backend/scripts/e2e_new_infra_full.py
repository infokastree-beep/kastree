#!/usr/bin/env python3
"""Full production E2E against NEW Railway backend (pre-DNS cutover).

Steps: health → Clerk sign-in → list/create client+company → upload TB →
parse/map → confirm mapping → validation → statements → export → download → R2.

Writes evidence JSON + downloaded export under EVIDENCE_DIR (default /tmp/e2e-new-infra).
Prints no secrets.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

import httpx
import openpyxl

API = os.environ.get(
    "E2E_API_BASE", "https://kastree-production-5658.up.railway.app"
).rstrip("/")
EMAIL = os.environ.get("E2E_USER_EMAIL", "markdooling25@gmail.com")
EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", "/tmp/e2e-new-infra"))
POLL_INTERVAL = 2.0
MAX_POLLS = 60


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def save(name: str, payload: object) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"EVIDENCE: {path}")
    return path


def step(title: str) -> None:
    print(f"\n=== {title} ===")


def clerk_session_jwt(email: str) -> str:
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
        fail(f"clerk_prod_jwt failed: {proc.stderr[:800] or proc.stdout[:800]}")
    token = proc.stdout.strip()
    if not token:
        fail("clerk_prod_jwt returned empty token")
    return token


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def balanced_tb_xlsx_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.append(["Account Code", "Account Name", "Debit", "Credit"])
    ws.append(["1100", "Cash at bank", "10000.00", "0.00"])
    ws.append(["3100", "Retained earnings", "0.00", "6000.00"])
    ws.append(["3000", "Share capital", "0.00", "4000.00"])
    ws.append(["4100", "Sales - Online", "0.00", "5000.00"])
    ws.append(["6100", "Operating expenses", "5000.00", "0.00"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def canonical_for(code: str | None, suggested: str) -> str:
    return {
        "1100": "cash",
        "4100": "revenue",
        "6100": "operating_expenses",
        "3000": "share_capital",
        "3100": "retained_earnings",
    }.get(code or "", suggested)


def verify_r2_object(export_id: str, fmt: str) -> dict:
    import boto3
    from botocore.exceptions import ClientError

    bucket = os.environ["S3_BUCKET"]
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if endpoint and endpoint.rstrip("/").endswith(f"/{bucket}"):
        endpoint = endpoint.rstrip("/")[: -(len(bucket) + 1)]
    region = os.environ.get("S3_REGION", "auto")
    if endpoint and "r2.cloudflarestorage.com" in endpoint:
        if region not in {"wnam", "enam", "weur", "eeur", "apac", "oc", "auto"}:
            region = "auto"
    key = f"exports/{export_id}.{fmt}"
    kwargs: dict = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    kwargs["aws_access_key_id"] = os.environ["AWS_ACCESS_KEY_ID"]
    kwargs["aws_secret_access_key"] = os.environ["AWS_SECRET_ACCESS_KEY"]
    client = boto3.client("s3", **kwargs)
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        fail(f"R2 head_object failed for {key}: {exc}")
    return {
        "bucket": bucket,
        "key": key,
        "size": head["ContentLength"],
        "etag": head["ETag"],
        "content_type": head.get("ContentType"),
    }


def main() -> None:
    evidence: dict = {"api_base": API, "email": EMAIL, "steps": {}}

    step("0 Health")
    health = httpx.get(f"{API}/health", timeout=15.0)
    print(f"GET {API}/health → {health.status_code} {health.text}")
    if health.status_code != 200:
        fail("Health check failed")
    evidence["steps"]["health"] = {"status": health.status_code, "body": health.json()}

    step("1 Auth (real Clerk user via sign-in ticket)")
    token = clerk_session_jwt(EMAIL)
    print(f"Clerk JWT obtained for {EMAIL} (len={len(token)})")
    me = httpx.get(f"{API}/users/me", headers=headers(token), timeout=30.0)
    print(f"GET /users/me → {me.status_code}")
    if me.status_code != 200:
        fail(f"/users/me failed: {me.text[:500]}")
    me_body = me.json()
    # Redact nothing sensitive beyond ids/email already known
    save(
        "01-auth-me.json",
        {
            "status": me.status_code,
            "email": me_body.get("email"),
            "role": me_body.get("role"),
            "org_id": me_body.get("org_id"),
            "user_id": me_body.get("id") or me_body.get("user_id"),
            "keys": sorted(me_body.keys()),
        },
    )
    evidence["steps"]["auth"] = {"email": EMAIL, "me_status": 200, "role": me_body.get("role")}

    org = httpx.get(f"{API}/organisations/me", headers=headers(token), timeout=30.0)
    print(f"GET /organisations/me → {org.status_code}")
    if org.status_code == 200:
        save(
            "01b-org-me.json",
            {
                "status": 200,
                "id": org.json().get("id"),
                "name": org.json().get("name"),
                "subscription_tier": org.json().get("subscription_tier"),
            },
        )

    step("2 List existing clients")
    clients = httpx.get(f"{API}/clients", headers=headers(token), timeout=30.0)
    print(f"GET /clients → {clients.status_code}")
    if clients.status_code != 200:
        fail(clients.text[:500])
    client_list = clients.json()
    save(
        "02-clients-list.json",
        {
            "status": 200,
            "total": client_list.get("total"),
            "names": [c.get("name") for c in (client_list.get("items") or [])],
            "ids": [c.get("id") for c in (client_list.get("items") or [])],
        },
    )
    evidence["steps"]["list_clients"] = {
        "total": client_list.get("total"),
        "count": len(client_list.get("items") or []),
    }

    step("3 Create client + company")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    client_name = f"E2E Cutover Client {stamp}"
    create_client = httpx.post(
        f"{API}/clients",
        headers={**headers(token), "Content-Type": "application/json"},
        json={"name": client_name},
        timeout=30.0,
    )
    print(f"POST /clients → {create_client.status_code}")
    if create_client.status_code not in (200, 201):
        fail(create_client.text[:500])
    client = create_client.json()
    client_id = client["id"]
    save(
        "03-client-created.json",
        {"status": create_client.status_code, "id": client_id, "name": client.get("name")},
    )

    company_name = f"E2E Cutover Co {stamp}"
    create_co = httpx.post(
        f"{API}/clients/{client_id}/companies",
        headers={**headers(token), "Content-Type": "application/json"},
        json={
            "name": company_name,
            "company_number": f"E2E{stamp[-6:]}",
            "industry": "professional_services",
            "functional_currency": "GBP",
        },
        timeout=30.0,
    )
    print(f"POST /clients/{{id}}/companies → {create_co.status_code}")
    if create_co.status_code not in (200, 201):
        fail(create_co.text[:500])
    company = create_co.json()
    company_id = company["id"]
    save(
        "03b-company-created.json",
        {
            "status": create_co.status_code,
            "id": company_id,
            "name": company.get("name"),
            "functional_currency": company.get("functional_currency"),
        },
    )
    evidence["steps"]["create"] = {
        "client_id": client_id,
        "company_id": company_id,
        "client_name": client_name,
        "company_name": company_name,
    }

    # Re-fetch client to prove view path
    get_client = httpx.get(
        f"{API}/clients/{client_id}", headers=headers(token), timeout=30.0
    )
    print(f"GET /clients/{{id}} → {get_client.status_code} name={get_client.json().get('name')}")
    if get_client.status_code != 200:
        fail(get_client.text[:500])

    step("4 Upload trial balance")
    tb_bytes = balanced_tb_xlsx_bytes()
    save("04-upload-source.xlsx", tb_bytes)
    # Unique period_end to avoid UNIQUE(client/company, period_end) — use far-future month
    period_end = date(2030, 9, 30).isoformat()
    upload = httpx.post(
        f"{API}/trial-balances/upload",
        headers=headers(token),
        data={
            "company_id": company_id,
            "period_end": period_end,
            "currency": "GBP",
        },
        files={
            "file": (
                "e2e-cutover-tb.xlsx",
                tb_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        timeout=120.0,
    )
    print(f"POST /trial-balances/upload → {upload.status_code}")
    if upload.status_code != 202:
        fail(upload.text[:800])
    upload_body = upload.json()
    tb_id = upload_body["tb_id"]
    save("04-upload-accepted.json", upload_body)
    evidence["steps"]["upload"] = {"tb_id": tb_id, "period_end": period_end, "bytes": len(tb_bytes)}
    print(f"TB_ID: {tb_id}")

    step("5 Poll parse + map")
    status_body = None
    for i in range(MAX_POLLS):
        status_resp = httpx.get(
            f"{API}/trial-balances/{tb_id}/status",
            headers=headers(token),
            timeout=30.0,
        )
        status_resp.raise_for_status()
        status_body = status_resp.json()
        jobs = {j["job_type"]: j["status"] for j in status_body.get("jobs") or []}
        print(
            f"POLL {i + 1}: tb_status={status_body.get('status')} jobs={jobs}"
        )
        if jobs.get("parse") == "complete" and jobs.get("map") == "complete":
            break
        if status_body.get("status") == "failed" or "failed" in jobs.values():
            save("05-status-failed.json", status_body)
            fail(f"processing failed: {status_body}")
        time.sleep(POLL_INTERVAL)
    else:
        save("05-status-timeout.json", status_body)
        fail(f"timed out waiting for parse/map: {status_body}")
    save("05-status-ready.json", status_body)
    evidence["steps"]["parse_map"] = status_body

    step("6 Mapping review + confirm")
    mapping_resp = httpx.get(
        f"{API}/trial-balances/{tb_id}/mapping",
        headers=headers(token),
        timeout=30.0,
    )
    print(f"GET /trial-balances/{{id}}/mapping → {mapping_resp.status_code}")
    if mapping_resp.status_code != 200:
        fail(mapping_resp.text[:500])
    mapping_body = mapping_resp.json()
    mappings = mapping_body.get("mappings") or []
    save(
        "06-mapping.json",
        {
            "tb_id": mapping_body.get("tb_id"),
            "mapping_rate": mapping_body.get("mapping_rate"),
            "count": len(mappings),
            "rows": [
                {
                    "source_code": m.get("source_code"),
                    "source_name": m.get("source_name"),
                    "suggested": m.get("suggested_canonical_line"),
                    "method": m.get("method"),
                    "confidence": m.get("confidence"),
                }
                for m in mappings
            ],
        },
    )
    if len(mappings) < 1:
        fail("No mapping rows returned")

    confirm_items = []
    for item in mappings:
        confirm_items.append(
            {
                "id": item["id"],
                "canonical_line": canonical_for(
                    item.get("source_code"), item["suggested_canonical_line"]
                ),
                "is_confirmed": True,
                "is_ignored": False,
            }
        )
    confirm = httpx.post(
        f"{API}/trial-balances/{tb_id}/mapping/confirm",
        headers={**headers(token), "Content-Type": "application/json"},
        json={"mappings": confirm_items},
        timeout=60.0,
    )
    print(f"POST /mapping/confirm → {confirm.status_code} {confirm.text[:200]}")
    if confirm.status_code != 200:
        fail(confirm.text[:500])
    save("06b-mapping-confirm.json", confirm.json())
    evidence["steps"]["mapping"] = {
        "rows": len(mappings),
        "confirmed": confirm.json().get("confirmed_count"),
        "status": confirm.json().get("status"),
    }

    step("7 Validation")
    validation_body = None
    for i in range(MAX_POLLS):
        validation = httpx.get(
            f"{API}/trial-balances/{tb_id}/validation",
            headers=headers(token),
            timeout=30.0,
        )
        if validation.status_code == 200:
            validation_body = validation.json()
            print(
                f"POLL {i + 1}: all_passed={validation_body.get('all_passed')} "
                f"can_generate={validation_body.get('can_generate_statements')}"
            )
            # Wait until validating job finishes if checks empty / still running
            if validation_body.get("checks") is not None:
                break
        else:
            print(f"POLL {i + 1}: validation → {validation.status_code}")
        time.sleep(POLL_INTERVAL)
    else:
        fail("timed out waiting for validation")
    assert validation_body is not None
    save("07-validation.json", validation_body)
    if not validation_body.get("can_generate_statements"):
        fail(f"cannot generate statements: {validation_body}")
    evidence["steps"]["validation"] = {
        "all_passed": validation_body.get("all_passed"),
        "can_generate_statements": validation_body.get("can_generate_statements"),
        "checks": [
            {"name": c.get("check_name") or c.get("name"), "passed": c.get("passed")}
            for c in (validation_body.get("checks") or [])
        ],
    }

    step("8 Generate statements")
    gen = httpx.post(
        f"{API}/trial-balances/{tb_id}/statements",
        headers=headers(token),
        timeout=120.0,
    )
    print(f"POST /statements → {gen.status_code}")
    if gen.status_code != 200:
        fail(gen.text[:800])
    gen_body = gen.json()
    statements = gen_body.get("statements") or []
    save(
        "08-statements.json",
        {
            "count": len(statements),
            "types": [s.get("statement_type") for s in statements],
            "line_counts": {
                s.get("statement_type"): len(s.get("line_items") or s.get("lines") or [])
                for s in statements
            },
            "preview": [
                {
                    "type": s.get("statement_type"),
                    "first_lines": (s.get("line_items") or s.get("lines") or [])[:5],
                }
                for s in statements
            ],
        },
    )
    types = {s.get("statement_type") for s in statements}
    if types != {"SOPL", "SOFP", "SOCIE"}:
        fail(f"Unexpected statement types: {types}")
    print(f"STATEMENTS: {sorted(types)} ({len(statements)} blocks)")
    evidence["steps"]["statements"] = {"types": sorted(types), "count": len(statements)}

    got = httpx.get(
        f"{API}/trial-balances/{tb_id}/statements",
        headers=headers(token),
        timeout=30.0,
    )
    print(f"GET /statements → {got.status_code} blocks={len(got.json().get('statements') or [])}")
    if got.status_code != 200 or len(got.json().get("statements") or []) != 3:
        fail("GET statements mismatch")

    step("9 Export xlsx + download + R2")
    create = httpx.post(
        f"{API}/trial-balances/{tb_id}/export",
        headers={**headers(token), "Content-Type": "application/json"},
        json={"format": "xlsx"},
        timeout=60.0,
    )
    print(f"POST /export → {create.status_code}")
    if create.status_code not in (200, 202):
        fail(create.text[:500])
    accepted = create.json()
    export_id = accepted["export_id"]
    save("09-export-accepted.json", accepted)
    print(f"EXPORT_ID: {export_id}")

    final = None
    for i in range(MAX_POLLS):
        resp = httpx.get(
            f"{API}/exports/{export_id}", headers=headers(token), timeout=30.0
        )
        resp.raise_for_status()
        final = resp.json()
        print(f"POLL {i + 1}: export status={final.get('status')}")
        if final.get("status") == "complete":
            break
        if final.get("status") == "failed":
            save("09-export-failed.json", final)
            fail(f"Export failed: {final.get('error_message')}")
        time.sleep(POLL_INTERVAL)
    else:
        fail("Export timed out")
    save(
        "09-export-complete.json",
        {
            k: final.get(k)
            for k in ("id", "status", "format", "file_url", "error_message")
        },
    )

    dl = httpx.get(
        f"{API}/exports/{export_id}/download",
        headers=headers(token),
        timeout=120.0,
        follow_redirects=True,
    )
    print(f"GET /exports/{{id}}/download → {dl.status_code}, bytes={len(dl.content)}")
    if dl.status_code != 200 or len(dl.content) < 100:
        fail(f"Download failed or too small: {dl.status_code}")
    xlsx_path = save(f"09-download-{export_id}.xlsx", dl.content)
    with zipfile.ZipFile(BytesIO(dl.content)) as zf:
        names = zf.namelist()[:8]
    print(f"XLSX_ZIP_ENTRIES: {names}")
    if not names:
        fail("Downloaded xlsx is not a valid zip")

    r2 = verify_r2_object(export_id, "xlsx")
    print(f"R2_OBJECT: {json.dumps(r2)}")
    save("09-r2-head.json", r2)
    evidence["steps"]["export"] = {
        "export_id": export_id,
        "download_bytes": len(dl.content),
        "xlsx_path": str(xlsx_path),
        "zip_entries": names,
        "r2": r2,
    }

    step("PASS — full E2E on NEW infrastructure")
    summary = {
        "result": "PASS",
        "api_base": API,
        "email": EMAIL,
        "client_id": client_id,
        "company_id": company_id,
        "tb_id": tb_id,
        "export_id": export_id,
        "statement_types": sorted(types),
        "r2_key": r2["key"],
        "r2_size": r2["size"],
        "download_bytes": len(dl.content),
    }
    save("00-summary.json", {**summary, "steps": evidence["steps"]})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
