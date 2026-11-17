"""FastAPI dependencies for resolving the active request locale."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from wishenka.auth.dependencies import (
    get_optional_current_user,
    get_settings,
    get_user_store,
)
from wishenka.auth.models import AuthenticatedUser
from wishenka.config import Settings
from wishenka.i18n.locale import (
    SupportedLocale,
    resolve_accept_language,
    resolve_optional_locale,
)
from wishenka.users.store import UserStore


async def get_request_locale(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> SupportedLocale:
    """Resolve the active locale for a request from live profile or anonymous signals."""
    current_user: AuthenticatedUser | None = None
    try:
        current_user = await get_optional_current_user(request, settings)
    except HTTPException:
        current_user = None

    resolved: SupportedLocale | None = None
    if current_user is not None:
        record = await user_store.get_by_telegram_id(current_user.telegram_id)
        if record is not None:
            resolved = record.locale

    if resolved is None:
        resolved = resolve_optional_locale(
            request.query_params.get("lang")
        ) or resolve_accept_language(request.headers.get("accept-language"))

    request.state.locale = resolved
    return resolved


LocaleDep = Annotated[SupportedLocale, Depends(get_request_locale)]
