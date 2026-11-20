"""Regression test suite for marketplace web cassettes (WISHENKA-97).

Validates:
1. Reference YAML cassettes exist for all top-5 target Russian marketplaces
   (Ozon, Wildberries, Yandex Market, Avito, Megamarket) covering both valid
   product cards (`product`) and anti-bot/anti-fraud screens (`antibot`).
2. Strict offline replay (`CassetteMode.REPLAY`) through the full
   `ItemPreviewService.fetch_preview` -> `UrlMetadataService._fetch_html` ->
   `HtmlMetadataExtractor.extract` pipeline without live DNS or socket calls.
3. Detection of Russian anti-bot/anti-fraud challenge pages (including 200 OK
   Yandex SmartCaptcha "Почти готово...", 200 OK Avito IP firewall
   "Доступ ограничен: проблема с IP", and 403/503 Qrator/Cloudflare/WAF pages)
   with graceful degradation (`is_fallback=True`, `fallback_reason="anti_bot_challenge"`)
   and zero leakage of challenge titles/descriptions into wish cards.
4. Fail-closed behavior on missing cassette interactions (`CassetteMissError`)
   without falling back to live external network requests or masking misses as
   generic `http_error` fallbacks.
5. Controlled recording (`CassetteMode.RECORD`) and refresh (`CassetteMode.REFRESH`)
   with automatic sanitization of cookies, authorization headers, tokens, client IPs,
   and tracking query parameters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml  # type: ignore[import-untyped]

from wishenka.items.service import ItemPreviewService
from wishenka.items.ssrf import _dns_cache, clear_dns_cache

pytestmark = pytest.mark.timeout(15)

CASSETTES_DIR = Path(__file__).resolve().parent / "cassettes" / "marketplaces"

MARKETPLACES: tuple[str, ...] = (
    "ozon",
    "wildberries",
    "yandex_market",
    "avito",
    "megamarket",
)

SCENARIOS: tuple[str, ...] = ("product", "antibot")

FORBIDDEN_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-xsrf-token",
        "cf-connecting-ip",
        "x-forwarded-for",
        "x-real-ip",
        "x-client-ip",
        "x-device-id",
        "x-session-id",
    }
)

PRODUCT_EXPECTATIONS: list[tuple[str, str, str, str, int, str, str, str]] = [
    (
        "ozon",
        "https://ozon.ru/product/besprovodnye-naushniki-sony-wh-1000xm5-123456789/?utm_source=telegram&utm_medium=share&clid=12345",
        "https://ozon.ru/product/besprovodnye-naushniki-sony-wh-1000xm5-123456789/",
        "Беспроводные наушники Sony WH-1000XM5",
        29990,
        "Ozon",
        "https://ir.ozone.ru/s3/multimedia-1/wc1000/6789012345.jpg",
        "Флагманские наушники с активным шумоподавлением и автономностью до 30 часов.",
    ),
    (
        "wildberries",
        "https://www.wildberries.ru/catalog/214567890/detail.aspx?utm_campaign=wb_share&targetUrl=XS&from=share_ios",
        "https://www.wildberries.ru/catalog/214567890/detail.aspx",
        "Кофемашина рожковая DeLonghi Dedica EC685.M",
        14590,
        "Wildberries",
        "https://basket-14.wbbasket.ru/vol2145/part214567/214567890/images/big/1.webp",
        "Компактная рожковая кофемашина в металлическом корпусе с профессиональным капучинатором.",
    ),
    (
        "yandex_market",
        "https://market.yandex.ru/product--umnye-chasy-apple-watch-series-9/987654321?clid=777&yclid=888&utm_term=watch",
        "https://market.yandex.ru/product--umnye-chasy-apple-watch-series-9/987654321",
        "Умные часы Apple Watch Series 9 45mm",
        38490,
        "Яндекс Маркет",
        "https://avatars.mds.yandex.net/get-mpic/5234567/img_id123456789.jpeg/orig",
        "Смарт-часы с чипом S9, ярким дисплеем Retina и жестом двойного касания.",
    ),
    (
        "avito",
        "https://www.avito.ru/moskva/audio_i_video/igrovaya_konsol_playstation_5_slim_3456789012?utm_source=avito_ios&src=sharing",
        "https://www.avito.ru/moskva/audio_i_video/igrovaya_konsol_playstation_5_slim_3456789012",
        "Игровая консоль PlayStation 5 Slim",
        47900,
        "Авито",
        "https://40.img.avito.st/image/1/1.ps5_slim.jpg",
        "Новая консоль PS5 Slim с дисководом, гарантия 1 год.",
    ),
    (
        "megamarket",
        "https://megamarket.ru/catalog/details/robot-pylesos-roborock-s8-pro-ultra-600012345678/?utm_source=mm_app&promo=ny2026",
        "https://megamarket.ru/catalog/details/robot-pylesos-roborock-s8-pro-ultra-600012345678/",
        "Робот-пылесос Roborock S8 Pro Ultra",
        89990,
        "Мегамаркет",
        "https://main-cdn.sbermegamarket.ru/big2/hlr-system/roborock-s8.jpg",
        "Мощный робот-пылесос со станцией самоочистки и влажной уборкой VibraRise 2.0.",
    ),
]

ANTIBOT_EXPECTATIONS: list[tuple[str, str, str, str, tuple[str, ...]]] = [
    (
        "ozon",
        "https://ozon.ru/product/besprovodnye-naushniki-sony-wh-1000xm5-123456789/?utm_source=share",
        "https://ozon.ru/product/besprovodnye-naushniki-sony-wh-1000xm5-123456789/",
        "Ozon",
        ("Доступ ограничен", "Проверка браузера"),
    ),
    (
        "wildberries",
        "https://www.wildberries.ru/catalog/214567890/detail.aspx?from=share",
        "https://www.wildberries.ru/catalog/214567890/detail.aspx",
        "Wildberries",
        ("Проверка браузера", "Доступ временно ограничен"),
    ),
    (
        "yandex_market",
        "https://market.yandex.ru/product--umnye-chasy-apple-watch-series-9/987654321?clid=900",
        "https://market.yandex.ru/product--umnye-chasy-apple-watch-series-9/987654321",
        "Яндекс Маркет",
        ("Почти готово", "не робот"),
    ),
    (
        "avito",
        "https://www.avito.ru/moskva/audio_i_video/igrovaya_konsol_playstation_5_slim_3456789012?src=share",
        "https://www.avito.ru/moskva/audio_i_video/igrovaya_konsol_playstation_5_slim_3456789012",
        "Авито",
        ("Доступ ограничен", "проблема с IP"),
    ),
    (
        "megamarket",
        "https://megamarket.ru/catalog/details/robot-pylesos-roborock-s8-pro-ultra-600012345678/?promo=test",
        "https://megamarket.ru/catalog/details/robot-pylesos-roborock-s8-pro-ultra-600012345678/",
        "Мегамаркет",
        ("Проверка браузера", "Доступ ограничен"),
    ),
]


def _load_cassettes_module() -> Any:
    """Import wishenka.items.cassettes at test execution time."""
    import wishenka.items.cassettes as cassettes

    return cassettes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "expected_store", "forbidden_snippet"),
    [
        ("yandex_market_antibot.yaml", "Яндекс Маркет", "Почти готово"),
        ("avito_antibot.yaml", "Авито", "Доступ ограничен"),
        ("megamarket_antibot.yaml", "Мегамаркет", "Проверка браузера"),
    ],
    ids=["yandex_smartcaptcha_200", "avito_ip_firewall_200", "megamarket_browser_check_503"],
)
async def test_russian_marketplace_antibot_pages_trigger_anti_bot_fallback_without_title_leak(
    filename: str,
    expected_store: str,
    forbidden_snippet: str,
) -> None:
    """Russian 200 OK / 503 anti-bot pages must degrade without leaking titles."""
    clear_dns_cache()
    service = ItemPreviewService()

    raw_data = yaml.safe_load((CASSETTES_DIR / filename).read_text(encoding="utf-8"))
    interaction = raw_data["interactions"][0]
    target_uri = interaction["request"]["uri"]
    status_code = interaction["response"]["status"]["code"]
    body_text = interaction["response"]["body"]["string"]

    parsed = httpx.URL(target_uri)
    _dns_cache.put(parsed.host, 443, ["93.184.216.34"])

    def _handler(
        request: httpx.Request,
        code: int = status_code,
        text: str = body_text,
    ) -> httpx.Response:
        return httpx.Response(
            status_code=code,
            headers={"content-type": "text/html; charset=utf-8"},
            text=text,
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        preview = await service.fetch_preview(target_uri, client=client)

    assert preview.is_fallback is True, (
        f"{filename}: expected is_fallback=True for anti-bot challenge page, "
        f"got is_fallback={preview.is_fallback} with title={preview.title!r}"
    )
    assert preview.fallback_reason == "anti_bot_challenge", (
        f"{filename}: expected fallback_reason='anti_bot_challenge', "
        f"got {preview.fallback_reason!r}"
    )
    assert preview.store_name == expected_store
    assert preview.title is None
    assert preview.description is None
    assert forbidden_snippet.lower() not in (preview.title or "").lower()


def test_marketplace_reference_cassettes_exist_and_load() -> None:
    """All 10 reference cassettes (5 marketplaces x 2 scenarios) must exist and load."""
    cassettes = _load_cassettes_module()

    for marketplace in MARKETPLACES:
        for scenario in SCENARIOS:
            cassette_path = CASSETTES_DIR / f"{marketplace}_{scenario}.yaml"
            assert cassette_path.is_file(), f"Missing reference cassette: {cassette_path}"

            loaded = cassettes.load_marketplace_cassette(marketplace, scenario)
            assert isinstance(loaded, cassettes.Cassette)
            assert loaded.version == 1
            assert loaded.marketplace == marketplace
            assert loaded.scenario == scenario
            assert len(loaded.interactions) >= 1

            for interaction in loaded.interactions:
                req_headers = {k.lower() for k in interaction.request.headers}
                resp_headers = {k.lower() for k in interaction.response.headers}
                assert req_headers.isdisjoint(FORBIDDEN_HEADER_NAMES)
                assert resp_headers.isdisjoint(FORBIDDEN_HEADER_NAMES)
                assert interaction.response.body.strip() != ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "marketplace",
        "dirty_url",
        "expected_clean_url",
        "expected_title",
        "expected_price",
        "expected_store",
        "expected_image",
        "expected_description",
    ),
    PRODUCT_EXPECTATIONS,
    ids=[row[0] for row in PRODUCT_EXPECTATIONS],
)
async def test_replay_product_cassettes_extract_metadata_offline(
    marketplace: str,
    dirty_url: str,
    expected_clean_url: str,
    expected_title: str,
    expected_price: int,
    expected_store: str,
    expected_image: str,
    expected_description: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Product cassettes for all 5 marketplaces must replay offline and extract rich metadata."""
    cassettes = _load_cassettes_module()
    clear_dns_cache()

    import socket

    def _forbid_live_dns(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Live DNS lookup attempted during offline REPLAY mode")

    monkeypatch.setattr(socket, "getaddrinfo", _forbid_live_dns)

    cassette_path = CASSETTES_DIR / f"{marketplace}_product.yaml"
    service = ItemPreviewService()

    async with cassettes.cassette_client(
        cassette_path,
        mode=cassettes.CassetteMode.REPLAY,
    ) as client:
        preview = await service.fetch_preview(dirty_url, client=client)

    assert preview.is_fallback is False
    assert preview.fallback_reason is None
    assert preview.url == expected_clean_url
    assert preview.title == expected_title
    assert preview.price == expected_price
    assert preview.currency == "RUB"
    assert preview.store_name == expected_store
    assert preview.image_url == expected_image
    assert preview.description == expected_description
    assert preview.store_icon_url is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "marketplace",
        "dirty_url",
        "expected_clean_url",
        "expected_store",
        "forbidden_snippets",
    ),
    ANTIBOT_EXPECTATIONS,
    ids=[row[0] for row in ANTIBOT_EXPECTATIONS],
)
async def test_replay_antibot_cassettes_trigger_graceful_fallback_without_title_leak(
    marketplace: str,
    dirty_url: str,
    expected_clean_url: str,
    expected_store: str,
    forbidden_snippets: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anti-bot cassettes for all 5 marketplaces must trigger fallback without text leak."""
    cassettes = _load_cassettes_module()
    clear_dns_cache()

    import socket

    def _forbid_live_dns(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Live DNS lookup attempted during offline REPLAY mode")

    monkeypatch.setattr(socket, "getaddrinfo", _forbid_live_dns)

    cassette_path = CASSETTES_DIR / f"{marketplace}_antibot.yaml"
    service = ItemPreviewService()

    async with cassettes.cassette_client(
        cassette_path,
        mode=cassettes.CassetteMode.REPLAY,
    ) as client:
        preview = await service.fetch_preview(dirty_url, client=client)

    assert preview.is_fallback is True
    assert preview.fallback_reason == "anti_bot_challenge"
    assert preview.url == expected_clean_url
    assert preview.store_name == expected_store
    assert preview.title is None
    assert preview.description is None
    for snippet in forbidden_snippets:
        assert snippet.lower() not in (preview.title or "").lower()
        assert snippet.lower() not in (preview.description or "").lower()


@pytest.mark.asyncio
async def test_replay_antibot_composite_share_preserves_residual_title_without_leak() -> None:
    """Composite mobile share input on an anti-bot cassette keeps user text and leaks no title."""
    cassettes = _load_cassettes_module()
    clear_dns_cache()

    cassette_path = CASSETTES_DIR / "yandex_market_antibot.yaml"
    service = ItemPreviewService()
    composite_input = (
        "Смотри какие часы на Маркете "
        "https://market.yandex.ru/product--umnye-chasy-apple-watch-series-9/987654321?utm_source=share"
    )

    async with cassettes.cassette_client(
        cassette_path,
        mode=cassettes.CassetteMode.REPLAY,
    ) as client:
        preview = await service.fetch_preview(composite_input, client=client)

    assert preview.is_fallback is True
    assert preview.fallback_reason == "anti_bot_challenge"
    assert preview.store_name == "Яндекс Маркет"
    assert (
        preview.url
        == "https://market.yandex.ru/product--umnye-chasy-apple-watch-series-9/987654321"
    )
    assert preview.title == "Смотри какие часы на Маркете"
    assert "почти готово" not in (preview.title or "").lower()


@pytest.mark.asyncio
async def test_replay_missing_interaction_raises_cassette_miss_error_and_blocks_network() -> None:
    """Unrecorded URL in REPLAY mode must raise CassetteMissError without network fallback."""
    cassettes = _load_cassettes_module()
    clear_dns_cache()

    cassette_path = CASSETTES_DIR / "ozon_product.yaml"
    service = ItemPreviewService()
    unrecorded_url = "https://ozon.ru/product/unrecorded-product-999999999/?utm_source=share"

    async with cassettes.cassette_client(
        cassette_path,
        mode=cassettes.CassetteMode.REPLAY,
    ) as client:
        with pytest.raises(cassettes.CassetteMissError) as exc_info:
            await service.fetch_preview(unrecorded_url, client=client)

        assert exc_info.value.method == "GET"
        assert "unrecorded-product-999999999" in exc_info.value.uri

        with pytest.raises(cassettes.CassetteMissError):
            await service.url_metadata_service.fetch_and_extract(unrecorded_url, client=client)


@pytest.mark.asyncio
async def test_record_and_refresh_modes_sanitize_headers_cookies_and_tracking_params(
    tmp_path: Path,
) -> None:
    """RECORD and REFRESH modes must strip cookies, auth headers, tokens, and tracking params."""
    cassettes = _load_cassettes_module()
    clear_dns_cache()

    cassette_file = tmp_path / "ozon_custom.yaml"
    call_count = 0
    current_price = "19990"

    def _origin_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        html = f"""<!DOCTYPE html>
        <html lang="ru">
        <head>
          <meta charset="utf-8">
          <title>Тестовая колонка — купить на OZON</title>
          <meta property="og:site_name" content="Ozon">
          <meta property="og:title" content="Тестовая колонка — Ozon">
          <meta property="og:image" content="https://ir.ozone.ru/speaker.jpg">
          <meta property="product:price:amount" content="{current_price}">
          <meta property="product:price:currency" content="RUB">
        </head>
        <body><h1>Тестовая колонка</h1></body>
        </html>"""
        return httpx.Response(
            status_code=200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Set-Cookie": "__Secure-ab-token=super_secret_cookie_value; Path=/; HttpOnly",
                "X-Auth-Token": "origin_secret_auth_token",
                "X-Session-Id": "sess_987654321",
            },
            text=html,
            request=request,
        )

    mock_origin = httpx.MockTransport(_origin_handler)
    dirty_record_url = "https://ozon.ru/product/testovaya-kolonka-555/?sku=42&utm_source=tg&token=secret_query_token"

    # 1. RECORD mode records interaction via inner_transport and writes sanitized YAML
    cassette = cassettes.Cassette(marketplace="ozon", scenario="product")
    record_transport = cassettes.CassetteTransport(
        cassette,
        mode=cassettes.CassetteMode.RECORD,
        cassette_path=cassette_file,
        inner_transport=mock_origin,
    )
    async with httpx.AsyncClient(transport=record_transport) as direct_client:
        resp = await direct_client.get(
            dirty_record_url,
            headers={
                "User-Agent": "WishenkaBot/1.0",
                "Cookie": "session_token=client_cookie_secret",
                "Authorization": "Bearer top_secret_bearer_token",
                "X-Api-Key": "api_key_secret_123",
                "X-Csrf-Token": "csrf_secret_456",
                "CF-Connecting-IP": "203.0.113.55",
            },
        )
        assert resp.status_code == 200

    assert call_count == 1
    assert cassette_file.is_file()
    raw_yaml_text = cassette_file.read_text(encoding="utf-8")

    # Verify sensitive secrets and tracking params were stripped from the persisted file
    for forbidden_secret in (
        "super_secret_cookie_value",
        "origin_secret_auth_token",
        "sess_987654321",
        "client_cookie_secret",
        "top_secret_bearer_token",
        "api_key_secret_123",
        "csrf_secret_456",
        "203.0.113.55",
        "secret_query_token",
        "utm_source",
    ):
        assert forbidden_secret not in raw_yaml_text

    # Non-tracking functional query parameter must be preserved
    assert "https://ozon.ru/product/testovaya-kolonka-555/?sku=42" in raw_yaml_text

    # 2. REPLAY mode uses the recorded cassette offline without calling inner_transport
    service = ItemPreviewService()
    async with cassettes.cassette_client(
        cassette_file,
        mode=cassettes.CassetteMode.REPLAY,
    ) as replay_client:
        preview = await service.fetch_preview(
            "https://ozon.ru/product/testovaya-kolonka-555/?sku=42&utm_medium=cpc",
            client=replay_client,
        )

    assert call_count == 1
    assert preview.is_fallback is False
    assert preview.title == "Тестовая колонка"
    assert preview.price == 19990
    assert preview.currency == "RUB"
    assert preview.store_name == "Ozon"

    # 3. REFRESH mode re-fetches and updates the cassette on disk
    current_price = "17490"
    async with cassettes.cassette_client(
        cassette_file,
        mode=cassettes.CassetteMode.REFRESH,
        inner_transport=mock_origin,
    ) as refresh_client:
        refreshed_preview = await service.fetch_preview(
            "https://ozon.ru/product/testovaya-kolonka-555/?sku=42",
            client=refresh_client,
        )

    assert call_count == 2
    assert refreshed_preview.is_fallback is False
    assert refreshed_preview.price == 17490


def test_cli_record_refresh_and_verify_entrypoint(tmp_path: Path) -> None:
    """CLI must support --mode record|refresh (--url/--output or directory) and --verify."""
    cassettes = _load_cassettes_module()
    clear_dns_cache()

    cassette_file = tmp_path / "wildberries_product.yaml"
    current_price = "4990"
    call_count = 0

    def _origin_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        html = f"""<!DOCTYPE html>
        <html lang="ru">
        <head>
          <meta charset="utf-8">
          <title>Умная лампа — купить в интернет-магазине Wildberries</title>
          <meta property="og:site_name" content="Wildberries">
          <meta property="og:title" content="Умная лампа">
          <meta property="og:image" content="https://basket-01.wbbasket.ru/lamp.webp">
          <meta property="product:price:amount" content="{current_price}">
          <meta property="product:price:currency" content="RUB">
        </head>
        <body><h1>Умная лампа</h1></body>
        </html>"""
        return httpx.Response(
            status_code=200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Set-Cookie": "wbx_secret=should_be_stripped; Path=/; HttpOnly",
            },
            text=html,
            request=request,
        )

    mock_origin = httpx.MockTransport(_origin_handler)

    # 1. CLI --mode record --url <url> --output <path>
    rc_record = cassettes.main(
        [
            "--mode",
            "record",
            "--url",
            "https://www.wildberries.ru/catalog/777888999/detail.aspx?utm_source=share&token=secret123",
            "--output",
            str(cassette_file),
            "--marketplace",
            "wildberries",
            "--scenario",
            "product",
        ],
        inner_transport=mock_origin,
    )
    assert rc_record == 0
    assert call_count == 1
    assert cassette_file.is_file()

    recorded_text = cassette_file.read_text(encoding="utf-8")
    assert "should_be_stripped" not in recorded_text
    assert "secret123" not in recorded_text
    assert "utm_source" not in recorded_text
    assert "4990" in recorded_text

    # 2. CLI --mode refresh --cassettes-dir <dir> updates all cassettes in directory
    current_price = "3590"
    rc_refresh = cassettes.main(
        [
            "--mode",
            "refresh",
            "--cassettes-dir",
            str(tmp_path),
        ],
        inner_transport=mock_origin,
    )
    assert rc_refresh == 0
    assert call_count == 2
    refreshed_text = cassette_file.read_text(encoding="utf-8")
    assert "3590" in refreshed_text

    # 3. CLI --verify runs offline against the recorded directory
    rc_verify = cassettes.main(
        [
            "--verify",
            "--cassettes-dir",
            str(tmp_path),
        ]
    )
    assert rc_verify == 0
    assert call_count == 2


@pytest.mark.asyncio
async def test_cassette_and_antibot_structured_logging_observability(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured log events for load/save/replay-hit/miss/record/refresh and anti-bot."""
    import logging

    cassettes = _load_cassettes_module()
    clear_dns_cache()
    service = ItemPreviewService()

    # 1. Replay hit + 200 OK Russian anti-bot challenge detection (Yandex SmartCaptcha)
    yandex_antibot_path = CASSETTES_DIR / "yandex_market_antibot.yaml"
    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        async with cassettes.cassette_client(
            yandex_antibot_path,
            mode=cassettes.CassetteMode.REPLAY,
        ) as client:
            preview = await service.fetch_preview(
                "https://market.yandex.ru/product--umnye-chasy-apple-watch-series-9/987654321?clid=900",
                client=client,
            )

    assert preview.is_fallback is True
    assert preview.fallback_reason == "anti_bot_challenge"

    loaded_records = [r for r in caplog.records if getattr(r, "event", None) == "cassette_loaded"]
    assert len(loaded_records) == 1
    assert loaded_records[0].levelname == "DEBUG"
    assert getattr(loaded_records[0], "marketplace", None) == "yandex_market"
    assert getattr(loaded_records[0], "scenario", None) == "antibot"
    assert getattr(loaded_records[0], "interactions_count", None) == 1

    hit_records = [r for r in caplog.records if getattr(r, "event", None) == "cassette_replay_hit"]
    assert len(hit_records) == 1
    assert hit_records[0].levelname == "DEBUG"
    assert getattr(hit_records[0], "method", None) == "GET"
    assert getattr(hit_records[0], "status_code", None) == 200
    assert getattr(hit_records[0], "mode", None) == "replay"
    assert getattr(hit_records[0], "marketplace", None) == "yandex_market"
    assert getattr(hit_records[0], "scenario", None) == "antibot"

    anti_bot_warn_records = [
        r for r in caplog.records if getattr(r, "event", None) == "item_preview_anti_bot"
    ]
    assert len(anti_bot_warn_records) == 1
    assert anti_bot_warn_records[0].levelname == "WARNING"
    assert getattr(anti_bot_warn_records[0], "status_code", None) == 200
    assert getattr(anti_bot_warn_records[0], "url_domain", None) == "market.yandex.ru"
    assert getattr(anti_bot_warn_records[0], "fallback_reason", None) == "anti_bot_challenge"

    anti_bot_info_records = [
        r for r in caplog.records if getattr(r, "event", None) == "anti_bot_challenge_detected"
    ]
    assert len(anti_bot_info_records) == 1
    assert anti_bot_info_records[0].levelname == "INFO"
    assert getattr(anti_bot_info_records[0], "status_code", None) == 200
    assert getattr(anti_bot_info_records[0], "url_domain", None) == "market.yandex.ru"
    assert getattr(anti_bot_info_records[0], "fallback_reason", None) == "anti_bot_challenge"

    # 2. Replay miss logs sanitized WARNING without leaking secret query tokens
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        async with cassettes.cassette_client(
            CASSETTES_DIR / "ozon_product.yaml",
            mode=cassettes.CassetteMode.REPLAY,
        ) as client:
            with pytest.raises(cassettes.CassetteMissError):
                await service.fetch_preview(
                    "https://ozon.ru/product/missing-item-777/?token=super_secret_miss_token&utm_source=tg",
                    client=client,
                )

    miss_records = [r for r in caplog.records if getattr(r, "event", None) == "cassette_miss"]
    assert len(miss_records) == 1
    assert miss_records[0].levelname == "WARNING"
    assert getattr(miss_records[0], "method", None) == "GET"
    assert getattr(miss_records[0], "uri", None) == "https://ozon.ru/product/missing-item-777/"
    assert "super_secret_miss_token" not in miss_records[0].getMessage()
    assert "utm_source" not in miss_records[0].getMessage()

    # 3. Record and Refresh emit structured cassette_recorded / cassette_refreshed / cassette_saved
    #    without dumping HTML bodies or sensitive secrets into logs
    caplog.clear()
    custom_cassette_path = tmp_path / "avito_recorded.yaml"

    def _mock_origin_handler(request: httpx.Request) -> httpx.Response:
        html = """<!DOCTYPE html>
        <html lang="ru">
        <head>
          <title>Велосипед горный — объявление на Авито</title>
          <meta property="og:title" content="Велосипед горный">
          <meta property="product:price:amount" content="24900">
          <meta property="product:price:currency" content="RUB">
        </head>
        <body><div>LARGE_HTML_PAYLOAD_DO_NOT_LOG</div></body>
        </html>"""
        return httpx.Response(
            status_code=200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Set-Cookie": "sessid=secret_avito_cookie; Path=/; HttpOnly",
            },
            text=html,
            request=request,
        )

    mock_origin = httpx.MockTransport(_mock_origin_handler)
    _dns_cache.put("www.avito.ru", 443, ["93.184.216.34"])

    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        async with cassettes.cassette_client(
            custom_cassette_path,
            mode=cassettes.CassetteMode.RECORD,
            inner_transport=mock_origin,
            marketplace="avito",
            scenario="product",
        ) as record_client:
            recorded_dto = await service.fetch_preview(
                "https://www.avito.ru/moskva/velosipedy/gornyy_111?token=secret_q_token&src=sharing",
                client=record_client,
            )

        async with cassettes.cassette_client(
            custom_cassette_path,
            mode=cassettes.CassetteMode.REFRESH,
            inner_transport=mock_origin,
        ) as refresh_client:
            refreshed_dto = await service.fetch_preview(
                "https://www.avito.ru/moskva/velosipedy/gornyy_111",
                client=refresh_client,
            )

    assert recorded_dto.is_fallback is False
    assert refreshed_dto.is_fallback is False

    recorded_records = [
        r for r in caplog.records if getattr(r, "event", None) == "cassette_recorded"
    ]
    assert len(recorded_records) == 1
    assert recorded_records[0].levelname == "INFO"
    assert getattr(recorded_records[0], "mode", None) == "record"
    assert getattr(recorded_records[0], "status_code", None) == 200
    assert (
        getattr(recorded_records[0], "uri", None)
        == "https://www.avito.ru/moskva/velosipedy/gornyy_111"
    )

    refreshed_records = [
        r for r in caplog.records if getattr(r, "event", None) == "cassette_refreshed"
    ]
    assert len(refreshed_records) == 1
    assert refreshed_records[0].levelname == "INFO"
    assert getattr(refreshed_records[0], "mode", None) == "refresh"
    assert getattr(refreshed_records[0], "status_code", None) == 200

    saved_records = [r for r in caplog.records if getattr(r, "event", None) == "cassette_saved"]
    assert len(saved_records) == 2
    assert all(r.levelname == "DEBUG" for r in saved_records)

    cassette_events = {
        "cassette_loaded",
        "cassette_saved",
        "cassette_replay_hit",
        "cassette_miss",
        "cassette_recorded",
        "cassette_refreshed",
    }
    for rec in caplog.records:
        msg = rec.getMessage()
        assert "LARGE_HTML_PAYLOAD_DO_NOT_LOG" not in msg
        assert "secret_avito_cookie" not in msg
        if getattr(rec, "event", None) in cassette_events:
            assert "secret_q_token" not in msg
            assert "secret_q_token" not in str(getattr(rec, "uri", ""))
