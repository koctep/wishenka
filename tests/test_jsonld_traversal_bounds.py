"""Regression checks for bounded JSON-LD discovery and type inspection."""

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from wishenka.items.parser import HtmlMetadataExtractor
from wishenka.logging import JsonFormatter

pytestmark = pytest.mark.timeout(30)


class CountingList(list[Any]):
    """Count elements retrieved through either traversal direction."""

    def __init__(self, values: list[Any]) -> None:
        super().__init__(values)
        self.reads = 0

    def __iter__(self) -> Iterator[Any]:
        for value in super().__iter__():
            self.reads += 1
            yield value

    def __reversed__(self) -> Iterator[Any]:
        for value in super().__reversed__():
            self.reads += 1
            yield value


class CountingDict(dict[str, Any]):
    """Count values obtained when iterating the mapping's items."""

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(values)
        self.reads = 0

    def items(self) -> Any:
        for item in super().items():
            self.reads += 1
            yield item


def test_wide_list_does_not_schedule_beyond_discovery_budget() -> None:
    product = {"@type": "Product", "name": "first"}
    values = CountingList([product, *([None] * 30_000)])

    assert HtmlMetadataExtractor._find_jsonld_products(values) == [product]
    assert values.reads <= 20_000


def test_wide_mapping_does_not_materialize_all_items() -> None:
    product = {"@type": "Product", "name": "first"}
    values = CountingDict({"first": product, **{f"k{i}": None for i in range(30_000)}})

    assert HtmlMetadataExtractor._find_jsonld_products(values) == [product]
    assert values.reads <= 20_000


def test_type_inspection_stops_reading_wide_list_at_first_match() -> None:
    types = CountingList(["Product", *(["Offer"] * 30_000)])

    assert HtmlMetadataExtractor._is_product_type(types)
    assert types.reads <= 2


def test_repeated_scalar_types_are_inspected_once_per_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = HtmlMetadataExtractor._is_product_type
    calls: list[Any] = []

    def count(value: Any) -> bool:
        calls.append(value)
        return original(value)

    monkeypatch.setattr(HtmlMetadataExtractor, "_is_product_type", staticmethod(count))
    products = [{"@type": "Product"} for _ in range(100)]
    assert HtmlMetadataExtractor._find_jsonld_products(products) == products
    assert calls.count("Product") == 1


def test_repeated_list_identity_is_inspected_once_per_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = HtmlMetadataExtractor._is_product_type
    calls: list[Any] = []

    def count(value: Any) -> bool:
        calls.append(value)
        return original(value)

    monkeypatch.setattr(HtmlMetadataExtractor, "_is_product_type", staticmethod(count))
    shared_type = ["Offer", "Product"]
    products = [{"@type": shared_type} for _ in range(100)]
    assert HtmlMetadataExtractor._find_jsonld_products(products) == products
    assert sum(value is shared_type for value in calls) == 1


def test_graph_first_order_and_node_budget_boundary() -> None:
    graph_product = {"@type": "Product", "name": "graph"}
    root = {"@type": "Product", "name": "root", "@graph": [graph_product]}
    assert HtmlMetadataExtractor._find_jsonld_products(root) == [graph_product, root]

    last = {"@type": "Product"}
    assert HtmlMetadataExtractor._find_jsonld_products([*([None] * 19_997), last]) == [last]
    assert HtmlMetadataExtractor._find_jsonld_products([*([None] * 19_998), last]) == []


def test_depth_limit_preserves_visitable_node_and_skips_deeper_product() -> None:
    product = {"@type": "Product"}
    at_limit: Any = product
    for _ in range(128):
        at_limit = [at_limit]
    assert HtmlMetadataExtractor._find_jsonld_products(at_limit) == [product]
    assert HtmlMetadataExtractor._find_jsonld_products([at_limit]) == []


@pytest.mark.parametrize("kind", ["list", "mapping"])
def test_wide_containers_keep_temporary_traversal_memory_bounded(kind: str) -> None:
    import tracemalloc

    product = {"@type": "Product"}
    data: Any = (
        [product, *([None] * 30_000)]
        if kind == "list"
        else {"first": product, **{f"k{i}": None for i in range(30_000)}}
    )
    tracemalloc.start()
    try:
        result = HtmlMetadataExtractor._find_jsonld_products(data)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result == [product]
    assert peak < 512 * 1024


@pytest.mark.parametrize(
    ("match_index", "expected"), [(19_997, True), (19_998, True), (19_999, False)]
)
def test_type_walk_obeys_visit_boundary(match_index: int, expected: bool) -> None:
    # Root list consumes one visit; item at index 19,998 is visit 20,000.
    types = ["Offer"] * 20_000
    types[match_index] = "Product"
    assert HtmlMetadataExtractor._is_product_type(types) is expected


