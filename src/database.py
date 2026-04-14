from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Generator

from src.config import db_path


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    p = Path(db_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as c:
        c.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS gemi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad TEXT NOT NULL,
                kod TEXT UNIQUE
            );

            CREATE TABLE IF NOT EXISTS makine_tipi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS personel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad TEXT NOT NULL,
                soyad TEXT NOT NULL,
                gemi_id INTEGER REFERENCES gemi(id),
                makine_tipi_id INTEGER REFERENCES makine_tipi(id),
                vardiya_tipi TEXT NOT NULL CHECK(vardiya_tipi IN ('SABIT','GRUPCU','8_5')),
                vardiya_gunleri TEXT,
                aktif INTEGER NOT NULL DEFAULT 1,
                gemiden_cekilme INTEGER NOT NULL DEFAULT 0,
                carkci_ile_sorun INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS izin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personel_id INTEGER NOT NULL REFERENCES personel(id) ON DELETE CASCADE,
                baslangic TEXT NOT NULL,
                bitis TEXT NOT NULL,
                gun_sayisi INTEGER NOT NULL,
                notlar TEXT
            );

            CREATE TABLE IF NOT EXISTS carkci (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad TEXT NOT NULL,
                soyad TEXT NOT NULL,
                gemi_id INTEGER REFERENCES gemi(id),
                problemli_yagci_id INTEGER REFERENCES personel(id),
                sorun_metni TEXT,
                vardiya_notu TEXT
            );
            """
        )
        mevcut_kolonlar = {row["name"] for row in c.execute("PRAGMA table_info(personel)").fetchall()}
        ek_kolonlar = [
            ("gemi_tutumu", "TEXT"),
            ("izin_tercih_gunleri", "TEXT"),
            ("izin_saat_araligi", "TEXT"),
            ("is_kalitesi", "INTEGER NOT NULL DEFAULT 3"),
            ("performans_notu", "TEXT"),
        ]
        for kolon_adi, kolon_tipi in ek_kolonlar:
            if kolon_adi not in mevcut_kolonlar:
                c.execute(f"ALTER TABLE personel ADD COLUMN {kolon_adi} {kolon_tipi}")


def sql_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with get_conn() as c:
        return list(c.execute(query, params).fetchall())


def sql_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with get_conn() as c:
        return c.execute(query, params).fetchone()


def sql_run(query: str, params: tuple[Any, ...] = ()) -> int:
    with get_conn() as c:
        cur = c.execute(query, params)
        return int(cur.lastrowid or 0)


def gun_sayisi(bas: date, bit: date) -> int:
    if bit < bas:
        return 0
    return (bit - bas).days + 1
