import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "ordino.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def sql_run(query, params=()):
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()

def sql_all(query, params=()):
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()

def sql_one(query, params=()):
    with get_connection() as conn:
        return conn.execute(query, params).fetchone()

def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gemi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad TEXT NOT NULL UNIQUE,
            kod TEXT
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
            vardiya_tipi TEXT NOT NULL DEFAULT 'SABIT',
            vardiya_gunleri TEXT DEFAULT '[]',
            aktif INTEGER DEFAULT 1,
            gemiden_cekilme INTEGER DEFAULT 0,
            carkci_ile_sorun INTEGER DEFAULT 0,
            carkci_sorun_notu TEXT,
            gemi_tutumu TEXT DEFAULT 'Orta',
            izin_tercih_gunleri TEXT DEFAULT '[]',
            izin_saat_araligi TEXT,
            is_kalitesi INTEGER DEFAULT 3,
            performans_notu TEXT,
            durum_tipi TEXT DEFAULT 'aktif'
        );
        CREATE TABLE IF NOT EXISTS izin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personel_id INTEGER REFERENCES personel(id),
            baslangic TEXT NOT NULL,
            bitis TEXT NOT NULL,
            gun_sayisi INTEGER,
            notlar TEXT
        );
        CREATE TABLE IF NOT EXISTS carkci (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad TEXT,
            soyad TEXT,
            gemi_id INTEGER REFERENCES gemi(id),
            problemli_yagci_id INTEGER REFERENCES personel(id),
            sorun_metni TEXT,
            vardiya_notu TEXT,
            carkci_vardiya TEXT
        );
        CREATE TABLE IF NOT EXISTS gemi_makine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gemi_id INTEGER REFERENCES gemi(id),
            makine_tipi_id INTEGER REFERENCES makine_tipi(id),
            tarih TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vardiya_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gemi_makine_id INTEGER REFERENCES gemi_makine(id),
            personel_id INTEGER REFERENCES personel(id),
            baslangic_saat TEXT,
            bitis_saat TEXT,
            onayli INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sablon (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad TEXT NOT NULL,
            icerik TEXT NOT NULL,
            tur TEXT DEFAULT 'haftalik'
        );
        CREATE INDEX IF NOT EXISTS idx_personel_aktif ON personel(aktif);
        CREATE INDEX IF NOT EXISTS idx_izin_baslangic ON izin(baslangic);
        CREATE INDEX IF NOT EXISTS idx_izin_bitis ON izin(bitis);
        CREATE INDEX IF NOT EXISTS idx_gemi_makine_tarih ON gemi_makine(tarih);
        CREATE INDEX IF NOT EXISTS idx_vardiya_plan_gmi ON vardiya_plan(gemi_makine_id);
    """)
    conn.commit()
    conn.close()
