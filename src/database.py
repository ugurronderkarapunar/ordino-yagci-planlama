from __future__ import annotations

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


def _table_cols(c: sqlite3.Cursor, table: str) -> set[str]:
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(c: sqlite3.Cursor, table: str, col: str, decl: str) -> None:
    if col not in _table_cols(c, table):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _migrate_personel_remove_vardiya_check(c: sqlite3.Cursor) -> None:
    row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='personel'").fetchone()
    ddl = (row[0] or "") if row else ""
    if "CHECK(vardiya_tipi" not in ddl and "check(vardiya_tipi" not in ddl.lower():
        return

    old_cols = [r[1] for r in c.execute("PRAGMA table_info(personel)").fetchall()]
    c.executescript("PRAGMA foreign_keys=OFF;")
    c.execute(
        """
        CREATE TABLE personel_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad TEXT NOT NULL,
            soyad TEXT NOT NULL,
            gemi_id INTEGER REFERENCES gemi(id),
            gemi_id_list TEXT,
            makine_tipi_id INTEGER REFERENCES makine_tipi(id),
            makine_tipi_id_list TEXT,
            vardiya_tipi TEXT NOT NULL DEFAULT 'SABIT',
            vardiya_gunleri TEXT,
            aktif INTEGER NOT NULL DEFAULT 1,
            gemiden_cekilme INTEGER NOT NULL DEFAULT 0,
            carkci_ile_sorun INTEGER NOT NULL DEFAULT 0,
            carkci_sorun_notu TEXT,
            gemi_tutumu TEXT,
            izin_tercih_gunleri TEXT,
            izin_saat_araligi TEXT,
            is_kalitesi INTEGER NOT NULL DEFAULT 3,
            performans_notu TEXT,
            durum TEXT DEFAULT 'Gemide',
            yillik_izin_hakki INTEGER
        )
        """
    )
    new_cols = {
        "id",
        "ad",
        "soyad",
        "gemi_id",
        "gemi_id_list",
        "makine_tipi_id",
        "makine_tipi_id_list",
        "vardiya_tipi",
        "vardiya_gunleri",
        "aktif",
        "gemiden_cekilme",
        "carkci_ile_sorun",
        "carkci_sorun_notu",
        "gemi_tutumu",
        "izin_tercih_gunleri",
        "izin_saat_araligi",
        "is_kalitesi",
        "performans_notu",
        "durum",
        "yillik_izin_hakki",
    }
    common = [x for x in old_cols if x in new_cols]
    if common:
        cols_sql = ", ".join(common)
        c.execute(f"INSERT INTO personel_new ({cols_sql}) SELECT {cols_sql} FROM personel")
    c.execute("DROP TABLE personel")
    c.execute("ALTER TABLE personel_new RENAME TO personel")
    c.executescript("PRAGMA foreign_keys=ON;")


def _ensure_core_tables(c: sqlite3.Cursor) -> None:
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
            vardiya_notu TEXT,
            carkci_vardiya TEXT
        );
        """
    )


def _ensure_v8_tables(c: sqlite3.Cursor) -> None:
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS gemi_makine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gemi_id INTEGER NOT NULL REFERENCES gemi(id) ON DELETE CASCADE,
            makine_tipi_id INTEGER NOT NULL REFERENCES makine_tipi(id) ON DELETE CASCADE,
            UNIQUE(gemi_id, makine_tipi_id)
        );

        CREATE TABLE IF NOT EXISTS vardiya_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personel_id INTEGER NOT NULL REFERENCES personel(id) ON DELETE CASCADE,
            gemi_id INTEGER NOT NULL REFERENCES gemi(id) ON DELETE CASCADE,
            makine_tipi_id INTEGER NOT NULL REFERENCES makine_tipi(id) ON DELETE CASCADE,
            tarih TEXT NOT NULL,
            baslangic_saat TEXT DEFAULT '08:00',
            bitis_saat TEXT DEFAULT '08:00',
            UNIQUE(personel_id, gemi_id, makine_tipi_id, tarih)
        );

        CREATE TABLE IF NOT EXISTS personel_sertifika (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personel_id INTEGER NOT NULL REFERENCES personel(id) ON DELETE CASCADE,
            makine_tipi_id INTEGER NOT NULL REFERENCES makine_tipi(id) ON DELETE CASCADE,
            sertifika_adi TEXT,
            gecerlilik_tarihi TEXT,
            notlar TEXT
        );

        CREATE TABLE IF NOT EXISTS performans_gecmis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personel_id INTEGER NOT NULL REFERENCES personel(id) ON DELETE CASCADE,
            tarih TEXT NOT NULL,
            puan INTEGER NOT NULL,
            kaynak TEXT DEFAULT 'manuel'
        );

        CREATE TABLE IF NOT EXISTS vardiya_takas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            talep_eden_id INTEGER NOT NULL REFERENCES personel(id),
            karsi_personel_id INTEGER NOT NULL REFERENCES personel(id),
            talep_eden_tarih TEXT NOT NULL,
            karsi_tarih TEXT NOT NULL,
            durum TEXT DEFAULT 'Beklemede',
            notlar TEXT,
            olusturma_tarihi TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _apply_column_migrations(c: sqlite3.Cursor) -> None:
    _add_column_if_missing(c, "gemi", "konum", "TEXT")
    _add_column_if_missing(c, "izin", "gunler_json", "TEXT")

    for col, decl in [
        ("gemi_tutumu", "TEXT"),
        ("izin_tercih_gunleri", "TEXT"),
        ("izin_saat_araligi", "TEXT"),
        ("is_kalitesi", "INTEGER NOT NULL DEFAULT 3"),
        ("performans_notu", "TEXT"),
        ("carkci_sorun_notu", "TEXT"),
        ("gemi_id_list", "TEXT"),
        ("makine_tipi_id_list", "TEXT"),
        ("durum", "TEXT DEFAULT 'Gemide'"),
        ("yillik_izin_hakki", "INTEGER"),
    ]:
        _add_column_if_missing(c, "personel", col, decl)

    carkci_cols = _table_cols(c, "carkci")
    if "carkci_vardiya" not in carkci_cols:
        c.execute("ALTER TABLE carkci ADD COLUMN carkci_vardiya TEXT")
    _add_column_if_missing(c, "carkci", "vardiya_gunleri", "TEXT")
    _add_column_if_missing(c, "carkci", "puan_kirma", "INTEGER DEFAULT 0")


def _seed_gemi_makine_from_personel(c: sqlite3.Cursor) -> None:
    n = c.execute("SELECT COUNT(*) FROM gemi_makine").fetchone()
    if n and int(n[0]) > 0:
        return
    for row in c.execute(
        "SELECT DISTINCT gemi_id, makine_tipi_id FROM personel WHERE gemi_id IS NOT NULL AND makine_tipi_id IS NOT NULL"
    ):
        try:
            c.execute(
                "INSERT OR IGNORE INTO gemi_makine(gemi_id, makine_tipi_id) VALUES (?, ?)",
                (int(row[0]), int(row[1])),
            )
        except sqlite3.IntegrityError:
            pass


def init_db() -> None:
    with get_conn() as conn:
        c = conn.cursor()
        _ensure_core_tables(c)
        _apply_column_migrations(c)
        _migrate_personel_remove_vardiya_check(c)
        _ensure_v8_tables(c)
        _seed_gemi_makine_from_personel(c)
        conn.commit()


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
