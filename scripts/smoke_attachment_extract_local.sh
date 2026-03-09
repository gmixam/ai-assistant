#!/usr/bin/env bash

set -euo pipefail

BACKEND_CONTAINER="${BACKEND_CONTAINER:-ai_backend}"
PDF_SAMPLE_PATH="${PDF_SAMPLE_PATH:-}"

command -v docker >/dev/null 2>&1 || { echo "FAIL: required command not found: docker" >&2; exit 1; }

docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || {
  echo "FAIL: backend container not found: $BACKEND_CONTAINER" >&2
  exit 1
}

docker exec -e PDF_SAMPLE_PATH="$PDF_SAMPLE_PATH" -i "$BACKEND_CONTAINER" python - <<'PY'
import io
import os
import pathlib

from docx import Document

from app.attachment_pipeline import _extract_text


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


txt_payload = "Hello from txt attachment".encode("utf-8")
txt_extracted = _extract_text(txt_payload, "text/plain")
if "Hello from txt attachment" not in txt_extracted:
    fail("txt extraction failed")
print("PASS: txt extraction")

docx_buffer = io.BytesIO()
doc = Document()
doc.add_paragraph("Hello from docx attachment")
doc.save(docx_buffer)
docx_extracted = _extract_text(
    docx_buffer.getvalue(),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
if "Hello from docx attachment" not in docx_extracted:
    fail("docx extraction failed")
print("PASS: docx extraction")

pdf_sample_path = os.getenv("PDF_SAMPLE_PATH", "").strip()
if pdf_sample_path:
    path = pathlib.Path(pdf_sample_path)
    if not path.exists():
        fail(f"PDF_SAMPLE_PATH not found in container: {pdf_sample_path}")
    payload = path.read_bytes()
    pdf_extracted = _extract_text(payload, "application/pdf")
    if not pdf_extracted.strip():
        fail("pdf extraction returned empty text")
    print("PASS: pdf extraction")
else:
    print("SKIP: pdf extraction (set PDF_SAMPLE_PATH to run)")

print("SMOKE ATTACHMENT EXTRACTION LOCAL PASSED")
PY
