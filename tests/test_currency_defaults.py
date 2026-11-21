"""Currency defaults and edit options remain consistent in rendered forms."""

import pytest
from bs4 import BeautifulSoup

from wishenka.items.parser import normalize_currency
from wishenka.web.templates import templates

pytestmark = pytest.mark.timeout(10)


@pytest.mark.parametrize(
    ("currency", "expected"), [(None, "RUB"), ("USD", "USD"), ("JPY", "JPY"), ("CHF", "CHF")]
)
def test_edit_form_currency_choices(currency: str | None, expected: str) -> None:
    """A missing currency selects RUB while an explicit selection is preserved."""
    template = templates.env.get_template("partials/item_edit_modal.html")
    html = template.render(form={"currency": currency}, wishlist_id=1, min_quantity=1)
    select = BeautifulSoup(html, "html.parser").select_one("#item-currency-select")
    assert select is not None
    options = select.select("option")
    standard_options = [
        (o["value"], o.get_text(strip=True)) for o in options if o["value"] != "CHF"
    ]
    assert standard_options == [
        ("RUB", "RUB (₽)"),
        ("USD", "USD ($)"),
        ("EUR", "EUR (€)"),
        ("KZT", "KZT (₸)"),
        ("BYN", "BYN (Br)"),
        ("CNY", "CNY (¥)"),
        ("GBP", "GBP (£)"),
        ("JPY", "JPY (¥)"),
        ("TRY", "TRY (₺)"),
        ("GEL", "GEL (₾)"),
        ("AMD", "AMD (֏)"),
    ]
    selected = select.select_one("option[selected]")
    assert selected is not None
    assert selected["value"] == expected


def test_currency_parser_preserves_default_and_explicit_currency() -> None:
    """The parser maintains existing default and normalization behavior."""
    assert normalize_currency(None) == "RUB"
    assert normalize_currency("$") == "USD"


@pytest.mark.parametrize(("currency", "expected"), [(None, "RUB"), ("USD", "USD")])
def test_currency_in_item_preview_archive_and_gifted(currency: str | None, expected: str) -> None:
    """Every affected presentation shows the fallback and preserves an explicit code."""
    from wishenka.web.gifted_view import build_gifted_rows
    from wishenka.wishlists.schemas import GiftedItemDTO

    item = {
        "id": 1,
        "title": "Kettle",
        "price": 100,
        "currency": currency,
        "quantity": 1,
        "received_quantity": 0,
        "is_recipient": True,
    }
    context = {"wishlist_id": 1, "item": item, "preview": item, "archived_items": [item]}
    for name, selector in (
        ("item_card.html", ".item-price"),
        ("item_preview_card.html", ".preview-price"),
        ("archived_items_section.html", ".archived-item-price"),
    ):
        html = templates.env.get_template(f"partials/{name}").render(**context)
        element = BeautifulSoup(html, "html.parser").select_one(selector)
        assert element is not None
        assert element.get_text(" ", strip=True) == f"100 {expected}"
        if name == "item_preview_card.html":
            hidden = BeautifulSoup(html, "html.parser").select_one('input[name="currency"]')
            assert hidden is not None
            assert hidden["value"] == expected

    gifted = GiftedItemDTO(id=1, title="Kettle", price=100, currency=currency or "")
    assert build_gifted_rows([gifted])[0].price == f"100 {expected}"


def test_currency_defaults_on_item_model_boundaries() -> None:
    """Item input and preview DTOs expose the default or the caller's explicit currency."""
    from wishenka.items.schemas import CreateItemDTO, ItemPreviewDTO
    from wishenka.wishlists.schemas import GiftedItemDTO

    assert CreateItemDTO(title="Kettle").currency == "RUB"
    assert CreateItemDTO(title="Kettle", currency="EUR").currency == "EUR"
    assert ItemPreviewDTO().currency == "RUB"
    assert ItemPreviewDTO(currency="USD").currency == "USD"
    assert GiftedItemDTO(id=1, title="Kettle").currency == "RUB"
