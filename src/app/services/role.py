import uuid
from typing import Any, Dict, List, Optional

from src.app.exceptions.base import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from src.app.repositories.role import RoleRepository
from src.app.repositories.role_permission import RolePermissionRepository
from src.app.repositories.permission import PermissionRepository
from src.app.repositories.user_role import UserRoleRepository


class RoleService:
    def __init__(
        self,
        role_repo: RoleRepository,
        role_perm_repo: RolePermissionRepository,
        permission_repo: PermissionRepository,
        user_role_repo: UserRoleRepository,
    ):
        self.role_repo = role_repo
        self.role_perm_repo = role_perm_repo
        self.permission_repo = permission_repo
        self.user_role_repo = user_role_repo

    async def create_role(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a custom role with optional permission assignments."""
        existing = await self.role_repo.get_by_name(data["name"])
        if existing:
            raise ConflictException(detail="Role name already exists")

        permission_ids = data.pop("permission_ids", None) or []

        # Custom roles are never system roles
        role = await self.role_repo.create({
            "name": data["name"],
            "description": data.get("description"),
            "is_system_role": False,
        })

        # Assign permissions
        for perm_id in permission_ids:
            await self.role_perm_repo.create(
                {"role_id": role.id, "permission_id": perm_id}
            )

        return await self._build_role_response(role.id)

    async def get_role(self, role_id: uuid.UUID) -> Dict[str, Any]:
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundException(detail="Role not found")
        return await self._build_role_response(role_id)

    async def get_roles(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        roles = await self.role_repo.get_all(skip=skip, limit=limit)
        return [await self._build_role_response(r.id) for r in roles]

    async def count_roles(self) -> int:
        return await self.role_repo.count()

    async def update_role(
        self, role_id: uuid.UUID, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundException(detail="Role not found")

        if role.is_system_role:
            raise BadRequestException(detail="Cannot modify system roles")

        # Check name uniqueness if changing name
        new_name = data.get("name")
        if new_name and new_name != role.name:
            existing = await self.role_repo.get_by_name(new_name)
            if existing:
                raise ConflictException(detail="Role name already exists")

        # Handle permission_ids: replace all role permissions
        permission_ids = data.pop("permission_ids", None)
        if permission_ids is not None:
            await self.role_perm_repo.delete_by_role_id(role_id)
            for perm_id in permission_ids:
                await self.role_perm_repo.create(
                    {"role_id": role_id, "permission_id": perm_id}
                )

        # Update role fields (name, description)
        update_fields = {}
        if "name" in data and data["name"] is not None:
            update_fields["name"] = data["name"]
        if "description" in data and data["description"] is not None:
            update_fields["description"] = data["description"]

        if update_fields:
            await self.role_repo.update(role_id, update_fields)

        return await self._build_role_response(role_id)

    async def delete_role(self, role_id: uuid.UUID) -> None:
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundException(detail="Role not found")

        if role.is_system_role:
            raise BadRequestException(detail="Cannot delete system roles")

        # Check if any users are assigned this role
        user_roles = await self.user_role_repo.get_by_role_id(role_id)
        if user_roles:
            raise BadRequestException(
                detail=f"Cannot delete role — {len(user_roles)} user(s) assigned"
            )

        # Remove permissions, then delete role
        await self.role_perm_repo.delete_by_role_id(role_id)
        await self.role_repo.delete(role_id)

    async def get_all_permissions(self) -> List[Any]:
        """Return all available permissions in the system."""
        return await self.permission_repo.get_all(limit=100)

    async def _build_role_response(self, role_id: uuid.UUID) -> Dict[str, Any]:
        """Build role dict with permissions list and user count."""
        role = await self.role_repo.get_by_id(role_id)
        role_perms = await self.role_perm_repo.get_by_role_id(role_id)
        user_roles = await self.user_role_repo.get_by_role_id(role_id)

        permissions = []
        for rp in role_perms:
            perm = rp.permission
            if perm:
                permissions.append({
                    "id": perm.id,
                    "resource": perm.resource,
                    "action": perm.action,
                    "created_at": perm.created_at,
                    "updated_at": perm.updated_at,
                })

        return {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "is_system_role": role.is_system_role,
            "permissions": permissions,
            "user_count": len(user_roles),
            "created_at": role.created_at,
            "updated_at": role.updated_at,
        }
