import sqlite3
import json
from datetime import date, timedelta
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app   # Artık streamlit mock'lanmış olduğu için hata vermez

TEST_DB = Path(__file__).parent / "test_ordino.db"

@pytest.fixture(autouse=True)
def setup_teardown():
    app.DB_PATH = TEST_DB
    app.YEDEK_DIR = Path(__file__).parent / "test_yedekler"
    app.LOG_DIR = Path(__file__).parent / "test_logs"
    if TEST_DB.exists():
        TEST_DB.unlink()
    app.init_db()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()

def test_saat_dakika():
    assert app.saat_dakika("08:00") == 480
    assert app.saat_dakika("23:59") == 1439

def test_saat_cakisiyor():
    assert app.saat_cakisiyor("08:00", "16:00", "12:00", "20:00") is True
    assert app.saat_cakisiyor("08:00", "12:00", "12:00", "16:00") is False

def test_gun_sayisi():
    assert app.gun_sayisi(date(2025, 1, 1), date(2025, 1, 1)) == 1
    assert app.gun_sayisi(date(2025, 1, 1), date(2025, 1, 10)) == 10

def test_nlp_skor_bos_metin():
    assert app.nlp_skor("") == 0.0
    assert app.nlp_skor(None) == 0.0

def test_nlp_skor_olumlu():
    skor = app.nlp_skor("çalışkan ve dikkatli mükemmel")
    assert skor > 0

def test_nlp_skor_olumsuz():
    skor = app.nlp_skor("tembel ve işe yaramaz berbat")
    assert skor < 0

def test_gemi_ekle():
    app.sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)", ("TEST", "T01", "Tersane"))
    gemi = app.sql_one("SELECT * FROM gemi WHERE ad='TEST'")
    assert gemi is not None
    assert gemi["kod"] == "T01"

def test_personel_ekle():
    app.sql_run("INSERT INTO gemi(ad) VALUES('G')")
    gemi_id = app.sql_one("SELECT id FROM gemi WHERE ad='G'")["id"]
    app.sql_run("INSERT INTO personel(ad,soyad,gemi_id,vardiya_tipi,vardiya_gunleri,is_kalitesi,durum) VALUES(?,?,?,?,?,?,?)",
                ("Ali", "Yılmaz", gemi_id, "SABIT", "[]", 4, "Gemide"))
    p = app.sql_one("SELECT * FROM personel WHERE ad='Ali'")
    assert p["soyad"] == "Yılmaz"

def test_izinli_listesi():
    app.sql_run("INSERT INTO personel(ad,soyad,vardiya_tipi,vardiya_gunleri,is_kalitesi,durum) VALUES('İzinli','Kişi','SABIT','[]',3,'Gemide')")
    pid = app.sql_one("SELECT id FROM personel WHERE ad='İzinli'")["id"]
    bugun = date.today()
    app.sql_run("INSERT INTO izin(personel_id,baslangic,bitis,gun_sayisi) VALUES(?,?,?,?)",
                (pid, bugun.isoformat(), (bugun + timedelta(days=2)).isoformat(), 3))
    izinli_set = app.bugun_izinli_ids()
    assert pid in izinli_set

def test_vardiya_plani_kontrol():
    app.sql_run("INSERT INTO gemi(ad) VALUES('PLANGEMI')")
    gemi_id = app.sql_one("SELECT id FROM gemi WHERE ad='PLANGEMI'")["id"]
    app.sql_run("INSERT INTO makine_tipi(ad) VALUES('MAK')")
    mak_id = app.sql_one("SELECT id FROM makine_tipi WHERE ad='MAK'")["id"]
    app.sql_run("INSERT INTO personel(ad,soyad,vardiya_tipi,vardiya_gunleri,is_kalitesi,durum) VALUES('P','X','SABIT','[]',3,'Gemide')")
    pid = app.sql_one("SELECT id FROM personel WHERE ad='P'")["id"]
    bugun = date.today()
    app.sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih) VALUES(?,?,?,?)",
                (pid, gemi_id, mak_id, bugun.isoformat()))
    assert app.vardiya_plani_kontrol(gemi_id, mak_id, bugun) == pid
