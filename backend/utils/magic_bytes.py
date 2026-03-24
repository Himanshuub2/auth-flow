"""Lightweight upload hardening: read only a small prefix and match magic bytes."""

from __future__ import annotations

import filetype
from fastapi import HTTPException, UploadFile, status

# 1KiB: covers filetype for images, PDF, MP4/MOV ftyp, OLE .doc (>515B), typical OOXML.
MAGIC_PREFIX_LEN = 1024


def normalize_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


async def read_prefix_and_rewind(file: UploadFile, max_bytes: int = MAGIC_PREFIX_LEN) -> bytes:
    await file.seek(0)
    prefix = await file.read(max_bytes)
    await file.seek(0)
    return prefix


def validate_magic_prefix(filename: str, prefix: bytes, allowed_mimes: frozenset[str]) -> None:
    """
    Compare filetype guess on the first bytes only against allowed MIME set.
    Caller supplies allowed_mimes for the file extension (incl. signature variants).
    """
    if not allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot verify file content for '{filename}'",
        )

    guessed = filetype.guess(prefix)
    if guessed is None:
        if len(prefix) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' is empty",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not verify file content for '{filename}' (try a valid file)",
        )

    actual = guessed.mime.lower()
    if actual not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File content type '{actual}' does not match "
                f"extension for '{filename}'"
            ),
        )
