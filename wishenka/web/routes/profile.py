"""User profile settings page and explicit locale update endpoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from aiogram import Bot
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from wishenka.auth.dependencies import get_current_user, get_settings, get_user_store
from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import delete_session_cookie
from wishenka.bot.i18n import sync_user_bot_commands
from wishenka.config import Settings
from wishenka.i18n import DEFAULT_LOCALE, SupportedLocale, t, validate_locale
from wishenka.i18n.dependencies import LocaleDep
from wishenka.notices.preferences import (
    WISHLIST_NOTIFICATION_CATEGORIES,
    NotificationPreferencesStore,
)
from wishenka.notices.sender import PLACEHOLDER_TOKEN
from wishenka.users.models import UserRecord
from wishenka.users.store import UserNotFoundError, UserStore, UserStoreBusyError
from wishenka.web.templates import templates
from wishenka.wishlists.deletion import AccountDeletionService
from wishenka.wishlists.store import WishlistStore

router = APIRouter(tags=["profile"])
logger = logging.getLogger("wishenka.web.profile")
bot_i18n_logger = logging.getLogger("wishenka.bot.i18n")


async def _find_active_chat_id(request: Request, user_store: UserStore, user_id: int) -> int | None:
    """Look up the active private Telegram chat_id for an internal user id, if available."""
    wishlist_store = getattr(request.app.state, "wishlist_store", None)
    engine = wishlist_store.engine if wishlist_store is not None else user_store.engine
    async with engine.connect() as conn:
        has_table = await conn.scalar(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bot_destinations'")
        )
        if not has_table:
            return None
        row = (
            await conn.execute(
                text("SELECT chat_id FROM bot_destinations WHERE user_id = :uid AND active = 1"),
                {"uid": user_id},
            )
        ).first()
        return int(row[0]) if row is not None else None


async def _sync_bot_commands_best_effort(
    settings: Settings,
    *,
    user_id: int,
    chat_id: int,
    locale: SupportedLocale,
    custom_hook: Any = None,
) -> None:
    """Trigger timeout-bounded per-chat Telegram command menu sync without failing the caller."""
    try:
        if callable(custom_hook):
            await asyncio.wait_for(custom_hook(chat_id, locale), timeout=2.0)
            return

        token = settings.bot_token
        if not token or token == PLACEHOLDER_TOKEN:
            return

        bot = Bot(token=token)
        try:
            await sync_user_bot_commands(bot, chat_id, locale, user_id=user_id, timeout_seconds=2.0)
        finally:
            await bot.session.close()
    except Exception as err:
        bot_i18n_logger.warning(
            "Failed to sync bot commands for locale %s",
            locale,
            extra={
                "event": "bot_commands_locale_sync_failed",
                "user_id": user_id,
                "target_locale": locale,
                "error_type": type(err).__name__,
            },
        )


async def _extract_requested_locale(request: Request) -> object:
    """Read requested locale from JSON body or form-encoded payload."""
    content_type = request.headers.get("content-type", "").lower()
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        return form.get("locale")
    try:
        payload: Any = await request.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get("locale")


def _get_preferences_store(request: Request, user_store: UserStore) -> NotificationPreferencesStore:
    wishlist_store = getattr(request.app.state, "wishlist_store", None)
    engine = wishlist_store.engine if wishlist_store is not None else user_store.engine
    return NotificationPreferencesStore(engine)


def _get_wishlist_store(request: Request) -> WishlistStore:
    store = getattr(request.app.state, "wishlist_store", None)
    if isinstance(store, WishlistStore):
        return store
    settings = getattr(request.app.state, "settings", None) or Settings()
    return WishlistStore(settings.database_url)


def _serialize_birthdate(record: UserRecord | None) -> dict[str, object]:
    if record is None:
        return {"day": None, "month": None, "year": None, "source": "auto"}
    return {
        "day": record.birth_day,
        "month": record.birth_month,
        "year": record.birth_year,
        "source": record.birthdate_source,
    }


async def _read_json_dict(request: Request, locale: SupportedLocale) -> dict[str, Any]:
    try:
        payload: Any = await request.json()
    except Exception as err:
        logger.warning(
            "Rejected malformed JSON payload on profile endpoint",
            extra={
                "event": "profile_malformed_json",
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_notification_setting", locale),
        ) from err
    if not isinstance(payload, dict):
        logger.warning(
            "Rejected non-object JSON payload on profile endpoint",
            extra={
                "event": "profile_malformed_json",
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_notification_setting", locale),
        )
    return payload


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> HTMLResponse:
    """Render authenticated Mini App profile settings page with language & preferences."""
    record = await user_store.get_by_telegram_id(current_user.telegram_id)
    locale_source = record.locale_source if record is not None else "auto"
    prefs_store = _get_preferences_store(request, user_store)
    global_notifications = await prefs_store.get_global_settings(current_user.telegram_id)
    wishlists = await prefs_store.list_accessible_wishlists_with_preferences(
        current_user.telegram_id
    )
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "viewer_identified": True,
            "locale": locale,
            "locale_source": locale_source,
            "birthdate": _serialize_birthdate(record),
            "global_notifications": global_notifications,
            "birthday_reminders": global_notifications["birthday_reminders"],
            "wishlist_categories": WISHLIST_NOTIFICATION_CATEGORIES,
            "wishlists": [wl.to_dict() for wl in wishlists],
        },
    )


@router.patch("/api/profile/locale")
async def update_profile_locale(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> JSONResponse:
    """Persist an explicit RU/EN locale choice and trigger HTMX refresh + bot sync."""
    raw_locale = await _extract_requested_locale(request)
    try:
        target_locale = validate_locale(raw_locale)
    except ValueError as err:
        logger.warning(
            "Rejected invalid locale update request",
            extra={
                "event": "locale_invalid_request",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_locale", DEFAULT_LOCALE),
        ) from err

    try:
        updated = await user_store.set_locale(current_user.telegram_id, target_locale)
    except UserStoreBusyError as err:
        logger.warning(
            "Locale update busy while persisting user",
            extra={
                "event": "locale_user_store_busy",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_503_SERVICE_UNAVAILABLE,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        ) from err
    except UserNotFoundError as err:
        logger.warning(
            "Locale update failed: user profile not found",
            extra={
                "event": "locale_user_not_found",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_404_NOT_FOUND,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        ) from err

    chat_id = await _find_active_chat_id(request, user_store, updated.id)
    if chat_id is not None:
        custom_hook = getattr(request.app.state, "bot_command_sync", None)
        background_tasks.add_task(
            _sync_bot_commands_best_effort,
            settings,
            user_id=updated.id,
            chat_id=chat_id,
            locale=updated.locale,
            custom_hook=custom_hook,
        )

    return JSONResponse(
        content={"locale": updated.locale, "locale_source": updated.locale_source},
        headers={"HX-Refresh": "true"},
    )


@router.get("/api/profile/preferences")
async def get_profile_preferences(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> JSONResponse:
    """Return user's locale, birthdate, global notifications, and per-wishlist preferences."""
    record = await user_store.get_by_telegram_id(current_user.telegram_id)
    prefs_store = _get_preferences_store(request, user_store)
    global_notifications = await prefs_store.get_global_settings(current_user.telegram_id)
    wishlists = await prefs_store.list_accessible_wishlists_with_preferences(
        current_user.telegram_id
    )
    return JSONResponse(
        content={
            "locale": locale,
            "locale_source": record.locale_source if record is not None else "auto",
            "birthdate": _serialize_birthdate(record),
            "birthday_reminders": global_notifications["birthday_reminders"],
            "global_notifications": global_notifications,
            "wishlists": [wl.to_dict() for wl in wishlists],
        }
    )


