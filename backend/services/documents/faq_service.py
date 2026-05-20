"""
FAQ Service
------------
Fetches the active FAQ document from blob storage, parses the Excel file
(Section / Question / Response), and returns a dict grouped by section.
Results are cached and invalidated when FAQ documents are created or updated.
"""

import asyncio
import io
import logging

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cache import cache_get, cache_set
from config import settings
from models.documents.document import Document, DocumentStatus, DocumentType
from storage import get_storage
from utils import cache_keys

logger = logging.getLogger(__name__)

FAQ_CACHE_TTL_SECONDS = 2 * 24 * 60 * 60  # 2 days


def _parse_faq_excel(file_bytes: bytes) -> dict[str, dict[str, str]]:
    """Parse FAQ xlsx bytes into {section: {question: response}}."""
    wb = load_workbook(filename=io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return {}

    result: dict[str, dict[str, str]] = {}

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if len(row) < 3:
            continue
        section, question, response = row[0], row[1], row[2]
        if not section or not question or not response:
            continue
        section_str = str(section).strip()
        question_str = str(question).strip()
        response_str = str(response).strip()
        if not section_str or not question_str:
            continue
        result.setdefault(section_str, {})[question_str] = response_str

    wb.close()
    return result


async def get_faq_data(db: AsyncSession) -> dict[str, dict[str, str]]:
    """Return parsed FAQ data, using cache when available."""
    key = cache_keys.faq_data()
    cached = await cache_get(key)
    if cached is not None:
        return cached

    stmt = (
        select(Document)
        .options(selectinload(Document.files))
        .where(
            Document.document_type == DocumentType.FAQ,
            Document.status == DocumentStatus.ACTIVE,
        )
        .order_by(Document.updated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    doc = result.scalars().first()

    if doc is None or not doc.files:
        return {}

    blob_path = doc.files[0].file_url
    storage = get_storage()
    file_bytes = await storage.read_bytes(blob_path)

    faq_data = await asyncio.to_thread(_parse_faq_excel, file_bytes)

    await cache_set(key, faq_data, ttl=FAQ_CACHE_TTL_SECONDS)
    return faq_data
