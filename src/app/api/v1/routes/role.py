from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.api.deps import PermissionChecker
from src.app.core.constants import Permission
from src.app.db.session import get_db
from src.app.repositories.role import RoleRepository
from src.app.schemas.role import RoleResponse
from src.app.schemas.base import PaginatedResponse

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("", response_model=PaginatedResponse[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(PermissionChecker(Permission.USERS_VIEW)),
):
    repo = RoleRepository(db)
    items = await repo.get_all(limit=50)
    total = await repo.count()
    return {"items": items, "total": total, "page": 1, "page_size": 50, "total_pages": 1}
