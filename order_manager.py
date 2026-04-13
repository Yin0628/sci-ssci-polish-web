"""Lightweight order & payment state manager for Streamlit deployment."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("ORDER_DB_PATH", "/tmp/sci_ssci_orders.db"))


@dataclass
class Order:
    order_id: str
    source_chars: int
    provider: str
    model: str
    unit_price_per_1k: float
    min_price_cny: float
    amount_cny: float
    status: str
    channel: str
    payer_note: str
    payment_ref: str
    proof_name: str
    created_at: int
    updated_at: int


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                source_chars INTEGER NOT NULL,
                provider TEXT DEFAULT '',
                model TEXT DEFAULT '',
                unit_price_per_1k REAL DEFAULT 0,
                min_price_cny REAL DEFAULT 0,
                amount_cny REAL NOT NULL,
                status TEXT NOT NULL,
                channel TEXT DEFAULT '',
                payer_note TEXT DEFAULT '',
                payment_ref TEXT DEFAULT '',
                proof_name TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()
        }
        if "provider" not in existing_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN provider TEXT DEFAULT ''")
        if "model" not in existing_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN model TEXT DEFAULT ''")
        if "unit_price_per_1k" not in existing_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN unit_price_per_1k REAL DEFAULT 0")
        if "min_price_cny" not in existing_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN min_price_cny REAL DEFAULT 0")
        conn.commit()


def get_model_pricing(model: str) -> tuple[float, float]:
    """
    Returns (unit_price_per_1k, min_price_cny).
    Default strategy (editable via env):
    - gpt-3.5-turbo: 4 / 1000 chars, min 19
    - deepseek-chat: 5 / 1000 chars, min 25
    - gpt-4o-mini: 7 / 1000 chars, min 29
    - deepseek-reasoner: 10 / 1000 chars, min 45
    - gpt-4o: 16 / 1000 chars, min 69
    """
    defaults = {
        "gpt-3.5-turbo": (4.0, 19.0),
        "deepseek-chat": (5.0, 25.0),
        "gpt-4o-mini": (7.0, 29.0),
        "deepseek-reasoner": (10.0, 45.0),
        "gpt-4o": (16.0, 69.0),
    }

    base_unit, base_min = defaults.get(model, (8.0, 39.0))

    env_unit = os.getenv(f"PRICE_{model.upper().replace('-', '_')}_PER_1K", "")
    env_min = os.getenv(f"PRICE_{model.upper().replace('-', '_')}_MIN", "")

    unit_price = float(env_unit) if env_unit else base_unit
    min_price = float(env_min) if env_min else base_min
    return round(unit_price, 2), round(min_price, 2)


def calc_price_cny(source_chars: int, model: str) -> tuple[float, float, float]:
    unit_price, min_price = get_model_pricing(model)
    units = (source_chars + 999) // 1000
    amount = max(min_price, units * unit_price)
    return round(amount, 2), unit_price, min_price


def create_order(source_chars: int, provider: str, model: str) -> Order:
    init_db()
    now = int(time.time())
    raw = f"{uuid.uuid4().hex}-{source_chars}-{provider}-{model}-{now}".encode("utf-8")
    order_id = hashlib.sha1(raw).hexdigest()[:14].upper()
    amount, unit_price, min_price = calc_price_cny(source_chars, model)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO orders (
                order_id, source_chars, provider, model, unit_price_per_1k, min_price_cny,
                amount_cny, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                order_id,
                source_chars,
                provider,
                model,
                unit_price,
                min_price,
                amount,
                now,
                now,
            ),
        )
        conn.commit()

    return get_order(order_id)


def get_order(order_id: str) -> Optional[Order]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()

    if not row:
        return None

    return Order(
        order_id=row["order_id"],
        source_chars=int(row["source_chars"]),
        provider=row["provider"] or "",
        model=row["model"] or "",
        unit_price_per_1k=float(row["unit_price_per_1k"] or 0),
        min_price_cny=float(row["min_price_cny"] or 0),
        amount_cny=float(row["amount_cny"]),
        status=row["status"],
        channel=row["channel"] or "",
        payer_note=row["payer_note"] or "",
        payment_ref=row["payment_ref"] or "",
        proof_name=row["proof_name"] or "",
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
    )


def submit_payment_claim(
    order_id: str,
    channel: str,
    payer_note: str,
    payment_ref: str,
    proof_name: str,
) -> Optional[Order]:
    init_db()
    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE orders
            SET status='submitted', channel=?, payer_note=?, payment_ref=?, proof_name=?, updated_at=?
            WHERE order_id=?
            """,
            (channel, payer_note.strip()[:120], payment_ref.strip()[:120], proof_name.strip()[:200], now, order_id),
        )
        conn.commit()

    return get_order(order_id)


def mark_order_paid(order_id: str) -> Optional[Order]:
    init_db()
    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE orders SET status='paid', updated_at=? WHERE order_id=?",
            (now, order_id),
        )
        conn.commit()

    return get_order(order_id)