@router.patch("/api/profile/birthdate")
async def update_profile_birthdate(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> JSONResponse:
    """Manually set or clear user's birthdate with birthdate_source='explicit'."""
    payload = await _read_json_dict(request, locale)
    clear_flag = payload.get("clear") is True
    try:
        if await user_store.get_by_telegram_id(current_user.telegram_id) is None:
            await user_store.upsert_user(
                TelegramUser(
                    id=current_user.telegram_id,
                    first_name=current_user.first_name or "User",
                    username=current_user.username,
                )
            )
        if clear_flag:
            updated = await user_store.clear_birthdate(current_user.telegram_id)
        else:
            day = payload.get("day")
            month = payload.get("month")
            year = payload.get("year")
            if day is None or month is None:
                raise ValueError("Day and month are required")
            updated = await user_store.set_birthdate(
                current_user.telegram_id,
                day=day,
                month=month,
                year=year,
            )
    except ValueError as err:
        logger.warning(
            "Rejected invalid birthdate update request",
            extra={
                "event": "birthdate_invalid_request",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_birthdate", locale),
        ) from err
    except UserStoreBusyError as err:
        logger.warning(
            "Birthdate update busy while persisting user",
            extra={
                "event": "birthdate_user_store_busy",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_503_SERVICE_UNAVAILABLE,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        ) from err
    except UserNotFoundError as err:
        logger.warning(
            "Birthdate update failed: user profile not found",
            extra={
                "event": "birthdate_user_not_found",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_404_NOT_FOUND,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        ) from err
    return JSONResponse(content=_serialize_birthdate(updated))


@router.put("/api/profile/notifications/global")
async def update_global_notifications(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> JSONResponse:
    """Update global notification toggles for the authenticated user."""
    payload = await _read_json_dict(request, locale)
    raw_settings = payload.get("settings")
    if not isinstance(raw_settings, dict):
        logger.warning(
            "Rejected invalid global notification settings payload",
            extra={
                "event": "notification_global_invalid_request",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_notification_setting", locale),
        )
    prefs_store = _get_preferences_store(request, user_store)
    try:
        updated = await prefs_store.update_global_settings(current_user.telegram_id, raw_settings)
    except ValueError as err:
        logger.warning(
            "Rejected unsupported global notification settings",
            extra={
                "event": "notification_global_invalid_request",
                "user_id": current_user.user_id,
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_notification_setting", locale),
        ) from err
    return JSONResponse(
        content={
            "global_notifications": updated,
            "birthday_reminders": updated["birthday_reminders"],
        }
    )


@router.get("/api/profile/notifications/wishlists/{wishlist_id}")
async def get_wishlist_notifications(
    wishlist_id: int,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> JSONResponse:
    """Return per-wishlist overrides and effective settings for an accessible wishlist."""
    prefs_store = _get_preferences_store(request, user_store)
    summary = await prefs_store.get_wishlist_preferences(current_user.telegram_id, wishlist_id)
    if summary is None:
        logger.warning(
            "Wishlist notification preferences not found",
            extra={
                "event": "notification_wishlist_not_found",
                "user_id": current_user.user_id,
                "wishlist_id": wishlist_id,
                "status_code": status.HTTP_404_NOT_FOUND,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("settings.wishlist_not_found", locale),
        )
    return JSONResponse(content=summary.to_dict())


@router.put("/api/profile/notifications/wishlists/{wishlist_id}")
async def update_wishlist_notifications(
    wishlist_id: int,
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> JSONResponse:
    """Update or reset per-wishlist notification overrides for an accessible wishlist."""
    payload = await _read_json_dict(request, locale)
    raw_overrides = payload.get("overrides")
    if not isinstance(raw_overrides, dict):
        logger.warning(
            "Rejected invalid wishlist notification overrides payload",
            extra={
                "event": "notification_wishlist_invalid_request",
                "user_id": current_user.user_id,
                "wishlist_id": wishlist_id,
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_notification_setting", locale),
        )
    prefs_store = _get_preferences_store(request, user_store)
    try:
        summary = await prefs_store.update_wishlist_overrides(
            current_user.telegram_id, wishlist_id, raw_overrides
        )
    except ValueError as err:
        logger.warning(
            "Rejected unsupported wishlist notification overrides",
            extra={
                "event": "notification_wishlist_invalid_request",
                "user_id": current_user.user_id,
                "wishlist_id": wishlist_id,
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.invalid_notification_setting", locale),
        ) from err
    if summary is None:
        logger.warning(
            "Wishlist notification overrides target not found",
            extra={
                "event": "notification_wishlist_not_found",
                "user_id": current_user.user_id,
                "wishlist_id": wishlist_id,
                "status_code": status.HTTP_404_NOT_FOUND,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("settings.wishlist_not_found", locale),
        )
    return JSONResponse(content=summary.to_dict())


@router.get("/api/profile/deletion-preview")
async def get_deletion_preview(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> JSONResponse:
    """Return personal account deletion impact summary without exposing others' reservations."""
    service = AccountDeletionService(_get_wishlist_store(request))
    preview = await service.preview_account_deletion(current_user.telegram_id)
    return JSONResponse(
        content={
            "personal_lists_count": preview.personal_lists_count,
            "collaborative_transferred_count": preview.collaborative_transferred_count,
            "collaborative_deleted_count": preview.collaborative_deleted_count,
            "reservations_count": preview.reservations_count,
        }
    )


@router.post("/api/profile/delete")
async def delete_profile_account(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    """Permanently delete the authenticated user's account and revoke all sessions."""
    payload = await _read_json_dict(request, locale)
    if payload.get("confirm") is not True:
        logger.warning(
            "Rejected account deletion without explicit confirmation",
            extra={
                "event": "account_deletion_rejected",
                "reason": "missing_confirmation",
                "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=t("settings.delete_confirmation_required", locale),
        )

    service = AccountDeletionService(_get_wishlist_store(request))
    result = await service.delete_account(
        current_user.telegram_id,
        secret_key=settings.secret_key,
        session_ttl_seconds=settings.session_ttl_seconds,
    )
    response = JSONResponse(
        content={
            "already_deleted": result.already_deleted,
            "deleted_lists": result.deleted_lists,
            "transferred_lists": result.transferred_lists,
            "cancelled_reservations": result.cancelled_reservations,
            "anonymized_items": result.anonymized_items,
        }
    )
    delete_session_cookie(response=response, settings=settings)
    return response
