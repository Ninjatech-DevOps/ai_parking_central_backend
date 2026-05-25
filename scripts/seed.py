"""
Seed script for initial roles, permissions, and Super Admin user.
Runs on every startup but is idempotent — skips if data already exists.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.core.constants import Permission, UserRole as UserRoleEnum
from src.app.core.security import hash_password
from src.app.db.session import async_session_factory

# Import all models to register them
import src.app.models  # noqa: F401

from src.app.models.permission import Permission as PermissionModel
from src.app.models.role import Role
from src.app.models.role_permission import RolePermission
from src.app.models.user import User
from src.app.models.user_role import UserRole

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

# All permissions in the system — standard CRUD + special actions per resource
ALL_PERMISSIONS = [
    ("devices", "view"),
    ("devices", "create"),
    ("devices", "edit"),
    ("devices", "delete"),
    ("devices", "restart"),
    ("devices", "update"),       # Firmware/OTA push
    ("devices", "shell"),
    ("locations", "view"),
    ("locations", "create"),
    ("locations", "edit"),
    ("locations", "delete"),
    ("slots", "view"),
    ("slots", "create"),
    ("slots", "edit"),
    ("slots", "delete"),
    ("users", "view"),
    ("users", "create"),
    ("users", "edit"),
    ("users", "delete"),
    ("roles", "view"),
    ("roles", "create"),
    ("roles", "edit"),
    ("roles", "delete"),
    ("alerts", "view"),
    ("alerts", "create"),
    ("alerts", "edit"),
    ("alerts", "delete"),
    ("alerts", "acknowledge"),
    ("alerts", "configure"),
    ("reports", "view"),
    ("reports", "export"),
    ("notifications", "view"),
    ("notifications", "create"),
    ("notifications", "edit"),
    ("notifications", "delete"),
    ("notifications", "configure"),
    ("ota", "view"),
    ("ota", "deploy"),
    ("ota", "rollback"),
    ("shared_links", "view"),
    ("shared_links", "create"),
    ("shared_links", "edit"),
    ("shared_links", "delete"),
]

# Only SUPER_ADMIN is seeded as a system role.
# All other roles are created dynamically via the Roles page.
ROLE_PERMISSIONS = {
    UserRoleEnum.SUPER_ADMIN: [f"{r}:{a}" for r, a in ALL_PERMISSIONS],  # all
}

# Default Super Admin credentials (from env or fallback)
ADMIN_EMAIL = "admin@aiparking.com"
ADMIN_NAME = "Super Admin"
ADMIN_PASSWORD = "Admin@123"


async def seed_permissions(db: AsyncSession) -> dict:
    """Create all permissions if they don't exist. Returns {key: id} map."""
    perm_map = {}

    for resource, action in ALL_PERMISSIONS:
        key = f"{resource}:{action}"
        result = await db.execute(
            select(PermissionModel).where(
                PermissionModel.resource == resource,
                PermissionModel.action == action,
            )
        )
        perm = result.scalars().first()

        if not perm:
            perm = PermissionModel(resource=resource, action=action)
            db.add(perm)
            await db.flush()
            logger.info("Created permission: %s", key)

        perm_map[key] = perm.id

    return perm_map


async def seed_roles(db: AsyncSession, perm_map: dict) -> dict:
    """
    Create or update system roles with their permissions.
    - New roles are created.
    - Existing system roles get their permissions synced (missing ones added).
    Returns {name: id} map.
    """
    role_map = {}

    for role_enum, perm_keys in ROLE_PERMISSIONS.items():
        result = await db.execute(
            select(Role).where(Role.name == role_enum.value)
        )
        role = result.scalars().first()

        if not role:
            role = Role(
                name=role_enum.value,
                description=f"{role_enum.value.replace('_', ' ').title()} role",
                is_system_role=True,
            )
            db.add(role)
            await db.flush()
            logger.info("Created role: %s", role_enum.value)

        # Sync permissions — get existing, add any missing
        result = await db.execute(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role.id
            )
        )
        existing_perm_ids = {row[0] for row in result.all()}

        added = 0
        for perm_key in perm_keys:
            perm_id = perm_map.get(perm_key)
            if perm_id and perm_id not in existing_perm_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm_id))
                added += 1

        if added:
            await db.flush()
            logger.info("Added %d new permissions to %s", added, role_enum.value)

        role_map[role_enum.value] = role.id

    return role_map


async def seed_admin_user(db: AsyncSession, role_map: dict):
    """Create the default Super Admin user if not exists."""
    result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
    user = result.scalars().first()

    if user:
        logger.info("Admin user already exists: %s", ADMIN_EMAIL)
        return

    user = User(
        email=ADMIN_EMAIL,
        name=ADMIN_NAME,
        password_hash=hash_password(ADMIN_PASSWORD),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Assign Super Admin role
    admin_role_id = role_map.get(UserRoleEnum.SUPER_ADMIN.value)
    if admin_role_id:
        ur = UserRole(user_id=user.id, role_id=admin_role_id)
        db.add(ur)
        await db.flush()

    logger.info("Created admin user: %s (password: %s)", ADMIN_EMAIL, ADMIN_PASSWORD)


async def seed_alert_rules(db):
    """Create default alert rules."""
    from src.app.models.alert_rule import AlertRule
    from src.app.core.constants import AlertTriggerType, AlertSeverity

    default_rules = [
        {
            "name": "Device Offline",
            "trigger_type": AlertTriggerType.DEVICE_OFFLINE,
            "severity": AlertSeverity.CRITICAL,
            "condition": "No heartbeat received within threshold",
        },
        {
            "name": "Camera Failure",
            "trigger_type": AlertTriggerType.CAMERA_FAILURE,
            "severity": AlertSeverity.CRITICAL,
            "condition": "Camera status reported as FAILED",
        },
        {
            "name": "High Occupancy",
            "trigger_type": AlertTriggerType.HIGH_OCCUPANCY,
            "severity": AlertSeverity.HIGH,
            "condition": "Location occupancy above 90%",
        },
        {
            "name": "Device High Temperature",
            "trigger_type": AlertTriggerType.DEVICE_HIGH_TEMP,
            "severity": AlertSeverity.MEDIUM,
            "condition": "Device temperature above 70C",
        },
    ]

    for rule_data in default_rules:
        result = await db.execute(
            select(AlertRule).where(AlertRule.name == rule_data["name"])
        )
        if not result.scalars().first():
            rule = AlertRule(**rule_data, is_active=True)
            db.add(rule)
            logger.info("Created alert rule: %s", rule_data["name"])

    await db.flush()


async def run_seed():
    async with async_session_factory() as db:
        try:
            logger.info("Starting seed...")

            perm_map = await seed_permissions(db)
            logger.info("Permissions: %d total", len(perm_map))

            role_map = await seed_roles(db, perm_map)
            logger.info("Roles: %d total", len(role_map))

            await seed_admin_user(db, role_map)
            await seed_alert_rules(db)

            await db.commit()
            logger.info("Seed completed successfully")

        except Exception:
            await db.rollback()
            logger.exception("Seed failed")
            raise


if __name__ == "__main__":
    asyncio.run(run_seed())
