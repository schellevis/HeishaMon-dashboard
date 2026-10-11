"""Pure coverage and rollup maths (spec §5.2). All timestamps are unix ms UTC.

A topic is covered at instant t when a valid value is known by LOCF and t lies in no applicable
outage. Intervals are half-open [start, end).
"""
from typing import Iterable, Sequence

MINUTE_MS = 60_000
HOUR_MS = 3_600_000

# (ts, valid, value) sorted by ts; value is a float for numeric topics, a string for text
SampleT = tuple[int, bool, object]
# (bucket, first_ts, last_ts, covered_seconds, avg, min, max, last)
Row = tuple[int, int | None, int | None, float, float | None, float | None, float | None, float | None]


def merge_outages(outages: Iterable[tuple[int, int | None]], a: int, b: int) -> list[tuple[int, int]]:
    """Clip outages (end None = open) to [a, b), drop empties and merge overlaps."""
    clipped = []
    for start, end in outages:
        s = max(start, a)
        e = b if end is None else min(end, b)
        if e > s:
            clipped.append((s, e))
    clipped.sort()
    merged: list[tuple[int, int]] = []
    for s, e in clipped:
        if merged and s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def covered_segments(
    samples: Sequence[SampleT], outages: Iterable[tuple[int, int | None]], a: int, b: int
) -> list[tuple[int, int, object]]:
    """Covered (start, end, value) pieces inside [a, b). `samples` may start with a carry-in
    sample before `a`; an invalid sample ends coverage until the next valid one."""
    segs: list[tuple[int, int, object]] = []
    n = len(samples)
    for i, (ts, valid, val) in enumerate(samples):
        if not valid:
            continue
        s = max(ts, a)
        e = b if i + 1 >= n else min(samples[i + 1][0], b)
        if e > s:
            segs.append((s, e, val))
    holes = merge_outages(outages, a, b)
    if not holes or not segs:
        return segs
    out: list[tuple[int, int, object]] = []
    j = 0
    for s, e, v in segs:
        cur = s
        while j < len(holes) and holes[j][1] <= cur:
            j += 1
        k = j
        while k < len(holes) and holes[k][0] < e:
            hs, he = holes[k]
            if hs > cur:
                out.append((cur, hs, v))
            cur = max(cur, he)
            if cur >= e:
                break
            k += 1
        if cur < e:
            out.append((cur, e, v))
    return out


def raw_intervals(segments: Sequence[tuple[int, int, object]]) -> list[list[int]]:
    """Covered intervals (adjacent pieces merged) as [[start, end], ...]."""
    out: list[list[int]] = []
    for s, e, _ in segments:
        if out and out[-1][1] == s:
            out[-1][1] = e
        else:
            out.append([s, e])
    return out


def bucket_rows(
    segments: Sequence[tuple[int, int, float]], a: int, b: int, size_ms: int = MINUTE_MS
) -> list[Row]:
    """One row per bucket whose start lies in [a, b) (a aligned to the bucket size), zero-coverage
    buckets included with NULL aggregates. Bucket number = ms // size_ms."""
    first_bucket = a // size_ms
    last_bucket = (b - 1) // size_ms
    if last_bucket < first_bucket:
        return []
    acc: dict[int, list] = {}
    for s, e, v in segments:
        bk = s // size_ms
        while bk * size_ms < e:
            lo = max(s, bk * size_ms)
            hi = min(e, (bk + 1) * size_ms)
            if hi > lo:
                x = acc.get(bk)
                if x is None:
                    acc[bk] = [hi - lo, v * (hi - lo), v, v, v, lo, hi]
                else:
                    x[0] += hi - lo
                    x[1] += v * (hi - lo)
                    x[2] = min(x[2], v)
                    x[3] = max(x[3], v)
                    x[4] = v
                    x[6] = hi
            bk += 1
    rows: list[Row] = []
    for bk in range(first_bucket, last_bucket + 1):
        x = acc.get(bk)
        if x is None:
            rows.append((bk, None, None, 0.0, None, None, None, None))
        else:
            rows.append((bk, x[5], x[6], x[0] / 1000.0, x[1] / x[0], x[2], x[3], x[4]))
    return rows


def aggregate_rows(rows: Sequence[Row], factor: int = 60) -> list[Row]:
    """Coverage-weighted aggregation of finer rows into buckets `factor` times coarser."""
    groups: dict[int, list[Row]] = {}
    for r in rows:
        groups.setdefault(r[0] // factor, []).append(r)
    out: list[Row] = []
    for bk in sorted(groups):
        covered = 0.0
        weighted = 0.0
        mn = mx = last = first_ts = last_ts = None
        for r in sorted(groups[bk]):
            if r[3] <= 0 or r[4] is None:
                continue
            covered += r[3]
            weighted += r[4] * r[3]
            mn = r[5] if mn is None else min(mn, r[5])
            mx = r[6] if mx is None else max(mx, r[6])
            last = r[7]
            first_ts = r[1] if first_ts is None else first_ts
            last_ts = r[2]
        if covered <= 0:
            out.append((bk, None, None, 0.0, None, None, None, None))
        else:
            out.append((bk, first_ts, last_ts, covered, weighted / covered, mn, mx, last))
    return out
