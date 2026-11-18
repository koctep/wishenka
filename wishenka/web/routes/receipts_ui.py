"""Receipt dialog and receipt command of the Mini App (WISHENKA-24, page layer only).

``GET`` opens the dialog, ``POST`` records the receipt and answers with out-of-band fragments.
Refusals use the statuses of the JSON route (``receipts._REFUSALS``, read-only), the marker header
``X-Receipt-Refusal`` and fixed Russian sentences. No booking or giver data is rendered or logged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse
from markupsafe import Markup

from wishenka.auth.dependencies import get_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.i18n import DEFAULT_LOCALE, SupportedLocale, t
from wishenka.i18n.dependencies import LocaleDep
from wishenka.web.gifted_view import (
    RECEIPT_REFUSAL_HEADER,
    GiftedRow,
    oob_text,
    read_gifted_rows,
)
from wishenka.web.idempotency import (
    HTML_MEDIA_TYPE,
    build_replay_response,
    compute_request_hash,
    parse_idempotency_key,
    retention_hours_from_request,
)
from wishenka.web.routes.items_ui import (
    _archived_section_html,
    _editor_card_flags,
    _execute,
    _items_list_html,
)
from wishenka.web.routes.receipts import _REFUSALS
from wishenka.web.templates import templates
from wishenka.wishlists.exceptions import (
    IdempotencyConflictError,
    InventoryBusyError,
    ItemNotFoundError,
    NothingRemainingError,
    PermissionDeniedError,
    QuantityAboveRemainingError,
    ReceiptNotFoundError,
    WishArchivedError,
    WishlistArchivedError,
    WishlistError,
)
from wishenka.wishlists.models import WishlistStatus
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.schemas import WishItemGifterViewDTO, WishItemRecipientViewDTO
from wishenka.wishlists.service import WishlistService

router = APIRouter(prefix="/web/wishlists/{wishlist_id}", tags=["receipts-ui"])
logger = logging.getLogger("wishenka.web.receipts_ui")
User = Annotated[AuthenticatedUser, Depends(get_current_user)]

BUSY = "busy"
_REFUSAL_KEYS: dict[str, str] = {
    "quantity_invalid": "web.receipt.error.quantity_invalid",
    "quantity_above_remaining": "web.receipt.error.quantity_above_remaining",
    "nothing_remaining": "web.receipt.error.nothing_remaining",
    "wish_archived": "web.receipt.error.wish_archived",
    "wishlist_not_active": "web.receipt.error.wishlist_not_active",
    "forbidden": "web.receipt.error.forbidden",
    "not_found": "web.receipt.error.not_found",
    "receipt_not_found": "web.receipt.error.receipt_not_found",
    BUSY: "web.receipt.error.busy",
}
_SENTENCES: dict[str, str] = {reason: t(key, "ru") for reason, key in _REFUSAL_KEYS.items()}
_WITH_REMAINING = (QuantityAboveRemainingError, NothingRemainingError)


def _classify(exc: Exception) -> tuple[int, str] | None:
    """Return ``(HTTP status, closed reason)`` of a refusal, or ``None`` for any other error."""
    for error_type, http_status, reason, _message in _REFUSALS:
        if isinstance(exc, error_type):
            return http_status, reason
    return None


def _sentence(
    reason: str,
    exc: Exception | None = None,
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> str:
    """Localized refusal sentence; the remaining quantity comes from the exception."""
    return t(_REFUSAL_KEYS[reason], locale, n=getattr(exc, "remaining_quantity", 0))


def _log(level: int, event: str, message: str, ids: tuple[int, int, int], **extra: Any) -> None:
    """Write one UI record with the fields allowed by WISHENKA-22 (ids are list, wish, actor)."""
    wishlist_id, item_id, actor_id = ids
    logger.log(
        level,
        message,
        extra={
            "event": event,
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": actor_id,
            **extra,
        },
    )


def _log_refusal(
    event: str, ids: tuple[int, int, int], reason: str, http_status: int, exc: Exception
) -> None:
    """Log a refusal; ``remaining_quantity`` only for the two reasons that carry it."""
    extra: dict[str, Any] = {"reason": reason, "http_status": http_status}
    if isinstance(exc, _WITH_REMAINING):
        extra["remaining_quantity"] = exc.remaining_quantity
    _log(logging.WARNING, event, "Receipt refused", ids, **extra)


def _ids(wishlist_id: int, item_id: int, user: AuthenticatedUser) -> tuple[int, int, int]:
    """Log identifiers of one request."""
    return wishlist_id, item_id, user.telegram_id


def _refusal_fragment(
    http_status: int, reason: str, sentence: str, extra_html: str = ""
) -> HTMLResponse:
    """Refusal response: the sentence in ``#receipt-feedback`` (OOB) plus the marker header."""
    body = extra_html or str(oob_text("receipt-feedback", sentence))
    return HTMLResponse(
        content=body, status_code=http_status, headers={RECEIPT_REFUSAL_HEADER: reason}
    )


