"""Protected records: commands, events, prefs and the budget that keeps them (spec §5.1)."""
import json
import sqlite3
from typing import Any

from .sqlite import locked

RESERVED_SLOTS = 66  # 64 terminal command updates + 2 saturation records (spec §5.1)
DETAIL_MAX_BYTES = 2048
COMMAND_COLS = (
    "submitted_ts", "published_ts", "name", "payload", "retained", "class", "prev_value",
    "status", "confirmed_ts", "attempts", "detail", "keys",
)


class StorageUnavailable(RuntimeError):
    """The protected-record budget is saturated; new commands are refused (503 storage_unavailable)."""


def _trunc(text: str | None) -> str | None:
    if text is None:
        return None
    raw = text.encode("utf-8")
    if len(raw) <= DETAIL_MAX_BYTES:
        return text
    return raw[:DETAIL_MAX_BYTES].decode("utf-8", errors="ignore")


def _detail_json(detail: Any) -> str:
    text = json.dumps(detail if detail is not None else {}, separators=(",", ":"))
    if len(text.encode("utf-8")) <= DETAIL_MAX_BYTES:
        return text
    return json.dumps({"truncated": True, "text": _trunc(text)[: DETAIL_MAX_BYTES - 64]})


def _bounded_detail(detail: Any) -> dict:
    """Event detail as it will be stored: oversize details are cut before they are buffered."""
    if detail is None:
        return {}
    if len(json.dumps(detail, separators=(",", ":")).encode("utf-8")) <= DETAIL_MAX_BYTES:
        return detail
    return json.loads(_detail_json(detail))


def command_from_row(row: sqlite3.Row | tuple) -> dict:
    d = dict(zip(("uuid",) + COMMAND_COLS, row))
    d["retained"] = bool(d["retained"])
    d["keys"] = json.loads(d["keys"]) if d["keys"] else None
    return d


def command_select() -> str:
    return "SELECT uuid, " + ", ".join(f'"{c}"' for c in COMMAND_COLS) + " FROM commands"


class RecordsMixin:
    def _init_records(self, audit_buffer_max: int) -> None:
        self._audit_max = audit_buffer_max
        self._cmds_new: dict[str, dict] = {}
        self._cmd_upd: dict[str, dict] = {}
        self._events: list[dict] = []
        self._agg: dict[str, dict] = {}
        self._events_dropped: dict | None = None
        self._sat = False

    def _clear_records(self) -> None:
        self._cmds_new.clear()
        self._cmd_upd.clear()
        self._events.clear()
        self._agg.clear()
        self._events_dropped = None
        self._sat = False
        self._sat_outage = None

    # ---------------------------------------------------------------- budget

    @property
    def saturated(self) -> bool:
        return self._sat

    @locked
    def audit_count(self) -> int:
        return (
            len(self._cmds_new) + len(self._cmd_upd) + len(self._events)
            + sum(1 for o in self._outages if o.rowid is None)
        )

    def protected_budget_ok(self) -> bool:
        return not self._sat

    def _maybe_saturate(self, ts: int) -> None:
        if self._sat or self.audit_count() < self._audit_max - RESERVED_SLOTS:
            return
        self._sat = True
        self._sat_outage = self._new_outage("dropped", ts, None, reserved=True)
        self._sat_outage.saturation = True

    # ---------------------------------------------------------------- events

    def _note_dropped_event(self, ts: int, kind: str) -> None:
        ev = self._events_dropped
        if ev is None:
            ev = {"ts": ts, "kind": "events_dropped", "detail": {"count": 0, "kinds": {}}}
            self._events_dropped = ev
            self._events.append(ev)  # reserved slot
        ev["detail"]["count"] += 1
        ev["detail"]["kinds"][kind] = ev["detail"]["kinds"].get(kind, 0) + 1

    @locked
    def append_event(self, ts: int, kind: str, detail: dict | None = None) -> bool:
        if self._sat:
            self._note_dropped_event(ts, kind)
            return False
        self._events.append({"ts": ts, "kind": kind, "detail": _bounded_detail(detail)})
        self._maybe_saturate(ts)
        return True

    def _agg_event(self, kind: str, ts: int, make: dict, mutate) -> None:
        """One buffered event per kind and flush cycle, updated in place."""
        ev = self._agg.get(kind)
        if ev is not None:
            mutate(ev["detail"])
            return
        if self._sat:
            self._note_dropped_event(ts, kind)
            return
        ev = {"ts": ts, "kind": kind, "detail": make}
        self._events.append(ev)
        self._agg[kind] = ev
        self._maybe_saturate(ts)

    # -------------------------------------------------------------- commands

    @locked
    def append_command(self, record: dict) -> None:
        if self._sat:
            raise StorageUnavailable("protected-record budget is full")
        rec = dict(record)
        rec["detail"] = _trunc(rec.get("detail"))
        self._cmds_new[rec["uuid"]] = rec
        self._maybe_saturate(rec.get("submitted_ts") or 0)

    @locked
    def update_command(self, uuid: str, fields: dict) -> None:
        fields = dict(fields)
        if "detail" in fields:
            fields["detail"] = _trunc(fields["detail"])
        if uuid in self._cmds_new:
            self._cmds_new[uuid].update(fields)
        elif uuid in self._cmd_upd:
            self._cmd_upd[uuid].update(fields)
        else:
            self._cmd_upd[uuid] = fields  # uses a reserved slot at the boundary

    # ----------------------------------------------------------------- prefs

    @locked
    def prefs_get(self) -> dict:
        return {k: json.loads(v) for k, v in self._conn.execute("SELECT key, value FROM prefs")}

    @locked
    def prefs_put(self, prefs: dict) -> None:
        """Written immediately in its own small transaction (spec §5.1)."""
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        try:
            for k, v in prefs.items():
                c.execute("INSERT OR REPLACE INTO prefs (key, value) VALUES (?, ?)", (k, json.dumps(v)))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    # ----------------------------------------------------------------- flush

    def _write_commands(self, c) -> None:
        for rec in self._cmds_new.values():
            keys_json = rec.get("keys")
            if keys_json is not None and not isinstance(keys_json, str):
                keys_json = json.dumps(keys_json, separators=(",", ":"))
            c.execute(
                "INSERT OR REPLACE INTO commands (uuid, " + ", ".join(f'"{x}"' for x in COMMAND_COLS)
                + ") VALUES (?" + ", ?" * len(COMMAND_COLS) + ")",
                (rec["uuid"],) + tuple(
                    keys_json if col == "keys" else (int(rec[col]) if col == "retained" and rec.get(col) is not None else rec.get(col))
                    for col in COMMAND_COLS
                ),
            )
        for uuid, upd in self._cmd_upd.items():
            cols = [col for col in upd if col in COMMAND_COLS]
            if not cols:
                continue
            vals = []
            for col in cols:
                v = upd[col]
                if col == "keys" and v is not None and not isinstance(v, str):
                    v = json.dumps(v, separators=(",", ":"))
                if col == "retained" and v is not None:
                    v = int(v)
                vals.append(v)
            c.execute(
                "UPDATE commands SET " + ", ".join(f'"{col}" = ?' for col in cols) + " WHERE uuid = ?",
                (*vals, uuid),
            )

    def _write_events(self, c, now: int) -> None:
        c.executemany(
            "INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)",
            [(e["ts"], e["kind"], _detail_json(e["detail"])) for e in self._events]
            + [(now, "flush", _detail_json({"samples": len(self._buf)}))],
        )