@pytest.mark.parametrize(("depth", "expected"), [(127, True), (128, True), (129, False)])
def test_type_walk_obeys_depth_boundary(depth: int, expected: bool) -> None:
    value: Any = "Product"
    for _ in range(depth):
        value = [value]
    assert HtmlMetadataExtractor._is_product_type(value) is expected


def test_type_walk_returns_early_before_out_of_budget_match() -> None:
    types = ["Product", *(["Offer"] * 20_000), "Product"]
    assert HtmlMetadataExtractor._is_product_type(types)


@pytest.mark.parametrize(("walk", "limit"), [("discovery", 262), ("type", 131)])
@pytest.mark.parametrize("kind", ["wide", "deep"])
def test_walk_pending_records_are_bounded(walk: str, limit: int, kind: str) -> None:
    # Private diagnostic runs the real walker and returns (result, peak pending records).
    # It must count actual pending records per invocation, not infer them from output size.
    inspect_walk = getattr(HtmlMetadataExtractor, "_jsonld_traversal_diagnostics", None)
    assert callable(inspect_walk), "per-call pending-record diagnostics are not implemented"

    if kind == "wide":
        data: Any = ["Offer"] * 30_000 if walk == "type" else [None] * 30_000
    else:
        data = "Offer" if walk == "type" else None
        for _ in range(129):
            data = [data] if walk == "type" else {"child": data}

    result, peak_pending = inspect_walk(walk, data)
    assert result is False if walk == "type" else result == []
    assert isinstance(peak_pending, int)
    assert 0 < peak_pending <= limit


def test_memo_preserves_limit_logging_and_is_local_to_each_discovery(
    caplog: pytest.LogCaptureFixture,
) -> None:
    shared: Any = "Offer"
    for _ in range(129):
        shared = [shared]
    data = [{"@type": shared}, {"@type": shared}]
    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        assert HtmlMetadataExtractor._find_jsonld_products(data) == []
        assert HtmlMetadataExtractor._find_jsonld_products(data) == []
    events = [r for r in caplog.records if getattr(r, "event", None) == "jsonld_type_limit"]
    assert [r.__dict__["visited_nodes"] for r in events] == [130] * 4


def test_discovery_and_graph_logging_emit_debug_metadata_without_raw_payloads(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "secret-jsonld-node-payload"
    wide_graph = {"@graph": [{"@type": "Product", "name": secret}, *([None] * 20_000)]}
    deep_node: Any = {"@type": secret, "child": {"nested": secret}}
    for _ in range(128):
        deep_node = {"child": deep_node}

    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        wide_products = HtmlMetadataExtractor._find_jsonld_products(wide_graph)
        deep_products = HtmlMetadataExtractor._find_jsonld_products(deep_node)

    assert len(wide_products) == 1
    assert deep_products == []

    graph_events = [
        r for r in caplog.records if getattr(r, "event", None) == "jsonld_graph_traversal"
    ]
    assert len(graph_events) == 1
    assert graph_events[0].levelname == "DEBUG"
    assert graph_events[0].__dict__["graph_items_count"] == 20_001

    limit_events = [
        r for r in caplog.records if getattr(r, "event", None) == "jsonld_discovery_limit"
    ]
    assert [r.levelname for r in limit_events] == ["DEBUG", "DEBUG"]
    assert [r.__dict__["visited_nodes"] for r in limit_events] == [20_000, 131]

    formatter = JsonFormatter()
    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in str(record.__dict__)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "DEBUG"
        assert "event" in parsed["extra"]
        assert secret not in json.dumps(parsed)


def test_type_visit_limit_logging_replays_on_memo_hit_without_payloads(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "secret-type-token"
    wide_types = [secret] * 20_000
    # Place both candidates at depth 128 so discovery stops at wide_types (depth 129)
    # and reaches the second dict to exercise memo replay of the 20,000-visit limit.
    data: Any = [{"@type": wide_types}, {"@type": wide_types}]
    for _ in range(127):
        data = [data]

    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        assert HtmlMetadataExtractor._find_jsonld_products(data) == []

    events = [r for r in caplog.records if getattr(r, "event", None) == "jsonld_type_limit"]
    assert [r.levelname for r in events] == ["DEBUG", "DEBUG"]
    assert [r.__dict__["visited_nodes"] for r in events] == [20_000, 20_000]
    assert secret not in caplog.text
    assert all(secret not in str(record.__dict__) for record in caplog.records)
