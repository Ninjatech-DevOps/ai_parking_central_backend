"""
Scope Resolver — resolves a user's scopes to a set of location_ids.

Cascading logic:
  STATE scope    → all locations in all cities/areas in that state
  CITY scope     → all locations in all areas in that city
  AREA scope     → all locations in that area
  LOCATION scope → just that location
  ZONE scope     → locations that contain that zone

Super Admin → returns None (meaning ALL locations, no filter)
"""

import uuid
from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.constants import ScopeType, UserRole as UserRoleEnum
from src.app.models.area import Area
from src.app.models.city import City
from src.app.models.location import Location
from src.app.models.user_role import UserRole
from src.app.models.user_scope import UserScope
from src.app.models.role import Role


class ScopeResolver:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_super_admin(self, user_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        roles = [row[0] for row in result.all()]
        return UserRoleEnum.SUPER_ADMIN.value in roles

    async def resolve_location_ids(
        self, user_id: uuid.UUID
    ) -> Optional[Set[uuid.UUID]]:
        """
        Returns set of location_ids this user can access.
        Returns None for Super Admin (no filtering needed).
        """
        if await self.is_super_admin(user_id):
            return None

        result = await self.db.execute(
            select(UserScope).where(UserScope.user_id == user_id)
        )
        scopes = result.scalars().all()

        if not scopes:
            return set()

        location_ids: Set[uuid.UUID] = set()

        for scope in scopes:
            ids = await self._resolve_scope(scope.scope_type, scope.scope_id)
            location_ids.update(ids)

        return location_ids

    async def _resolve_scope(
        self, scope_type: str, scope_id: uuid.UUID
    ) -> Set[uuid.UUID]:
        if scope_type == ScopeType.LOCATION:
            return {scope_id}

        elif scope_type == ScopeType.AREA:
            result = await self.db.execute(
                select(Location.id).where(Location.area_id == scope_id)
            )
            return {row[0] for row in result.all()}

        elif scope_type == ScopeType.CITY:
            # Use denormalized city_id on Location (not Area join — area_id can be NULL)
            result = await self.db.execute(
                select(Location.id).where(Location.city_id == scope_id)
            )
            return {row[0] for row in result.all()}

        elif scope_type == ScopeType.STATE:
            # Use denormalized city_id on Location → City.state_id
            result = await self.db.execute(
                select(Location.id)
                .join(City, City.id == Location.city_id)
                .where(City.state_id == scope_id)
            )
            return {row[0] for row in result.all()}

        elif scope_type == ScopeType.ZONE:
            result = await self.db.execute(
                select(Location.id)
                .where(Location.id.in_(
                    select(Location.id)
                    .join(Location.floors)
                    .where(Location.floors.any(
                        zones=scope_id
                    ))
                ))
            )
            # Simpler: just get the location that contains this zone
            from src.app.models.floor import Floor
            from src.app.models.zone import Zone
            result = await self.db.execute(
                select(Location.id)
                .join(Floor, Floor.location_id == Location.id)
                .join(Zone, Zone.floor_id == Floor.id)
                .where(Zone.id == scope_id)
            )
            return {row[0] for row in result.all()}

        return set()

    async def resolve_users_for_location(
        self, location_id: uuid.UUID
    ) -> Set[uuid.UUID]:
        """
        Reverse resolution: given a location_id, find ALL users whose scope
        includes this location. Used for cascading alert notifications.
        """
        user_ids: Set[uuid.UUID] = set()

        # Super Admins always get notified
        result = await self.db.execute(
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == UserRoleEnum.SUPER_ADMIN.value)
        )
        user_ids.update(row[0] for row in result.all())

        # Get location's full hierarchy
        result = await self.db.execute(
            select(Location.id, Area.id, Area.city_id, City.state_id)
            .join(Area, Area.id == Location.area_id)
            .join(City, City.id == Area.city_id)
            .where(Location.id == location_id)
        )
        row = result.first()
        if not row:
            return user_ids

        loc_id, area_id, city_id, state_id = row

        # Users scoped to this location, area, city, or state
        result = await self.db.execute(
            select(UserScope.user_id).where(
                (
                    (UserScope.scope_type == ScopeType.LOCATION)
                    & (UserScope.scope_id == loc_id)
                )
                | (
                    (UserScope.scope_type == ScopeType.AREA)
                    & (UserScope.scope_id == area_id)
                )
                | (
                    (UserScope.scope_type == ScopeType.CITY)
                    & (UserScope.scope_id == city_id)
                )
                | (
                    (UserScope.scope_type == ScopeType.STATE)
                    & (UserScope.scope_id == state_id)
                )
            )
        )
        user_ids.update(r[0] for r in result.all())

        return user_ids
