"""Receipt presentation remains readable with Telegram theme variables."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpPage
from tests.browser_helpers import Seeded, open_receipt_dialog

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]


@pytest.mark.parametrize(
    ("background", "foreground"),
    [(None, None), ("#ffffff", "#202020"), ("#202020", "#f5f5f5")],
    ids=["fallback", "light", "dark"],
)
def test_receipt_text_has_readable_contrast(
    seed_wishlist: Callable[..., Seeded],
    wishlist_page: Callable[..., CdpPage],
    background: str | None,
    foreground: str | None,
) -> None:
    """Actual receipt text and controls stay legible in both themes and fallback."""
    seeded = seed_wishlist(["Kettle"], quantities=[5])
    page = wishlist_page(seeded)
    open_receipt_dialog(page, seeded, seeded.item_ids[0])
    page.evaluate(
        "document.querySelector('#receipt-feedback').textContent = 'Feedback';"
        "document.querySelector('#list-notice').textContent = 'Notice';"
    )
    if background is not None and foreground is not None:
        page.evaluate(
            f"document.documentElement.style.setProperty('--tg-theme-bg-color', '{background}');"
            f"document.documentElement.style.setProperty('--tg-theme-text-color', '{foreground}');"
        )

    # Find the nearest painted background, rather than mistaking transparent children for white.
    results = page.evaluate(
        """(() => {
          const selectors = ['.receipt-sheet h2', '.receipt-sheet label',
            '.receipt-feedback', '.receipt-final', '.receipt-sheet select',
            '.btn-receipt-confirm', '.receipt-sheet .btn-modal-close', '#list-notice'];
          const rgb = (value) => value.match(/[\\d.]+/g).map(Number);
          const luminance = (color) => color.slice(0, 3).map((v) => {
            v /= 255;
            return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          }).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
          return selectors.map((selector) => {
            const element = document.querySelector(selector);
            const style = getComputedStyle(element);
            let surface = element;
            while (surface && rgb(getComputedStyle(surface).backgroundColor)[3] === 0) {
              surface = surface.parentElement;
            }
            const fg = luminance(rgb(style.color));
            const bg = luminance(rgb(getComputedStyle(surface).backgroundColor));
            const rect = element.getBoundingClientRect();
            return {selector, contrast: (Math.max(fg, bg) + 0.05) /
              (Math.min(fg, bg) + 0.05), visible: rect.width > 0 && rect.height > 0};
          });
        })()"""
    )
    for result in results:
        assert result["visible"], result
        assert result["contrast"] >= 4.5, result
