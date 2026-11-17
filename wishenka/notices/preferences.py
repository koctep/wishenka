"""Repository and service for global and per-wishlist notification preferences."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger("wishenka.notices.preferences")

PreferenceSource = Literal["override", "global", "default"]
WishlistRole = Literal["owner", "member", "favorite"]

GLOBAL_NOTIFICATION_DEFAULTS: dict[str, bool] = {
    "wishlist_changes": True,
    "reservation_changes": False,
    "gift_received": True,
    "reminders": True,
    "birthday_reminders": True,
}

WISHLIST_NOTIFICATION_CATEGORIES: tuple[str, ...] = (
    "wishlist_changes",
    "reservation_changes",
    "gift_received",
    "reminders",
)


@dataclass(frozen=True)
class EffectiveSetting:
    """Resolved effective notification status and its origin."""

    enabled: bool
    source: PreferenceSource

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-compatible dict."""
        return {"enabled": self.enabled, "source": self.source}


@dataclass(frozen=True)
class WishlistNotificationSummary:
    """Per-wishlist notification overrides and effective resolved preferences."""

    id: int
    title: str
    role: WishlistRole
    overrides: dict[str, bool | None]
    effective: dict[str, EffectiveSetting]

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-compatible dict."""
        return {
            "id": self.id,
            "title": self.title,
            "role": self.role,
            "overrides": dict(self.overrides),
            "effective": {k: v.to_dict() for k, v in self.effective.items()},
        }


def _resolve_effective(
    category: str,
    *,
    override: bool | None,
    global_rows: dict[str, bool],
) -> EffectiveSetting:
    if override is not None:
        return EffectiveSetting(enabled=override, source="override")
    if category in global_rows:
        return EffectiveSetting(enabled=global_rows[category], source="global")
    return EffectiveSetting(enabled=GLOBAL_NOTIFICATION_DEFAULTS[category], source="default")


class NotificationPreferencesStore:
    """Async SQLite repository for user_notification_settings & wl_list_notification_settings."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @staticmethod
    async def _fetch_global_rows(conn: AsyncConnection, telegram_id: int) -> dict[str, bool]:
        rows = (
            await conn.execute(
                text(
                    "SELECT event_type, enabled FROM user_notification_settings "
                    "WHERE user_id = :uid"
                ),
                {"uid": telegram_id},
            )
        ).all()
        return {
            str(row.event_type): bool(row.enabled)
            for row in rows
            if str(row.event_type) in GLOBAL_NOTIFICATION_DEFAULTS
        }

    @staticmethod
    async def _fetch_accessible_wishlist_meta(
        conn: AsyncConnection, telegram_id: int, wishlist_id: int
    ) -> tuple[int, str, WishlistRole] | None:
        row = (
            await conn.execute(
                text(
                    "SELECT l.id, l.title, l.owner_id, "
                    "EXISTS(SELECT 1 FROM wl_members m "
                    "WHERE m.wishlist_id = l.id AND m.user_id = :uid) AS is_member, "
                    "EXISTS(SELECT 1 FROM wl_favorites f "
                    "WHERE f.wishlist_id = l.id AND f.user_id = :uid) AS is_favorite "
                    "FROM wl_lists l "
                    "WHERE l.id = :wl_id AND l.status IN ('active', 'archived') "
                    "AND (l.owner_id = :uid "
                    "OR EXISTS(SELECT 1 FROM wl_members m "
                    "WHERE m.wishlist_id = l.id AND m.user_id = :uid) "
                    "OR EXISTS(SELECT 1 FROM wl_favorites f "
                    "WHERE f.wishlist_id = l.id AND f.user_id = :uid))"
                ),
                {"uid": telegram_id, "wl_id": wishlist_id},
            )
        ).first()
        if row is None:
            return None
        role: WishlistRole = (
            "owner"
            if int(row.owner_id) == telegram_id
            else ("member" if bool(row.is_member) else "favorite")
        )
        return int(row.id), str(row.title), role

    @staticmethod
    async def _build_wishlist_summary(
        conn: AsyncConnection,
        telegram_id: int,
        wishlist_id: int,
        title: str,
        role: WishlistRole,
        global_rows: dict[str, bool],
    ) -> WishlistNotificationSummary:
        override_rows = (
            await conn.execute(
                text(
                    "SELECT event_type, enabled FROM wl_list_notification_settings "
                    "WHERE user_id = :uid AND wishlist_id = :wl_id"
                ),
                {"uid": telegram_id, "wl_id": wishlist_id},
            )
        ).all()
        raw_overrides: dict[str, bool] = {str(r.event_type): bool(r.enabled) for r in override_rows}
        overrides: dict[str, bool | None] = {
            cat: raw_overrides.get(cat) for cat in WISHLIST_NOTIFICATION_CATEGORIES
        }
        effective: dict[str, EffectiveSetting] = {
            cat: _resolve_effective(cat, override=overrides[cat], global_rows=global_rows)
            for cat in WISHLIST_NOTIFICATION_CATEGORIES
        }
        return WishlistNotificationSummary(
            id=wishlist_id,
            title=title,
            role=role,
            overrides=overrides,
            effective=effective,
        )

    async def get_global_settings(self, telegram_id: int) -> dict[str, bool]:
        """Return merged global notification settings (stored values + defaults)."""
        async with self.engine.connect() as conn:
            stored = await self._fetch_global_rows(conn, telegram_id)
        return {
            cat: stored.get(cat, default) for cat, default in GLOBAL_NOTIFICATION_DEFAULTS.items()
        }

    async def update_global_settings(
        self, telegram_id: int, settings: dict[str, object]
    ) -> dict[str, bool]:
        """Validate and upsert global notification settings for the user."""
        if not settings:
            raise ValueError("Settings payload cannot be empty")
        validated: dict[str, bool] = {}
        for key, value in settings.items():
            if key not in GLOBAL_NOTIFICATION_DEFAULTS:
                raise ValueError(f"Unsupported notification category: {key}")
            if not isinstance(value, bool):
                raise ValueError(f"Notification setting for {key} must be a boolean")
            validated[key] = value

        now = int(time.time())
        async with self.engine.begin() as conn:
            for event_type, enabled in validated.items():
                await conn.execute(
                    text(
                        "INSERT INTO user_notification_settings "
                        "(user_id, event_type, enabled, updated_at) "
                        "VALUES (:uid, :event_type, :enabled, :updated_at) "
                        "ON CONFLICT(user_id, event_type) DO UPDATE SET "
                        "enabled = excluded.enabled, updated_at = excluded.updated_at"
                    ),
                    {
                        "uid": telegram_id,
                        "event_type": event_type,
                        "enabled": 1 if enabled else 0,
                        "updated_at": now,
                    },
                )
            stored = await self._fetch_global_rows(conn, telegram_id)
        logger.info(
            "Global notification preferences updated",
            extra={
                "event": "notification_global_updated",
                "updated_count": len(validated),
                "categories": ",".join(sorted(validated)),
            },
        )
        return {
            cat: stored.get(cat, default) for cat, default in GLOBAL_NOTIFICATION_DEFAULTS.items()
        }

    async def list_accessible_wishlists_with_preferences(
        self, telegram_id: int
    ) -> list[WishlistNotificationSummary]:
        """Return all accessible non-deleted wishlists with overrides and effective settings."""
        async with self.engine.connect() as conn:
            global_rows = await self._fetch_global_rows(conn, telegram_id)
            wl_rows = (
                await conn.execute(
                    text(
                        "SELECT l.id, l.title, l.owner_id, "
                        "EXISTS(SELECT 1 FROM wl_members m "
                        "WHERE m.wishlist_id = l.id AND m.user_id = :uid) AS is_member "
                        "FROM wl_lists l "
                        "WHERE l.status IN ('active', 'archived') "
                        "AND (l.owner_id = :uid "
                        "OR EXISTS(SELECT 1 FROM wl_members m "
                        "WHERE m.wishlist_id = l.id AND m.user_id = :uid) "
                        "OR EXISTS(SELECT 1 FROM wl_favorites f "
                        "WHERE f.wishlist_id = l.id AND f.user_id = :uid)) "
                        "ORDER BY l.id ASC"
                    ),
                    {"uid": telegram_id},
                )
            ).all()
            summaries: list[WishlistNotificationSummary] = []
            for row in wl_rows:
                role: WishlistRole = (
                    "owner"
                    if int(row.owner_id) == telegram_id
                    else ("member" if bool(row.is_member) else "favorite")
                )
                summaries.append(
                    await self._build_wishlist_summary(
                        conn,
                        telegram_id,
                        int(row.id),
                        str(row.title),
                        role,
                        global_rows,
                    )
                )
            return summaries

    async def get_wishlist_preferences(
        self, telegram_id: int, wishlist_id: int
    ) -> WishlistNotificationSummary | None:
        """Return overrides and effective settings for one accessible wishlist, or None."""
        async with self.engine.connect() as conn:
            meta = await self._fetch_accessible_wishlist_meta(conn, telegram_id, wishlist_id)
            if meta is None:
                return None
            wl_id, title, role = meta
            global_rows = await self._fetch_global_rows(conn, telegram_id)
            return await self._build_wishlist_summary(
                conn, telegram_id, wl_id, title, role, global_rows
            )

    async def update_wishlist_overrides(
        self,
        telegram_id: int,
        wishlist_id: int,
        overrides: dict[str, object],
    ) -> WishlistNotificationSummary | None:
        """Update per-wishlist notification overrides; None clears override to inherit global."""
        if not overrides:
            raise ValueError("Overrides payload cannot be empty")
        validated: dict[str, bool | None] = {}
        for key, value in overrides.items():
            if key not in WISHLIST_NOTIFICATION_CATEGORIES:
                raise ValueError(f"Unsupported wishlist notification category: {key}")
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"Override for {key} must be a boolean or null")
            validated[key] = value

        now = int(time.time())
        async with self.engine.begin() as conn:
            meta = await self._fetch_accessible_wishlist_meta(conn, telegram_id, wishlist_id)
            if meta is None:
                return None
            wl_id, title, role = meta
            for event_type, value in validated.items():
                if value is None:
                    await conn.execute(
                        text(
                            "DELETE FROM wl_list_notification_settings "
                            "WHERE user_id = :uid AND wishlist_id = :wl_id "
                            "AND event_type = :event_type"
                        ),
                        {"uid": telegram_id, "wl_id": wl_id, "event_type": event_type},
                    )
                else:
                    await conn.execute(
                        text(
                            "INSERT INTO wl_list_notification_settings "
                            "(user_id, wishlist_id, event_type, enabled, updated_at) "
                            "VALUES (:uid, :wl_id, :event_type, :enabled, :updated_at) "
                            "ON CONFLICT(user_id, wishlist_id, event_type) DO UPDATE SET "
                            "enabled = excluded.enabled, updated_at = excluded.updated_at"
                        ),
                        {
                            "uid": telegram_id,
                            "wl_id": wl_id,
                            "event_type": event_type,
                            "enabled": 1 if value else 0,
                            "updated_at": now,
                        },
                    )
            global_rows = await self._fetch_global_rows(conn, telegram_id)
            summary = await self._build_wishlist_summary(
                conn, telegram_id, wl_id, title, role, global_rows
            )
        logger.info(
            "Wishlist notification overrides updated",
            extra={
                "event": "notification_wishlist_updated",
                "wishlist_id": wl_id,
                "role": role,
                "updated_count": len(validated),
                "cleared_count": sum(1 for v in validated.values() if v is None),
            },
        )
        return summary
