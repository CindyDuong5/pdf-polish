# app/services/additional_documents.py
from __future__ import annotations

import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote
from uuid import uuid4

import requests
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.email.smtp_sender import EmailAttachment


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    # add later if needed:
    # "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _clean_display_name(name: str) -> str:
    v = (name or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail="display_name is required")
    return v


def _safe_filename(name: str) -> str:
    v = (name or "").strip()
    if not v:
        return "file"
    v = v.replace("\\", "_").replace("/", "_")
    v = re.sub(r"\s+", " ", v).strip()
    return v or "file"


def _filename_from_url(file_url: str) -> str:
    path = urlparse(file_url).path or ""
    name = unquote(path.split("/")[-1]).strip()
    return _safe_filename(name or "file")


def _extension_from_name(name: str | None) -> str:
    if not name:
        return ""
    return Path(name).suffix or ""


def _guess_content_type(filename: str | None, fallback: str | None = None) -> str:
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or fallback or "application/octet-stream"


def _is_allowed_content_type(content_type: str) -> bool:
    base = (content_type or "").split(";")[0].strip().lower()
    return base in ALLOWED_CONTENT_TYPES


def _build_storage_key(doc_id: str, original_filename: str) -> str:
    d = datetime.now(timezone.utc).date().isoformat()
    safe_name = _safe_filename(original_filename)
    return f"additional_documents/{d}/{doc_id}/{uuid4()}_{safe_name}"