RECEIPT_SELECT_MAX = 20


def _dialog_html(wishlist_id: int, item_id: int, title: str, remaining: int, **context: Any) -> str:
    """Render the receipt dialog; ``title`` is empty for a viewer who is not a member."""
    return templates.get_template("partials/item_receipt_modal.html").render(
        {
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "item_title": title,
            "remaining": remaining,
            "select_max": RECEIPT_SELECT_MAX,
            **context,
        }
    )


@dataclass(frozen=True)
class _Opened:
    """Advisory state of a member's dialog request; ``refusal`` is the guard that failed."""

    title: str
    remaining: int
    refusal: Exception | None


async def _check_receipt_open(
    svc: WishlistService, wishlist_id: int, item_id: int, user: AuthenticatedUser
) -> _Opened:
    """Guards of the service in its order; a non-member raises, a member gets the verdict."""
    wishlist = await svc.get_wishlist_by_id(wishlist_id)
    item = next((wish for wish in wishlist.items if wish.id == item_id), None)
    if item is None:
        raise ItemNotFoundError(f"Item {item_id} not found")
    if not WishlistAccessPolicy.resolve_context(user, wishlist).is_member:
        raise PermissionDeniedError("Actor cannot fulfill items in this wishlist")
    refusal: Exception | None = None
    if wishlist.status != WishlistStatus.ACTIVE:
        refusal = WishlistArchivedError(f"Wishlist {wishlist_id} is archived")
    elif item.is_archived:
        refusal = WishArchivedError()
    elif item.remaining_quantity == 0:
        refusal = NothingRemainingError()
    return _Opened(item.title, item.remaining_quantity, refusal)


