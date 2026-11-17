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
from wishenka.auth.models import AuthenticatedUser
from wishenka.bot.i18n import sync_user_bot_commands
from wishenka.config import Settings
from wishenka.i18n import DEFAULT_LOCALE, SupportedLocale, t, validate_locale
from wishenka.i18n.dependencies import LocaleDep
from wishenka.notices.sender import PLACEHOLDER_TOKEN
from wishenka.users.store import UserNotFoundError, UserStore
from wishenka.web.templates import templates

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


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> HTMLResponse:
    """Render authenticated Mini App profile settings page with language selector."""
    record = await user_store.get_by_telegram_id(current_user.telegram_id)
    locale_source = record.locale_source if record is not None else "auto"
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "viewer_identified": True,
            "locale": locale,
            "locale_source": locale_source,
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
    except UserNotFoundError as err:
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
