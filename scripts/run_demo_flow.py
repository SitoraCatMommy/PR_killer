#!/usr/bin/env python3
"""End-to-end demo: create demo project+batch, wait for Celery pipelines, batch report, verify public link.

Requires a running API and Celery worker (same Redis/DB). Set OPENAI_API_KEY for extraction + report.

Environment:
  DEMO_API_BASE          API root including prefix (default: http://127.0.0.1:8000/api/v1)
  DEMO_PROCESS_TIMEOUT   Seconds to wait for chunk+extract (default: 420)
  DEMO_REPORT_TIMEOUT     Seconds to wait for batch report after queue (default: 600)
  DEMO_POLL_INTERVAL      Poll interval seconds (default: 3)
"""

from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlparse

import httpx


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _origin_from_api_base(api_base: str) -> str:
    p = urlparse(api_base)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"


def main() -> None:
    api_base = os.environ.get("DEMO_API_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
    process_timeout = float(os.environ.get("DEMO_PROCESS_TIMEOUT", "420"))
    report_timeout = float(os.environ.get("DEMO_REPORT_TIMEOUT", "600"))
    poll = float(os.environ.get("DEMO_POLL_INTERVAL", "3"))

    t0_process = time.monotonic()
    deadline_process = t0_process + process_timeout

    with httpx.Client(base_url=api_base, timeout=120.0) as client:
        r = client.post("/demo/create")
        if r.status_code != 200:
            _die(f"POST /demo/create -> {r.status_code}\n{r.text}")
        created = r.json()
        batch_id = created["batch_id"]
        project_id = created["project_id"]
        report_path = str(created.get("report_path") or "").strip()
        public_token = str(created.get("public_token") or "").strip()

        print("demo/create:", created)

        def batch_doc_ids() -> list[str]:
            br = client.get(f"/batches/{batch_id}")
            if br.status_code != 200:
                _die(f"GET /batches/{{id}} -> {br.status_code}\n{br.text}")
            out: list[str] = []
            for s in br.json().get("sources") or []:
                if s.get("source_kind") == "document" and s.get("source_document_id"):
                    out.append(str(s["source_document_id"]))
            return out

        doc_ids = batch_doc_ids()
        if not doc_ids:
            _die("No document sources on demo batch.")

        nudged_chunk = False
        nudged_extract = False

        while time.monotonic() < deadline_process:
            all_ready = True
            states: list[tuple[str, int, int]] = []
            for did in doc_ids:
                dr = client.get(f"/sources/documents/{did}")
                if dr.status_code != 200:
                    all_ready = False
                    states.append((did, -1, -1))
                    continue
                d = dr.json()
                ch = int(d.get("text_chunks_count") or 0)
                en = int(d.get("extracted_entities_count") or 0)
                states.append((did, ch, en))
                if ch < 1 or en < 1:
                    all_ready = False

            if all_ready:
                for did, ch, en in states:
                    print(f"  ready document {did}: chunks={ch} entities={en}")
                break

            elapsed = time.monotonic() - t0_process
            if elapsed > 15 and not nudged_chunk:
                # Worker may have been down at demo/create; idempotent chunk queue.
                nudged_chunk = True
                for did in doc_ids:
                    cr = client.post(f"/sources/documents/{did}/chunk")
                    print(f"  nudge POST /sources/documents/.../chunk -> {cr.status_code}")
            if elapsed > 30 and not nudged_extract:
                nudged_extract = True
                for did in doc_ids:
                    er = client.post(f"/sources/documents/{did}/extract")
                    print(f"  nudge POST /sources/documents/.../extract -> {er.status_code}")

            time.sleep(poll)
        else:
            _die(
                "Timeout waiting for chunking + extraction. "
                "Ensure `docker compose up -d worker` (or equivalent) and OPENAI_API_KEY.",
                2,
            )

        gr = client.post(
            f"/batches/{batch_id}/report/generate",
            json={"output_language": "ru"},
        )
        if gr.status_code != 202:
            _die(f"POST /batches/.../report/generate -> {gr.status_code}\n{gr.text}")
        print("batch report queued:", gr.json())

        t_report = time.monotonic()
        deadline_report = t_report + report_timeout
        while time.monotonic() < deadline_report:
            er = client.get(f"/batches/{batch_id}/export/excel")
            if er.status_code == 200:
                print(f"batch report READY (excel probe {len(er.content)} bytes)")
                break
            if er.status_code in (404, 409):
                time.sleep(poll)
                continue
            _die(f"GET /batches/.../export/excel -> {er.status_code}\n{er.text[:800]}", 4)
        else:
            _die(
                "Timeout waiting for batch research report. "
                "Check worker logs and OPENAI_API_KEY.",
                4,
            )

        if public_token and report_path:
            pr = client.get(f"/report/public/{public_token}")
            if pr.status_code != 200:
                _die(f"GET public report -> {pr.status_code}\n{pr.text[:800]}")
            print("public report OK, keys:", list(pr.json().keys())[:8])

        origin = _origin_from_api_base(api_base)
        if origin and report_path.startswith("/"):
            print("\n--- Public page (open in browser) ---")
            print(f"{origin}{report_path}")
        elif report_path:
            print("\n--- Public path (relative) ---")
            print(report_path)


if __name__ == "__main__":
    main()