def _blocked_dialog(
    http_status: int,
    reason: str,
    ids: tuple[int, int, int],
    title: str,
    exc: Exception | None,
    extra_html: str = "",
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> HTMLResponse:
    """The dialog in blocked state (sentence, no form) with the marker header."""
    wishlist_id, item_id, _actor = ids
    body = _dialog_html(
        wishlist_id,
        item_id,
        title,
        0,
        blocked=True,
        feedback=_sentence(reason, exc, locale),
        locale=locale,
    )
    return HTMLResponse(
        content=f"{body}\n{extra_html}",
        status_code=http_status,
        headers={RECEIPT_REFUSAL_HEADER: reason},
    )


@router.get("/items/{item_id}/receipt", response_class=HTMLResponse)
async def get_receipt_dialog(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
) -> Response:
    """Open the receipt dialog; a stale card gets the blocked dialog with the contract status."""
    ids = _ids(wishlist_id, item_id, user)
    title = ""
    remaining = 0
    refusal: Exception | None
    try:
        opened = await _execute(
            request, lambda svc: _check_receipt_open(svc, wishlist_id, item_id, user)
        )
        title, remaining, refusal = opened.title, opened.remaining, opened.refusal
    except WishlistError as exc:
        refusal = exc
    if refusal is None:
        _log(logging.INFO, "ui_receipt_form_opened", "Receipt dialog opened", ids)
        return HTMLResponse(
            _dialog_html(wishlist_id, item_id, title, remaining, selected=1, locale=locale)
        )
    if isinstance(refusal, InventoryBusyError):
        http_status, reason = 503, BUSY
    else:
        verdict = _classify(refusal)
        if verdict is None:
            raise refusal
        http_status, reason = verdict
    _log_refusal("ui_receipt_form_refused", ids, reason, http_status, refusal)
    extra = ""
    if isinstance(refusal, NothingRemainingError):
        extra = (
            await _effect_fragments(
                request,
                user,
                ids,
                reason,
                refusal,
                title,
                dialog_oob=False,
                locale=locale,
            )
            or ""
        )
    return _blocked_dialog(http_status, reason, ids, title, refusal, extra, locale=locale)


type _View = WishItemRecipientViewDTO | WishItemGifterViewDTO


@dataclass(frozen=True)
class _State:
    """Committed state read for the response: the viewer's active list and the gifted rows."""

    items: list[_View]
    gifted: list[GiftedRow] | None

    def shown(self, item_id: int) -> _View | None:
        """The wish as a card of the active list, ``None`` when it left the list."""
        return next((item for item in self.items if item.id == item_id), None)


async def _read_state(
    svc: WishlistService,
    wishlist_id: int,
    user: AuthenticatedUser,
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> _State:
    """Read the active list and the gifted rows (fail-soft) for the viewer."""
    items = await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)
    return _State(items, await read_gifted_rows(svc, wishlist_id, user, locale))


@dataclass(frozen=True)
class _Receipt:
    """Result of an accepted receipt."""

    title: str
    remaining: int
    state: _State


def _quantity_of(raw: str) -> int:
    """Parse the form value; text that is not a whole number becomes 0, which the service
    refuses as ``quantity_invalid`` after its membership and state guards."""
    text = raw.strip()
    return int(text) if re.fullmatch(r"-?[0-9]{1,9}", text) else 0


def _card_oob(
    request: Request,
    wishlist_id: int,
    item: _View,
    items: list[_View],
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> str:
    """The card of ``item`` as an out-of-band replacement with first/last flags of ``items``."""
    position = [wish.id for wish in items].index(item.id)
    return templates.get_template("partials/item_card.html").render(
        {
            "request": request,
            "item": item,
            "wishlist_id": wishlist_id,
            "can_edit_wishlist": True,
            "card_oob": True,
            "is_first": position == 0,
            "is_last": position == len(items) - 1,
            "locale": locale,
            **_editor_card_flags(),
        }
    )


def _list_oob(
    request: Request,
    wishlist_id: int,
    items: list[_View],
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> Markup:
    """Replace the content of ``#items-list`` (flags and the empty-list text come along)."""
    html = _items_list_html(request, wishlist_id, items, locale)
    return Markup('<div hx-swap-oob="innerHTML:#items-list">{}</div>').format(Markup(html))


def _gifted_oob(
    request: Request,
    gifted: list[GiftedRow] | None,
    locale: SupportedLocale = DEFAULT_LOCALE,
    *,
    wishlist_id: int | None = None,
) -> str:
    """The «Подаренные» section as an out-of-band replacement."""
    return templates.get_template("partials/gifted_items_section.html").render(
        {
            "request": request,
            "gifted_rows": gifted,
            "wishlist_id": wishlist_id,
            "can_edit_wishlist": wishlist_id is not None,
            "oob": True,
            "locale": locale,
        }
    )


async def _effect_fragments(
    request: Request,
    user: AuthenticatedUser,
    ids: tuple[int, int, int],
    reason: str,
    exc: Exception,
    title: str = "",
    *,
    dialog_oob: bool = True,
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> str | None:
    """Fragments that show the current state after a refusal; ``None`` degrades to the sentence.

    The refused transaction was rolled back, so this is one more read-only action. It is best
    effort: a domain or busy error here never replaces the status or sentence of the refusal.
    """
    wishlist_id, item_id, _actor = ids
    try:
        state = await _execute(request, lambda svc: _read_state(svc, wishlist_id, user, locale))
    except WishlistError:
        return None
    sentence = _sentence(reason, exc, locale)
    shown = state.shown(item_id)
    if reason == "quantity_above_remaining":
        if shown is None:
            return None
        card = _card_oob(request, wishlist_id, shown, state.items, locale)
        dialog = _dialog_html(
            wishlist_id,
            item_id,
            shown.title,
            shown.remaining_quantity or 0,
            feedback=sentence,
            oob=True,
            selected=1,
            locale=locale,
        )
        return f"{card}\n{dialog}"
    gifted = state.gifted or []
    title = title or next((row.title for row in gifted if row.item_id == item_id), "")
    parts = [
        _list_oob(request, wishlist_id, state.items, locale),
        _gifted_oob(request, state.gifted, locale, wishlist_id=wishlist_id),
    ]
    if dialog_oob:
        parts.append(
            _dialog_html(
                wishlist_id,
                item_id,
                title,
                0,
                blocked=True,
                feedback=sentence,
                oob=True,
                locale=locale,
            )
        )
    return "\n".join(parts)


@router.post(
    "/items/{item_id}/receipt",
    response_class=HTMLResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_receipt_ui(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
    quantity: Annotated[str, Form()] = "",
) -> Response:
    """Record a receipt and answer with out-of-band fragments (dialog, notice, card or list)."""
    idempotency_key = parse_idempotency_key(request)
    ids = _ids(wishlist_id, item_id, user)
    count = _quantity_of(quantity)

    async def action(svc: WishlistService) -> _Receipt:
        item = await svc.record_item_fulfillment(item_id, user, count, wishlist_id=wishlist_id)
        return _Receipt(
            item.title, item.remaining_quantity, await _read_state(svc, wishlist_id, user, locale)
        )

    def _render_receipt_html(done: _Receipt) -> str:
        state = done.state
        shown = state.shown(item_id)
        main = (
            _card_oob(request, wishlist_id, shown, state.items, locale)
            if shown is not None and done.remaining > 0
            else _list_oob(request, wishlist_id, state.items, locale)
        )
        notice = oob_text(
            "list-notice",
            t("web.receipt.recorded_notice", locale, count=count, title=done.title),
        )
        parts = [
            oob_text("item-modal-container"),
            notice,
            main,
            _gifted_oob(request, state.gifted, locale, wishlist_id=wishlist_id),
        ]
        return "\n".join(parts)

    try:
        injected = getattr(request.app.state, "wishlist_service", None)
        if idempotency_key is not None and injected is None:
            request_hash = compute_request_hash(
                "record_receipt_ui",
                {"wishlist_id": wishlist_id, "item_id": item_id},
                {"quantity": count},
            )

            async def serialized_action(svc: WishlistService) -> tuple[int, str, str]:
                done = await action(svc)
                return status.HTTP_201_CREATED, HTML_MEDIA_TYPE, _render_receipt_html(done)

            outcome = await request.app.state.wishlist_store.execute_wish_idempotent(
                serialized_action,
                actor_id=user.telegram_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                retention_hours=retention_hours_from_request(request),
                item_id=item_id,
                operation_name="record_receipt_ui",
                require_member=True,
            )
            _log(logging.INFO, "receipt_recorded_http", "Receipt recorded", ids)
            return build_replay_response(outcome.status_code, outcome.content_type, outcome.body)
        done = await _execute(request, action)
    except InventoryBusyError:
        _log(logging.WARNING, "receipt_inventory_busy", "Receipt busy", ids)
        return _refusal_fragment(
            status.HTTP_503_SERVICE_UNAVAILABLE, BUSY, _sentence(BUSY, locale=locale)
        )
    except IdempotencyConflictError as exc:
        _log_refusal("receipt_refused", ids, "idempotency_conflict", status.HTTP_409_CONFLICT, exc)
        return _refusal_fragment(status.HTTP_409_CONFLICT, "idempotency_conflict", str(exc))
    except WishlistError as exc:
        verdict = _classify(exc)
        if verdict is None:
            raise
        http_status, reason = verdict
        _log_refusal("receipt_refused", ids, reason, http_status, exc)
        extra = None
        if isinstance(exc, _WITH_REMAINING):
            extra = await _effect_fragments(request, user, ids, reason, exc, locale=locale)
        return _refusal_fragment(http_status, reason, _sentence(reason, exc, locale), extra or "")
    _log(logging.INFO, "receipt_recorded_http", "Receipt recorded", ids)
    return HTMLResponse(_render_receipt_html(done), status_code=status.HTTP_201_CREATED)


@dataclass(frozen=True)
class _ReceiptEntryOpen:
    """Advisory state of a receipt edit/cancel modal request."""

    title: str
    current_quantity: int
    max_allowed: int
    refusal: Exception | None


@dataclass(frozen=True)
class _FullMutationState:
    """Committed state read for edit/cancel OOB updates (active, archive, gifted)."""

    title: str
    items: list[_View]
    archived: list[WishItemRecipientViewDTO]
    gifted: list[GiftedRow] | None


async def _check_receipt_entry_open(
    svc: WishlistService,
    wishlist_id: int,
    item_id: int,
    receipt_id: int,
    user: AuthenticatedUser,
) -> _ReceiptEntryOpen:
    """Validate membership, list status, item, and receipt record for edit/cancel modal open."""
    wishlist = await svc.get_wishlist_by_id(wishlist_id)
    item = next((wish for wish in wishlist.items if wish.id == item_id), None)
    if item is None:
        raise ItemNotFoundError(f"Item {item_id} not found")
    if not WishlistAccessPolicy.resolve_context(user, wishlist).is_member:
        raise PermissionDeniedError("Actor cannot modify receipts in this wishlist")
    if wishlist.status != WishlistStatus.ACTIVE:
        return _ReceiptEntryOpen(
            item.title, 0, 0, WishlistArchivedError(f"Wishlist {wishlist_id} is archived")
        )
    receipt = next((r for r in item.receipts if r.id == receipt_id), None)
    if receipt is None:
        return _ReceiptEntryOpen(
            item.title, 0, 0, ReceiptNotFoundError(f"Receipt {receipt_id} not found")
        )
    return _ReceiptEntryOpen(
        item.title, receipt.quantity, receipt.quantity + item.remaining_quantity, None
    )


async def _read_full_mutation_state(
    svc: WishlistService,
    wishlist_id: int,
    user: AuthenticatedUser,
    title: str,
    locale: SupportedLocale,
) -> _FullMutationState:
    items = await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)
    view = await svc.get_wishlist_view(wishlist_id, user)
    gifted = await read_gifted_rows(svc, wishlist_id, user, locale)
    return _FullMutationState(title, items, list(view.archived_items), gifted)


def _render_mutation_oob(
    request: Request,
    wishlist_id: int,
    state: _FullMutationState,
    notice_text: str,
    locale: SupportedLocale,
) -> str:
    parts = [
        str(oob_text("item-modal-container")),
        str(oob_text("list-notice", notice_text)),
        str(_list_oob(request, wishlist_id, state.items, locale)),
        _gifted_oob(request, state.gifted, locale, wishlist_id=wishlist_id),
        _archived_section_html(request, wishlist_id, state.archived, locale),
    ]
    return "\n".join(parts)


async def _open_receipt_entry_modal(
    template_name: str,
    wishlist_id: int,
    item_id: int,
    receipt_id: int,
    request: Request,
    user: AuthenticatedUser,
    locale: SupportedLocale,
) -> Response:
    ids = _ids(wishlist_id, item_id, user)
    title = ""
    current_quantity = 0
    max_allowed = 0
    refusal: Exception | None
    try:
        opened = await _execute(
            request,
            lambda svc: _check_receipt_entry_open(svc, wishlist_id, item_id, receipt_id, user),
        )
        title = opened.title
        current_quantity = opened.current_quantity
        max_allowed = opened.max_allowed
        refusal = opened.refusal
    except WishlistError as exc:
        refusal = exc

    ctx: dict[str, Any] = {
        "wishlist_id": wishlist_id,
        "item_id": item_id,
        "receipt_id": receipt_id,
        "item_title": title,
        "current_quantity": current_quantity,
        "max_allowed": max_allowed,
        "locale": locale,
    }
    if refusal is None:
        _log(
            logging.INFO,
            "ui_receipt_entry_form_opened",
            "Receipt entry dialog opened",
            ids,
            receipt_id=receipt_id,
        )
        return HTMLResponse(templates.get_template(template_name).render(ctx))

    if isinstance(refusal, InventoryBusyError):
        http_status, reason = 503, BUSY
    else:
        verdict = _classify(refusal)
        if verdict is None:
            raise refusal
        http_status, reason = verdict
    _log_refusal("ui_receipt_entry_form_refused", ids, reason, http_status, refusal)
    ctx["blocked"] = True
    ctx["feedback"] = _sentence(reason, refusal, locale)
    return HTMLResponse(
        content=templates.get_template(template_name).render(ctx),
        status_code=http_status,
        headers={RECEIPT_REFUSAL_HEADER: reason},
    )


async def _execute_receipt_mutation_ui(
    request: Request,
    user: AuthenticatedUser,
    wishlist_id: int,
    item_id: int,
    receipt_id: int,
    operation_name: str,
    success_event: str,
    request_hash_payload: dict[str, Any],
    action: Any,
    notice_fn: Any,
    locale: SupportedLocale,
) -> Response:
    idempotency_key = parse_idempotency_key(request)
    ids = _ids(wishlist_id, item_id, user)

    def _render_html(done: _FullMutationState) -> str:
        return _render_mutation_oob(request, wishlist_id, done, notice_fn(done.title), locale)

    try:
        injected = getattr(request.app.state, "wishlist_service", None)
        if idempotency_key is not None and injected is None:
            request_hash = compute_request_hash(
                operation_name,
                {"wishlist_id": wishlist_id, "item_id": item_id},
                request_hash_payload,
            )

            async def serialized_action(svc: WishlistService) -> tuple[int, str, str]:
                done = await action(svc)
                return status.HTTP_200_OK, HTML_MEDIA_TYPE, _render_html(done)

            outcome = await request.app.state.wishlist_store.execute_wish_idempotent(
                serialized_action,
                actor_id=user.telegram_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                retention_hours=retention_hours_from_request(request),
                item_id=item_id,
                operation_name=operation_name,
                require_member=True,
            )
            _log(
                logging.INFO,
                success_event,
                "Receipt mutation applied",
                ids,
                receipt_id=receipt_id,
            )
            return build_replay_response(outcome.status_code, outcome.content_type, outcome.body)
        done = await _execute(request, action)
    except InventoryBusyError:
        _log(logging.WARNING, "receipt_inventory_busy", "Receipt busy", ids)
        return _refusal_fragment(
            status.HTTP_503_SERVICE_UNAVAILABLE, BUSY, _sentence(BUSY, locale=locale)
        )
    except IdempotencyConflictError as exc:
        _log_refusal("receipt_refused", ids, "idempotency_conflict", status.HTTP_409_CONFLICT, exc)
        return _refusal_fragment(status.HTTP_409_CONFLICT, "idempotency_conflict", str(exc))
    except WishlistError as exc:
        verdict = _classify(exc)
        if verdict is None:
            raise
        http_status, reason = verdict
        _log_refusal("receipt_refused", ids, reason, http_status, exc)
        return _refusal_fragment(http_status, reason, _sentence(reason, exc, locale))
    _log(logging.INFO, success_event, "Receipt mutation applied", ids, receipt_id=receipt_id)
    return HTMLResponse(_render_html(done), status_code=status.HTTP_200_OK)


@router.get("/items/{item_id}/receipts/{receipt_id}/edit", response_class=HTMLResponse)
async def get_receipt_edit_dialog(
    wishlist_id: int,
    item_id: int,
    receipt_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
) -> Response:
    """Open the receipt quantity correction modal."""
    return await _open_receipt_entry_modal(
        "partials/receipt_edit_modal.html",
        wishlist_id,
        item_id,
        receipt_id,
        request,
        user,
        locale,
    )


@router.post("/items/{item_id}/receipts/{receipt_id}/edit", response_class=HTMLResponse)
async def correct_receipt_ui(
    wishlist_id: int,
    item_id: int,
    receipt_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
    quantity: Annotated[str, Form()] = "",
) -> Response:
    """Correct a receipt record quantity and return OOB fragments."""
    count = _quantity_of(quantity)

    async def action(svc: WishlistService) -> _FullMutationState:
        item = await svc.correct_item_receipt(
            item_id, receipt_id, user, count, wishlist_id=wishlist_id
        )
        return await _read_full_mutation_state(svc, wishlist_id, user, item.title, locale)

    return await _execute_receipt_mutation_ui(
        request,
        user,
        wishlist_id,
        item_id,
        receipt_id,
        "correct_receipt_ui",
        "receipt_corrected_http",
        {"receipt_id": receipt_id, "quantity": count},
        action,
        lambda title: t("web.receipt.corrected_notice", locale, count=count, title=title),
        locale,
    )


@router.get("/items/{item_id}/receipts/{receipt_id}/cancel", response_class=HTMLResponse)
async def get_receipt_cancel_dialog(
    wishlist_id: int,
    item_id: int,
    receipt_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
) -> Response:
    """Open the receipt cancellation confirmation modal."""
    return await _open_receipt_entry_modal(
        "partials/receipt_cancel_modal.html",
        wishlist_id,
        item_id,
        receipt_id,
        request,
        user,
        locale,
    )


@router.post("/items/{item_id}/receipts/{receipt_id}/cancel", response_class=HTMLResponse)
async def cancel_receipt_ui(
    wishlist_id: int,
    item_id: int,
    receipt_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
) -> Response:
    """Cancel a receipt record and return OOB fragments."""

    async def action(svc: WishlistService) -> _FullMutationState:
        item = await svc.cancel_item_receipt(item_id, receipt_id, user, wishlist_id=wishlist_id)
        return await _read_full_mutation_state(svc, wishlist_id, user, item.title, locale)

    return await _execute_receipt_mutation_ui(
        request,
        user,
        wishlist_id,
        item_id,
        receipt_id,
        "cancel_receipt_ui",
        "receipt_cancelled_http",
        {"receipt_id": receipt_id},
        action,
        lambda title: t("web.receipt.cancelled_notice", locale, title=title),
        locale,
    )
