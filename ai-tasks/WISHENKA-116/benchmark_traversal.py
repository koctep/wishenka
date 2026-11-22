import json
import platform
import sys
import time
import tracemalloc
from statistics import median

from wishenka.items.parser import HtmlMetadataExtractor as E

fixtures = {
    "wide_list": [None] * 30000,
    "wide_object": {f"k{i}": None for i in range(30000)},
    "repeated_types": [{"@type": ["Offer"] * 100} for _ in range(500)],
}
print("python", sys.version.replace("\n", " "), "platform", platform.platform())
for name, data in fixtures.items():
    size = len(json.dumps(data, separators=(",", ":")).encode())
    assert size < 2097152
    E._find_jsonld_products(data)
    rows = []
    for _ in range(3):
        tracemalloc.start()
        start = time.perf_counter()
        E._find_jsonld_products(data)
        duration = time.perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append((round(duration, 6), peak))
    print(
        name,
        "bytes",
        size,
        "samples_seconds_peakbytes",
        rows,
        "median_s",
        round(median(x[0] for x in rows), 6),
        "max_peak_bytes",
        max(x[1] for x in rows),
    )
