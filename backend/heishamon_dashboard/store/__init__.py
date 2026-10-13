"""RAM-buffered SQLite store (spec §5).

Everything is buffered in RAM and written in one transaction per flush. Coverage, outages,
rollups and the protected-record budget follow §5.1-§5.4. Timestamps are unix ms UTC.

`Store` is the facade the rest of the app uses. Its behaviour is split by concern:
`buffer` (RAM samples), `outages`, `records` (commands, events, prefs, budget), `rollups`
(minute/hour maths), `queries` (reads on a second, `query_only` connection) and `sqlite`
(connections, the flush transaction, purge).
"""
import os

from .buffer import BufferMixin, Sample
from .outages import OUTAGE_KINDS, Outage, OutageMixin
from .queries import BREAK_MIN_MS, MINUTE_MAX_SPAN_MS, RAW_MAX_SPAN_MS, QueryMixin
from .records import (
    COMMAND_COLS, DETAIL_MAX_BYTES, RESERVED_SLOTS, RecordsMixin, StorageUnavailable,
)
from .sqlite import FlushResult, SqliteMixin

__all__ = [
    "BREAK_MIN_MS", "COMMAND_COLS", "DETAIL_MAX_BYTES", "FlushResult", "MINUTE_MAX_SPAN_MS",
    "OUTAGE_KINDS", "Outage", "RAW_MAX_SPAN_MS", "RESERVED_SLOTS", "Sample", "StorageUnavailable",
    "Store",
]


class Store(BufferMixin, OutageMixin, RecordsMixin, QueryMixin, SqliteMixin):
    def __init__(
        self,
        db_path: str,
        *,
        buffer_max_entries: int = 200_000,
        buffer_max_bytes: int = 268_435_456,
        audit_buffer_max: int = 10_000,
        raw_retention_days: int | None = None,
    ) -> None:
        self._init_sqlite(db_path, raw_retention_days)
        self._init_buffer(buffer_max_entries, buffer_max_bytes)
        self._init_records(audit_buffer_max)
        self._init_outages()
        self._ignored_on = {
            k for k, v in (self.prefs_get().get("topic_visibility") or {}).items() if v == "ignored"
        }
        self._load_open_outages()

    @classmethod
    def from_config(cls, cfg, filename: str = "heishamon.db") -> "Store":
        os.makedirs(cfg.data_dir, exist_ok=True)
        return cls(
            os.path.join(cfg.data_dir, filename),
            buffer_max_entries=cfg.buffer_max_entries,
            buffer_max_bytes=cfg.buffer_max_bytes,
            audit_buffer_max=cfg.audit_buffer_max,
            raw_retention_days=cfg.raw_retention_days,
        )
