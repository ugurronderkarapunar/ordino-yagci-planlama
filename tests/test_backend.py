"""Pytest: boş veritabanında migrasyon ve temel sorgular."""

from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture()
def fresh_db(monkeypatch, tmp_path):
    db_file = tmp_path / "t.sqlite3"
    monkeypatch.setenv("ORDINO_DB_PATH", str(db_file))
    # Yeniden yüklemeden önce modül önbelleğini temizlemek gerekmez; db_path() her çağrıda env okur.
    from src import database as db

    db.init_db()
    return db


def test_init_creates_vardiya_plan_table(fresh_db):
    from src import database as db

    row = db.sql_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='vardiya_plan'",
        (),
    )
    assert row is not None


def test_time_overlap():
    from src.time_utils import saat_cakisiyor

    assert saat_cakisiyor("08:00", "17:00", "12:00", "13:00") is True
    assert saat_cakisiyor("08:00", "12:00", "13:00", "17:00") is False


def test_gemi_makine_seed_from_personel(monkeypatch, tmp_path):
    monkeypatch.setenv("ORDINO_DB_PATH", str(tmp_path / "s.sqlite3"))
    from src import database as db

    db.init_db()
    db.sql_run("INSERT INTO gemi(ad, kod) VALUES (?, ?)", ("G1", "K1"))
    db.sql_run("INSERT INTO makine_tipi(ad) VALUES (?)", ("M1",))
    gid = int(db.sql_one("SELECT id FROM gemi WHERE ad=?", ("G1",))["id"])
    mid = int(db.sql_one("SELECT id FROM makine_tipi WHERE ad=?", ("M1",))["id"])
    db.sql_run(
        "INSERT INTO personel(ad, soyad, gemi_id, makine_tipi_id, vardiya_tipi, vardiya_gunleri) VALUES (?,?,?,?,?,?)",
        ("A", "B", gid, mid, "SABIT", "[0,2,4]"),
    )
    db.sql_run("DELETE FROM gemi_makine", ())
    db.init_db()
    n = db.sql_one("SELECT COUNT(*) AS c FROM gemi_makine", ())
    assert int(n["c"]) >= 1


def test_oneri_engine_empty_pool(monkeypatch, tmp_path):
    monkeypatch.setenv("ORDINO_DB_PATH", str(tmp_path / "o.sqlite3"))
    from src import database as db
    from src.services.oneri_engine import onerileri_hesapla_v8

    db.init_db()
    db.sql_run("INSERT INTO gemi(ad, kod, konum) VALUES (?,?,?)", ("G2", "K2", "Tersane"))
    db.sql_run("INSERT INTO makine_tipi(ad) VALUES (?)", ("MX",))
    gid = int(db.sql_one("SELECT id FROM gemi", ())["id"])
    mid = int(db.sql_one("SELECT id FROM makine_tipi", ())["id"])
    db.sql_run("INSERT INTO gemi_makine(gemi_id, makine_tipi_id) VALUES (?, ?)", (gid, mid))
    out = onerileri_hesapla_v8(gid, mid, date.today(), limit=3)
    assert isinstance(out, list)