def _get_document_row(db: Session, doc_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT id, doc_type, status
            FROM public.documents
            WHERE id = :id
            """
        ),
        {"id": doc_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    rowd = dict(row)
    if (rowd.get("status") or "").upper() == "REPLACED":
        raise HTTPException(status_code=409, detail="This document has been replaced by a newer version.")

    return rowd


def list_additional_documents(db: Session, doc_id: str) -> list[dict[str, Any]]:
    _get_document_row(db, doc_id)

    rows = db.execute(
        text(
            """
            SELECT
                id,
                document_id,
                display_name,
                source_type,
                storage_key,
                original_filename,
                content_type,
                file_size,
                created_at,
                updated_at
            FROM public.document_additional_documents
            WHERE document_id = :doc_id
            ORDER BY created_at ASC
            """
        ),
        {"doc_id": doc_id},
    ).mappings().all()

    return [dict(r) for r in rows]


async def create_uploaded_additional_document(
    db: Session,
    storage,
    doc_id: str,
    display_name: str,
    upload_file: UploadFile,
) -> dict[str, Any]:
    _get_document_row(db, doc_id)

    display_name = _clean_display_name(display_name)

    original_filename = _safe_filename(upload_file.filename or "file")
    content_type = (upload_file.content_type or "").split(";")[0].strip().lower()
    if not content_type:
        content_type = _guess_content_type(original_filename)

    if not _is_allowed_content_type(content_type):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed types: PDF, JPG, JPEG, PNG.",
        )

    data = await upload_file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File is too large. Max 10 MB.")

    storage_key = _build_storage_key(doc_id, original_filename)
    storage.upload_bytes(key=storage_key, data=data, content_type=content_type)

    row = db.execute(
        text(
            """
            INSERT INTO public.document_additional_documents (
                id,
                document_id,
                display_name,
                source_type,
                storage_key,
                original_filename,
                content_type,
                file_size,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :document_id,
                :display_name,
                :source_type,
                :storage_key,
                :original_filename,
                :content_type,
                :file_size,
                now(),
                now()
            )
            RETURNING
                id,
                document_id,
                display_name,
                source_type,
                storage_key,
                original_filename,
                content_type,
                file_size,
                created_at,
                updated_at
            """
        ),
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "display_name": display_name,
            "source_type": "upload",
            "storage_key": storage_key,
            "original_filename": original_filename,
            "content_type": content_type,
            "file_size": len(data),
        },
    ).mappings().first()

    db.commit()
    return dict(row)


def create_url_additional_document(
    db: Session,
    storage,
    doc_id: str,
    display_name: str,
    file_url: str,
) -> dict[str, Any]:
    _get_document_row(db, doc_id)

    display_name = _clean_display_name(display_name)
    file_url = (file_url or "").strip()
    if not file_url:
        raise HTTPException(status_code=400, detail="file_url is required")

    try:
        r = requests.get(file_url, timeout=60)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download file from URL: {e}")

    data = r.content or b""
    if not data:
        raise HTTPException(status_code=400, detail="Downloaded file is empty")

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File is too large. Max 10 MB.")

    content_type = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    original_filename = _filename_from_url(file_url)

    if not content_type:
        content_type = _guess_content_type(original_filename)

    if content_type == "text/html":
        raise HTTPException(
            status_code=400,
            detail="Provided URL does not appear to be a direct file link.",
        )

    if not _is_allowed_content_type(content_type):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type from URL. Allowed types: PDF, JPG, JPEG, PNG.",
        )

    storage_key = _build_storage_key(doc_id, original_filename)
    storage.upload_bytes(key=storage_key, data=data, content_type=content_type)

    row = db.execute(
        text(
            """
            INSERT INTO public.document_additional_documents (
                id,
                document_id,
                display_name,
                source_type,
                storage_key,
                original_filename,
                content_type,
                file_size,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :document_id,
                :display_name,
                :source_type,
                :storage_key,
                :original_filename,
                :content_type,
                :file_size,
                now(),
                now()
            )
            RETURNING
                id,
                document_id,
                display_name,
                source_type,
                storage_key,
                original_filename,
                content_type,
                file_size,
                created_at,
                updated_at
            """
        ),
        {
            "id": str(uuid4()),
            "document_id": doc_id,
            "display_name": display_name,
            "source_type": "url",
            "storage_key": storage_key,
            "original_filename": original_filename,
            "content_type": content_type,
            "file_size": len(data),
        },
    ).mappings().first()

    db.commit()
    return dict(row)


def delete_additional_document(
    db: Session,
    storage,
    doc_id: str,
    additional_doc_id: str,
) -> None:
    _get_document_row(db, doc_id)

    row = db.execute(
        text(
            """
            SELECT id, storage_key
            FROM public.document_additional_documents
            WHERE id = :id AND document_id = :doc_id
            """
        ),
        {"id": additional_doc_id, "doc_id": doc_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Additional document not found")

    rowd = dict(row)

    db.execute(
        text(
            """
            DELETE FROM public.document_additional_documents
            WHERE id = :id AND document_id = :doc_id
            """
        ),
        {"id": additional_doc_id, "doc_id": doc_id},
    )
    db.commit()

    try:
        storage.delete_object(rowd["storage_key"])
    except Exception:
        pass


def _attachment_filename(display_name: str, original_filename: str | None, content_type: str | None) -> str:
    ext = _extension_from_name(original_filename)
    if not ext:
        guessed_ext = mimetypes.guess_extension(content_type or "")
        ext = guessed_ext or ""
    base = _safe_filename(display_name)
    return f"{base}{ext}" if ext else base


def build_additional_email_attachments(db: Session, storage, doc_id: str) -> list[EmailAttachment]:
    rows = list_additional_documents(db, doc_id)

    attachments: list[EmailAttachment] = []
    for row in rows:
        storage_key = row.get("storage_key")
        if not storage_key:
            continue

        data = storage.download_bytes(storage_key)
        filename = _attachment_filename(
            display_name=row.get("display_name") or "Attachment",
            original_filename=row.get("original_filename"),
            content_type=row.get("content_type"),
        )
        content_type = row.get("content_type") or "application/octet-stream"

        attachments.append(
            EmailAttachment(
                filename=filename,
                content_type=content_type,
                data=data,
            )
        )

    return attachments