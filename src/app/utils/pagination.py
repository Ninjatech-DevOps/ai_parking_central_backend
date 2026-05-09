import math

from src.app.core.config import settings


def get_pagination_params(page: int = 1, page_size: int = None) -> tuple:
    if page_size is None:
        page_size = settings.DEFAULT_PAGE_SIZE
    page_size = min(page_size, settings.MAX_PAGE_SIZE)
    page = max(page, 1)
    skip = (page - 1) * page_size
    return skip, page_size


def build_paginated_response(items, total: int, page: int, page_size: int) -> dict:
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
