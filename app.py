"""
Ordino Yağcı Planlaması — SON SÜRÜM (+PDF Rapor, Otomatik Yedekleme, Veri Doğrulama, Test Verisi, Konum Haritası)
Çalıştır: streamlit run app.py
"""
from __future__ import annotations

import json
import sqlite3
import calendar as _cal
from datetime import date, timedelta, datetime
from pathlib import Path
import io
import os
import shutil
import random

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF

# ---------- VERİTABANI ----------
DB_PATH = Path(__file__).parent / "ordino.db"
FOTO_DIR = Path(__file__).parent / "gemi_fotolari"
YEDEK_DIR = Path(__file__).parent / "yedekler"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def sql_one(query: str, params=()):
    with get_connection() as conn:
        cur = conn.execute(query, params)
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        return None

def sql_all(query: str, params=()):
    with get_connection() as conn:
        cur = conn.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def sql_run(query: str, params=()):
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()

def veritabani_yedekle():
    """Veritabanını yedekler"""
    YEDEK_DIR.mkdir(exist_ok=True)
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek_adi = f"ordino_yedek_{zaman}.db"
    yedek_yolu = YEDEK_DIR / yedek_adi
    shutil.copy2(DB_PATH, yedek_yolu)
    # Eski yedekleri temizle (son 10 yedek kalsın)
    yedekler = sorted(YEDEK_DIR.glob("ordino_yedek_*.db"))
    if len(yedekler) > 10:
        for eski in yedekler[:-10]:
            eski.unlink()
    return yedek_yolu

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS gemi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT UNIQUE NOT NULL, kod TEXT, konum TEXT, foto TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS makine_tipi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT UNIQUE NOT NULL)""")

    c.execute("""CREATE TABLE IF NOT EXISTS personel (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL, soyad TEXT NOT NULL,
        gemi_id INTEGER, gemi_id_list TEXT,
        makine_tipi_id INTEGER, makine_tipi_id_list TEXT,
        vardiya_tipi TEXT, vardiya_gunleri TEXT,
        gemiden_cekilme INTEGER DEFAULT 0,
        carkci_ile_sorun INTEGER DEFAULT 0, carkci_sorun_notu TEXT,
        gemi_tutumu TEXT, izin_tercih_gunleri TEXT, izin_saat_araligi TEXT,
        is_kalitesi INTEGER, performans_notu TEXT, aktif INTEGER DEFAULT 1
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS izin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personel_id INTEGER NOT NULL,
        baslangic TEXT, bitis TEXT,
        gun_sayisi INTEGER, notlar TEXT, gunler_json TEXT,
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS carkci (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT, soyad TEXT, gemi_id INTEGER,
        problemli_yagci_id INTEGER, sorun_metni TEXT,
        vardiya_notu TEXT, carkci_vardiya TEXT, vardiya_gunleri TEXT,
        puan_kirma INTEGER DEFAULT 0,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id) ON DELETE SET NULL,
        FOREIGN KEY(problemli_yagci_id) REFERENCES personel(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS vardiya_plan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personel_id INTEGER NOT NULL,
        gemi_id INTEGER NOT NULL,
        makine_tipi_id INTEGER NOT NULL,
        tarih TEXT NOT NULL,
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS personel_sertifika (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personel_id INTEGER NOT NULL,
        makine_tipi_id INTEGER NOT NULL,
        sertifika_adi TEXT,
        gecerlilik_tarihi TEXT,
        notlar TEXT,
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS performans_gecmis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personel_id INTEGER NOT NULL,
        tarih TEXT NOT NULL,
        puan INTEGER NOT NULL,
        kaynak TEXT DEFAULT 'manuel',
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE
    )""")

    # Sütun kontrolleri
    c.execute("PRAGMA table_info(gemi)")
    g_cols = [col[1] for col in c.fetchall()]
    if "konum" not in g_cols: c.execute("ALTER TABLE gemi ADD COLUMN konum TEXT")
    if "foto" not in g_cols: c.execute("ALTER TABLE gemi ADD COLUMN foto TEXT")

    c.execute("PRAGMA table_info(personel)")
    p_cols = [col[1] for col in c.fetchall()]
    for col, typ in [("gemi_id_list","TEXT"),("makine_tipi_id_list","TEXT"),
                     ("gemiden_cekilme","INTEGER DEFAULT 0"),("carkci_ile_sorun","INTEGER DEFAULT 0"),
                     ("carkci_sorun_notu","TEXT"),("gemi_tutumu","TEXT"),
                     ("izin_tercih_gunleri","TEXT"),("izin_saat_araligi","TEXT"),
                     ("is_kalitesi","INTEGER"),("performans_notu","TEXT"),("aktif","INTEGER DEFAULT 1")]:
        if col not in p_cols:
            try: c.execute(f"ALTER TABLE personel ADD COLUMN {col} {typ}")
            except: pass

    c.execute("PRAGMA table_info(izin)")
    if "gunler_json" not in [c[1] for c in c.fetchall()]:
        c.execute("ALTER TABLE izin ADD COLUMN gunler_json TEXT")

    c.execute("PRAGMA table_info(carkci)")
    c_cols = [col[1] for col in c.fetchall()]
    if "vardiya_gunleri" not in c_cols: c.execute("ALTER TABLE carkci ADD COLUMN vardiya_gunleri TEXT")
    if "puan_kirma" not in c_cols: c.execute("ALTER TABLE carkci ADD COLUMN puan_kirma INTEGER DEFAULT 0")

    conn.commit()
    conn.close()

# ---------- YARDIMCI ----------
GUNLER_TR = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
AY_ADLARI = ["","Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
             "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
VARDIYA_TIPLERI = ["SABIT","GRUPCU","IZINCI","TERSANE","8_5"]
GEMI_KONUMLARI = ["Tersane", "Dışarıda", "Gecede", "Belirtilmedi"]

def _json_gunleri_metne(v):
    if not v: return "-"
    try:
        idx = json.loads(v)
        if not isinstance(idx, list): return "-"
        return ", ".join(GUNLER_TR[int(i)] for i in idx if 0 <= int(i) < 7) or "-"
    except: return "-"

def _makine_id_json(lst): return json.dumps(lst)
def _gemi_id_json(lst):   return json.dumps(lst)

def _id_listesi(v):
    if not v: return []
    try:
        p = json.loads(v)
        return [int(x) for x in p] if isinstance(p, list) else [int(p)]
    except: return []

def _personel_label_map(rows):
    return {f"{r['ad']} {r['soyad']} (ID:{r['id']})": int(r["id"]) for r in rows}

def gun_sayisi(bas, bit): return (bit - bas).days + 1

def bugun_izinli_ids() -> set[int]:
    bugun = date.today().isoformat()
    rows = sql_all("SELECT DISTINCT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (bugun,))
    return {r["personel_id"] for r in rows}

def izinde_mi(pid: int, kontrol: date) -> bool:
    t = kontrol.isoformat()
    return bool(sql_one("SELECT id FROM izin WHERE personel_id=? AND ?>=baslangic AND ?<=bitis", (pid, t, t)))

def sertifika_gecerli_mi(pid: int, makine_tipi_id: int, kontrol_tarih: date) -> bool:
    row = sql_one("""SELECT id FROM personel_sertifika
                     WHERE personel_id=? AND makine_tipi_id=? AND (gecerlilik_tarihi IS NULL OR gecerlilik_tarihi >= ?)""",
                   (pid, makine_tipi_id, kontrol_tarih.isoformat()))
    return row is not None

def baska_gemide_mi(personel_id: int, tarih: date, mevcut_gemi_id: int, esnek=False) -> bool:
    if esnek: return False
    t_str = tarih.isoformat()
    row = sql_one("""SELECT v.gemi_id FROM vardiya_plan v
                     WHERE v.personel_id=? AND v.tarih=? AND v.gemi_id != ?""",
                   (personel_id, t_str, mevcut_gemi_id))
    return row is not None

def ayni_gun_baska_makine(personel_id: int, tarih: date, makine_tipi_id: int) -> bool:
    """Aynı gün aynı kişiye farklı makine atanmış mı?"""
    t_str = tarih.isoformat()
    row = sql_one("""SELECT id FROM vardiya_plan
                     WHERE personel_id=? AND tarih=? AND makine_tipi_id != ?""",
                   (personel_id, t_str, makine_tipi_id))
    return row is not None

def fazla_mesai_kontrol(personel_id: int, tarih: date) -> tuple[bool, int]:
    """Son 7 günde kaç gün çalışmış?"""
    bas = (tarih - timedelta(days=7)).isoformat()
    bit = tarih.isoformat()
    row = sql_one("""SELECT COUNT(DISTINCT tarih) AS c FROM vardiya_plan
                     WHERE personel_id=? AND tarih >= ? AND tarih <= ?""",
                   (personel_id, bas, bit))
    gun = row["c"] if row else 0
    return gun >= 6, gun  # 6 günden fazla çalışmışsa uyar

def vardiya_plani_kontrol(gemi_id, makine_tipi_id, tarih):
    t_str = tarih.isoformat()
    row = sql_one("SELECT personel_id FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", 
                  (gemi_id, makine_tipi_id, t_str))
    return row["personel_id"] if row else None

def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5, esnek_cakisma=False):
    mevcut_atanmis = vardiya_plani_kontrol(gemi_id, makine_tipi_id, hedef_tarih)
    if mevcut_atanmis:
        p = sql_one("SELECT id,ad,soyad,vardiya_tipi,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,carkci_ile_sorun,is_kalitesi FROM personel WHERE id=?", (mevcut_atanmis,))
        if p:
            return [{
                **p,
                "puan": 999,
                "uyari_8_5": p.get("vardiya_tipi")=="8_5",
                "zaten_atanmis": True
            }]

    tum = sql_all("""SELECT id,ad,soyad,vardiya_tipi,gemi_id,gemi_id_list,
                            makine_tipi_id,makine_tipi_id_list,carkci_ile_sorun,is_kalitesi
                     FROM personel WHERE aktif=1""")
    sonuclar = []
    for p in tum:
        if cikan_id and p["id"] == cikan_id: continue
        if izinde_mi(p["id"], hedef_tarih): continue
        if baska_gemide_mi(p["id"], hedef_tarih, gemi_id, esnek=esnek_cakisma): continue
        # Yeni doğrulama: aynı gün farklı makineye atanmış mı?
        if ayni_gun_baska_makine(p["id"], hedef_tarih, makine_tipi_id):
            continue
        mids = _id_listesi(p.get("makine_tipi_id_list")) or ([p["makine_tipi_id"]] if p.get("makine_tipi_id") else [])
        if makine_tipi_id not in mids: continue
        if not sertifika_gecerli_mi(p["id"], makine_tipi_id, hedef_tarih):
            continue
        gids = _id_listesi(p.get("gemi_id_list")) or ([p.get("gemi_id")] if p.get("gemi_id") else [])
        if gemi_id not in gids: continue
        if p.get("carkci_ile_sorun"): continue

        # Fazla mesai kontrolü (puan kırma)
        fazla_mesai, gun_say = fazla_mesai_kontrol(p["id"], hedef_tarih)
        vardiya = p.get("vardiya_tipi","")
        vardiya_puan = {"IZINCI":100, "TERSANE":95, "GRUPCU":80, "SABIT":60, "8_5":40}.get(vardiya, 50)
        kalite_puan = (p.get("is_kalitesi") or 3) * 10
        mesai_ceza = -20 if fazla_mesai else 0
        toplam_puan = vardiya_puan + kalite_puan + mesai_ceza
        sonuclar.append({
            **p, 
            "puan": toplam_puan, 
            "uyari_8_5": vardiya=="8_5", 
            "zaten_atanmis": False,
            "fazla_mesai": fazla_mesai,
            "son_7_gun": gun_say
        })
    sonuclar.sort(key=lambda x: -x["puan"])
    return sonuclar[:limit]

def to_dict_rows(oneriler):
    tum_mak = {r["id"]: r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
    rows = []
    for o in oneriler:
        mids = _id_listesi(o.get("makine_tipi_id_list")) or ([o["makine_tipi_id"]] if o.get("makine_tipi_id") else [])
        row_data = {
            "id": o["id"],
            "ad_soyad": f"{o['ad']} {o['soyad']}",
            "vardiya": o.get("vardiya_tipi","-"),
            "makine": ", ".join(tum_mak.get(m,str(m)) for m in mids),
            "puan": o["puan"],
            "uyari_8_5": o.get("uyari_8_5",False),
            "zaten_atanmis": o.get("zaten_atanmis", False)
        }
        if o.get("fazla_mesai"):
            row_data["ad_soyad"] += " ⚠️ FAZLA MESAİ"
            row_data["puan"] = o["puan"]  # zaten düşürülmüş
        rows.append(row_data)
    return rows

# ---------- TAKVİM HTML ----------
def _takvim_html(yil: int, ay: int, isaretli: set[date]) -> str:
    son_gun = _cal.monthrange(yil, ay)[1]
    ilk_gun_haftaici = date(yil, ay, 1).weekday()
    bugun = date.today()
    css = """
    <style>
    .cal{font-family:system-ui,sans-serif;max-width:400px;margin:0 auto;
         background:#2b2b2b;border-radius:16px;padding:16px;box-shadow:0 2px 10px rgba(0,0,0,0.3);}
    .cal-title{text-align:center;font-size:18px;font-weight:600;color:#f0f0f0;margin-bottom:12px;}
    .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}
    .cal-hdr{text-align:center;font-size:12px;font-weight:600;color:#aaa;padding:6px 0;}
    .cal-cell{text-align:center;padding:10px 2px;border-radius:10px;font-size:14px;font-weight:500;}
    .cal-empty{background:transparent;}
    .cal-normal{background:#3a3a3a;color:#ddd;}
    .cal-izin{background:#f3831f;color:#fff;font-weight:600;box-shadow:0 2px 5px rgba(243,131,31,0.5);}
    .cal-bugun{background:#2b2b2b;color:#f3831f;border:2px solid #f3831f;font-weight:700;}
    .cal-izin.cal-bugun{background:#d35400;color:#fff;border:2px solid #d35400;}
    </style>
    """
    html = css + f'<div class="cal"><div class="cal-title">{AY_ADLARI[ay]} {yil}</div>'
    html += '<div class="cal-grid">'
    for g in ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]:
        html += f'<div class="cal-hdr">{g}</div>'
    for _ in range(ilk_gun_haftaici):
        html += '<div class="cal-cell cal-empty"></div>'
    for n in range(1, son_gun + 1):
        d = date(yil, ay, n)
        cls = "cal-izin" if d in isaretli else "cal-normal"
        if d == bugun: cls += " cal-bugun"
        html += f'<div class="cal-cell {cls}">{n}</div>'
    html += "</div></div>"
    return html

# ---------- GEMİ KONUM HARİTASI HTML ----------
def _konum_haritasi_html():
    gemiler = sql_all("SELECT ad, konum FROM gemi ORDER BY ad")
    if not gemiler:
        return "<p style='color:#aaa;'>Henüz gemi eklenmemiş.</p>"
    
    icon_map = {
        "Tersane": "🏗️",
        "Dışarıda": "⚓",
        "Gecede": "🌙",
        "Belirtilmedi": "❓"
    }
    
    html = """
    <style>
        .harita-container {
            background: #2b2b2b;
            border-radius: 16px;
            padding: 20px;
            margin: 10px 0;
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            justify-content: center;
        }
        .gemi-kart {
            background: #3a3a4e;
            border-radius: 12px;
            padding: 15px;
            text-align: center;
            min-width: 100px;
            transition: transform 0.2s;
        }
        .gemi-kart:hover {
            transform: scale(1.05);
            background: #4a4a5e;
        }
        .gemi-ikon {
            font-size: 40px;
        }
        .gemi-ad {
            color: #f0f0f0;
            font-weight: bold;
            margin-top: 5px;
        }
        .gemi-konum {
            color: #f3831f;
            font-size: 14px;
        }
        .konum-baslik {
            color: #f0f0f0;
            text-align: center;
            margin-bottom: 15px;
            font-size: 18px;
            font-weight: 600;
        }
        .konum-grup {
            background: #333;
            border-radius: 12px;
            padding: 10px;
            margin: 5px;
            min-width: 150px;
        }
        .konum-grup-baslik {
            color: #f3831f;
            font-weight: bold;
            margin-bottom: 8px;
            text-align: center;
        }
    </style>
    <div class="harita-container">
    """
    
    # Konumlara göre grupla
    konum_gruplari = {}
    for g in gemiler:
        konum = g.get("konum") or "Belirtilmedi"
        if konum not in konum_gruplari:
            konum_gruplari[konum] = []
        konum_gruplari[konum].append(g["ad"])
    
    for konum, gemi_listesi in konum_gruplari.items():
        html += f"""
        <div class="konum-grup">
            <div class="konum-grup-baslik">{icon_map.get(konum, '❓')} {konum}</div>
            {''.join(f'<div class="gemi-kart"><div class="gemi-ad">{g}</div></div>' for g in gemi_listesi)}
        </div>
        """
    
    html += "</div>"
    return html

# ---------- PDF RAPORLAMA ----------
class PDFRapor(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Ordino Yağcı Planlaması - Rapor', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Sayfa {self.page_no()}/{{nb}}', 0, 0, 'C')

def pdf_rapor_olustur(rapor_tipi="aylik_ozet", ay=None, yil=None):
    """PDF raporu oluşturur"""
    pdf = PDFRapor()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Türkçe karakter desteği için font
    pdf.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
    pdf.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf', uni=True)
    
    if rapor_tipi == "aylik_ozet":
        if not ay or not yil:
            bugun = date.today()
            ay = ay or bugun.month
            yil = yil or bugun.year
        ay_bas = date(yil, ay, 1)
        ay_son = date(yil, ay, _cal.monthrange(yil, ay)[1])
        
        pdf.set_font('DejaVu', 'B', 14)
        pdf.cell(0, 10, f'Aylık Personel Özeti - {AY_ADLARI[ay]} {yil}', 0, 1, 'C')
        pdf.ln(5)
        
        pdf.set_font('DejaVu', 'B', 10)
        pdf.cell(50, 7, 'Personel', 1)
        pdf.cell(30, 7, 'Çalışma Günü', 1)
        pdf.cell(30, 7, 'İzin Günü', 1)
        pdf.cell(30, 7, 'Toplam Gün', 1)
        pdf.ln()
        
        personeller = sql_all("SELECT id, ad, soyad FROM personel ORDER BY ad")
        pdf.set_font('DejaVu', '', 10)
        for p in personeller:
            izin_gunleri = 0
            izinler = sql_all("SELECT baslangic, bitis FROM izin WHERE personel_id=? AND baslangic <= ? AND bitis >= ?",
                              (p["id"], ay_son.isoformat(), ay_bas.isoformat()))
            for iz in izinler:
                bas = max(date.fromisoformat(iz["baslangic"]), ay_bas)
                bit = min(date.fromisoformat(iz["bitis"]), ay_son)
                izin_gunleri += (bit - bas).days + 1
            calisma = sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE personel_id=? AND tarih >= ? AND tarih <= ?",
                              (p["id"], ay_bas.isoformat(), ay_son.isoformat()))
            calisma_gunleri = calisma["c"] if calisma else 0
            pdf.cell(50, 7, f"{p['ad']} {p['soyad']}", 1)
            pdf.cell(30, 7, str(calisma_gunleri), 1)
            pdf.cell(30, 7, str(izin_gunleri), 1)
            pdf.cell(30, 7, str(calisma_gunleri + izin_gunleri), 1)
            pdf.ln()
    
    elif rapor_tipi == "vardiya_plani":
        pdf.set_font('DejaVu', 'B', 14)
        pdf.cell(0, 10, 'Vardiya Planı Raporu', 0, 1, 'C')
        pdf.ln(5)
        
        pdf.set_font('DejaVu', 'B', 9)
        pdf.cell(30, 7, 'Tarih', 1)
        pdf.cell(40, 7, 'Gemi', 1)
        pdf.cell(35, 7, 'Makine', 1)
        pdf.cell(40, 7, 'Personel', 1)
        pdf.ln()
        
        plan = sql_all("""SELECT v.tarih, g.ad AS gemi, m.ad AS makine, p.ad||' '||p.soyad AS personel
            FROM vardiya_plan v
            JOIN gemi g ON v.gemi_id=g.id
            JOIN makine_tipi m ON v.makine_tipi_id=m.id
            JOIN personel p ON v.personel_id=p.id
            ORDER BY v.tarih DESC LIMIT 50""")
        
        pdf.set_font('DejaVu', '', 9)
        for p in plan:
            pdf.cell(30, 7, p['tarih'], 1)
            pdf.cell(40, 7, p['gemi'], 1)
            pdf.cell(35, 7, p['makine'], 1)
            pdf.cell(40, 7, p['personel'], 1)
            pdf.ln()
    
    # PDF'i kaydet
    pdf_path = Path(__file__).parent / f"rapor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(str(pdf_path))
    return pdf_path

# ---------- TEST VERİSİ OLUŞTURMA ----------
def test_verisi_olustur():
    """Demo test verileri oluşturur"""
    # Gemiler
    for gemi_ad in ["M/T ATLANTİC", "M/V BOĞAZİÇİ", "T/S ÇINAR", "M/V DENİZ YILDIZI"]:
        try:
            sql_run("INSERT INTO gemi(ad, kod, konum) VALUES(?,?,?)",
                    (gemi_ad, f"G{random.randint(100,999)}", random.choice(GEMI_KONUMLARI[:3])))
        except: pass
    
    # Makine tipleri
    for mak in ["Dizel Motor", "Kompresör", "Pompa", "Jeneratör", "Kazan"]:
        try:
            sql_run("INSERT INTO makine_tipi(ad) VALUES(?)", (mak,))
        except: pass
    
    gemiler = sql_all("SELECT id FROM gemi")
    makineler = sql_all("SELECT id FROM makine_tipi")
    
    # Personel
    isimler = [
        ("Ahmet", "Yılmaz"), ("Mehmet", "Demir"), ("Ali", "Kaya"), ("Veli", "Şahin"),
        ("Ayşe", "Çelik"), ("Fatma", "Aydın"), ("Hasan", "Öztürk"), ("Hüseyin", "Arslan")
    ]
    for ad, soyad in isimler:
        gemi_id = random.choice(gemiler)["id"] if gemiler else None
        mak_id = random.choice(makineler)["id"] if makineler else None
        vt = random.choice(VARDIYA_TIPLERI)
        gunler = json.dumps(random.sample(range(7), random.randint(2,5)))
        try:
            sql_run("""INSERT INTO personel(ad,soyad,gemi_id,makine_tipi_id,makine_tipi_id_list,
                vardiya_tipi,vardiya_gunleri,is_kalitesi) VALUES(?,?,?,?,?,?,?,?)""",
                (ad, soyad, gemi_id, mak_id, _makine_id_json([mak_id]), vt, gunler, random.randint(2,5)))
        except: pass
    
    st.success("Test verileri başarıyla oluşturuldu!")
    st.rerun()

# ---------- SAYFA: GEMİLER ----------
def _sayfa_excel():
    st.subheader("🚢 Gemiler & Makine Yönetimi")

    with st.form("gemi_ekle_form", clear_on_submit=True):
        c1,c2,c3,c4 = st.columns(4)
        gad  = c1.text_input("Gemi Adı")
        gkod = c2.text_input("Gemi Kodu (opsiyonel)")
        mad  = c3.text_input("Makine Tipi Adı")
        konum = c4.selectbox("Gemi Nerede?", GEMI_KONUMLARI, index=3)
        if st.form_submit_button("➕ Ekle"):
            if not gad.strip() or not mad.strip():
                st.error("Gemi adı ve makine tipi adı zorunlu.")
            else:
                try:
                    sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",(gad.strip(),gkod.strip() or None, konum if konum != "Belirtilmedi" else None))
                except: st.warning("Gemi zaten kayıtlı.")
                try:
                    sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(mad.strip(),))
                except: st.warning("Makine tipi zaten kayıtlı.")
                st.success("Başarıyla eklendi.")
                st.rerun()

    # Gemi Konum Haritası
    st.subheader("🗺️ Gemi Konum Haritası")
    st.components.v1.html(_konum_haritasi_html(), height=300, scrolling=True)

    # ... (geri kalan gemi kodları aynı) ...
    st.divider()
    g_rows = sql_all("""SELECT g.id,g.ad,g.kod,g.konum,g.foto,COUNT(p.id) AS personel_sayisi
        FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad""")
    st.dataframe(pd.DataFrame(g_rows), use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        with st.expander("✏️ Gemi Düzenle / Sil (Fotoğraf Yükleyin)"):
            if g_rows:
                g_map = {f"{r['ad']} (ID:{r['id']})": r for r in g_rows}
                gs = st.selectbox("Gemi Seç", list(g_map.keys()), key="gd_sec")
                gr = g_map[gs]
                na = st.text_input("Yeni Ad", value=gr["ad"] or "", key="gd_ad")
                nk = st.text_input("Yeni Kod", value=gr["kod"] or "", key="gd_kod")
                nkonum = st.selectbox("Yeni Konum", GEMI_KONUMLARI,
                                      index=GEMI_KONUMLARI.index(gr["konum"]) if gr["konum"] in GEMI_KONUMLARI else 3,
                                      key="gd_konum")
                if gr.get("foto"):
                    foto_path = Path(gr["foto"])
                    if foto_path.exists():
                        st.image(str(foto_path), width=200, caption="Mevcut Fotoğraf")
                uploaded_foto = st.file_uploader("Yeni fotoğraf (opsiyonel)", type=["png","jpg","jpeg"], key="gd_foto")
                if st.button("Güncelle", key="btn_gd"):
                    if not na.strip(): st.error("Ad boş olamaz.")
                    else:
                        foto_kayit = gr["foto"]
                        if uploaded_foto is not None:
                            FOTO_DIR.mkdir(exist_ok=True)
                            ext = uploaded_foto.name.split('.')[-1]
                            file_path = FOTO_DIR / f"gemi_{gr['id']}.{ext}"
                            with open(file_path, "wb") as f:
                                f.write(uploaded_foto.getbuffer())
                            foto_kayit = str(file_path)
                        sql_run("UPDATE gemi SET ad=?,kod=?,konum=?,foto=? WHERE id=?",
                                (na.strip(), nk.strip() or None, nkonum if nkonum != "Belirtilmedi" else None, foto_kayit, gr["id"]))
                        st.success("Güncellendi."); st.rerun()
                if st.button("Gemiyi Sil", type="secondary", key="btn_gsil"):
                    b = sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id=?",(int(gr['id']),))
                    if b and b["c"]>0: st.error("Bu gemiye bağlı personel var.")
                    else:
                        if gr.get("foto") and Path(gr["foto"]).exists():
                            try: os.remove(gr["foto"])
                            except: pass
                        sql_run("DELETE FROM carkci WHERE gemi_id=?", (int(gr['id']),))
                        sql_run("DELETE FROM vardiya_plan WHERE gemi_id=?", (int(gr['id']),))
                        sql_run("DELETE FROM gemi WHERE id=?",(int(gr['id']),))
                        st.success("Gemi silindi."); st.rerun()
            else: st.info("Gemi yok.")

    with col2:
        with st.expander("✏️ Makine Tipi Düzenle / Sil"):
            m_rows = sql_all("""SELECT m.id,m.ad,COUNT(p.id) AS personel_sayisi
                FROM makine_tipi m LEFT JOIN personel p ON p.makine_tipi_id=m.id GROUP BY m.id ORDER BY m.ad""")
            if m_rows:
                m_map = {f"{r['ad']} (ID:{r['id']})": r for r in m_rows}
                ms = st.selectbox("Makine Tipi Seç", list(m_map.keys()), key="md_sec")
                mr = m_map[ms]
                nm = st.text_input("Yeni Ad", value=mr["ad"] or "", key="md_ad")
                if st.button("Güncelle", key="btn_md"):
                    if not nm.strip(): st.error("Ad boş olamaz.")
                    else:
                        sql_run("UPDATE makine_tipi SET ad=? WHERE id=?",(nm.strip(),mr["id"]))
                        st.success("Güncellendi."); st.rerun()
                if st.button("Makine Tipini Sil", type="secondary", key="btn_msil"):
                    b = sql_one("SELECT COUNT(*) AS c FROM personel WHERE makine_tipi_id=?",(int(mr['id']),))
                    if b and b["c"]>0: st.error("Bağlı personel var.")
                    else:
                        sql_run("DELETE FROM vardiya_plan WHERE makine_tipi_id=?",(int(mr['id']),))
                        sql_run("DELETE FROM makine_tipi WHERE id=?",(int(mr['id']),))
                        st.success("Silindi."); st.rerun()
            else: st.info("Makine tipi yok.")

    # Gemi Detay Kartları
    st.divider()
    st.subheader("📸 Gemi Detay Kartları")
    tum_gemiler = sql_all("SELECT * FROM gemi ORDER BY ad")
    if tum_gemiler:
        for gemi in tum_gemiler:
            with st.container():
                cols = st.columns([1,2])
                with cols[0]:
                    if gemi.get("foto") and Path(gemi["foto"]).exists():
                        st.image(str(gemi["foto"]), use_container_width=True, caption=gemi["ad"])
                    else:
                        st.image("https://via.placeholder.com/200x150?text=Foto%C4%9Fraf+Yok", caption=gemi["ad"], use_container_width=True)
                with cols[1]:
                    st.markdown(f"### {gemi['ad']} ({gemi.get('konum','Konum belirtilmedi')})")
                    yagcilar = sql_all("SELECT ad, soyad, vardiya_tipi FROM personel WHERE aktif=1 AND (gemi_id=? OR gemi_id_list LIKE ?)",
                                       (gemi["id"], f'%{gemi["id"]}%'))
                    if yagcilar:
                        st.markdown("**Yağcılar:**")
                        for y in yagcilar:
                            st.write(f"- {y['ad']} {y['soyad']} ({y['vardiya_tipi']})")
                    else: st.markdown("*Yağcı atanmamış.*")
                    carkcilar = sql_all("SELECT ad, soyad, carkci_vardiya FROM carkci WHERE gemi_id=?", (gemi["id"],))
                    if carkcilar:
                        st.markdown("**Çarkçı(lar):**")
                        for c in carkcilar:
                            st.write(f"- {c['ad']} {c['soyad']} ({c['carkci_vardiya']})")
                    else: st.markdown("*Çarkçı kaydı yok.*")
                st.markdown("---")
    else: st.info("Henüz gemi eklenmemiş.")

# ---------- DİĞER SAYFALAR ----------
# (Personel, İzin, Çarkçı, Öneri, Bilgi sayfaları aynı kalır,
#  sadece Bilgi sayfasına PDF rapor ve yedekleme butonları eklenir)

def _sayfa_bilgi():
    st.subheader("📊 Durum Özeti, Uyarılar ve Raporlar")

    # --- Yedekleme ve Test Verisi Butonları ---
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    with col_btn1:
        if st.button("💾 Veritabanını Yedekle", key="btn_yedek"):
            yedek_yolu = veritabani_yedekle()
            st.success(f"Yedekleme tamamlandı: {yedek_yolu.name}")
    with col_btn2:
        if st.button("🧪 Test Verisi Oluştur", key="btn_test"):
            test_verisi_olustur()
    with col_btn3:
        st.download_button(
            label="📥 Veritabanını İndir",
            data=open(DB_PATH, "rb"),
            file_name=f"ordino_yedek_{date.today().isoformat()}.db",
            mime="application/octet-stream"
        )

    st.divider()

    # --- PDF Raporlar ---
    st.subheader("📄 PDF Raporlar")
    col_pdf1, col_pdf2 = st.columns(2)
    with col_pdf1:
        if st.button("📊 Aylık Personel Özeti (PDF)", key="btn_pdf_aylik"):
            pdf_path = pdf_rapor_olustur("aylik_ozet")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    "📥 PDF İndir",
                    data=f,
                    file_name=pdf_path.name,
                    mime="application/pdf"
                )
    with col_pdf2:
        if st.button("📋 Vardiya Planı (PDF)", key="btn_pdf_vardiya"):
            pdf_path = pdf_rapor_olustur("vardiya_plani")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    "📥 PDF İndir",
                    data=f,
                    file_name=pdf_path.name,
                    mime="application/pdf"
                )

    st.divider()

    # --- Uyarılar ---
    st.markdown("### 🚨 Uyarılar")
    uyari_say = 0
    uyari_metinleri = []

    bugun_izinliler = sql_all("""SELECT p.ad, p.soyad, i.baslangic, i.bitis
        FROM izin i JOIN personel p ON p.id=i.personel_id
        WHERE date('now') BETWEEN i.baslangic AND i.bitis""")
    if bugun_izinliler:
        uyari_say += len(bugun_izinliler)
        uyari_metinleri.append(f"Bugün {len(bugun_izinliler)} kişi izinde.")
        with st.expander(f"🟠 Bugün İzinde ({len(bugun_izinliler)} kişi)", expanded=True):
            st.dataframe(pd.DataFrame(bugun_izinliler), use_container_width=True, hide_index=True)

    # Fazla mesai uyarısı
    fazla_mesai_listesi = []
    personeller = sql_all("SELECT id, ad, soyad FROM personel WHERE aktif=1")
    for p in personeller:
        fazla, gun = fazla_mesai_kontrol(p["id"], date.today())
        if fazla:
            fazla_mesai_listesi.append(f"{p['ad']} {p['soyad']} (son 7 günde {gun} gün)")
    if fazla_mesai_listesi:
        uyari_say += len(fazla_mesai_listesi)
        uyari_metinleri.append(f"{len(fazla_mesai_listesi)} kişi fazla mesai yapıyor.")
        with st.expander(f"⚠️ Fazla Mesai Yapan Personel ({len(fazla_mesai_listesi)})"):
            for fm in fazla_mesai_listesi:
                st.write(f"- {fm}")

    yarin = (date.today() + timedelta(days=1)).isoformat()
    yarin_izin = sql_all("""SELECT p.ad, p.soyad, i.baslangic, i.bitis
        FROM izin i JOIN personel p ON p.id=i.personel_id
        WHERE i.baslangic = ?""", (yarin,))
    if yarin_izin:
        uyari_say += len(yarin_izin)
        uyari_metinleri.append(f"Yarın {len(yarin_izin)} kişi izne başlıyor.")
        with st.expander(f"🔵 Yarın Başlayacak İzinler"):
            st.dataframe(pd.DataFrame(yarin_izin), use_container_width=True, hide_index=True)

    if uyari_say == 0:
        st.success("Hiçbir uyarı yok.")
    else:
        if st.button("🔊 Uyarıları Sesli Oku"):
            metin = "Uyarılar. " + " ".join(uyari_metinleri)
            js = f"""
            <script>
            var msg = new SpeechSynthesisUtterance("{metin}");
            msg.lang = 'tr-TR';
            window.speechSynthesis.speak(msg);
            </script>
            """
            st.components.v1.html(js, height=0)

    # ... (diğer bilgi sayfası içeriği aynen korunur) ...

# ---------- ANA ----------
def main():
    st.set_page_config(page_title="Ordino Yağcı", page_icon="⚓", layout="centered")
    st.markdown("""
    <style>
        .stApp { background: #1a1a2e; }
        .main .block-container {
            background: #2b2b3d; border-radius: 20px; padding: 1.5rem 1rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4); margin-top: 10px; color: #f0f0f0;
            max-width: 650px; margin-left: auto; margin-right: auto;
        }
        h1, h2, h3, h4, h5, h6, p, span, div, label { color: #f0f0f0 !important; }
        .stTabs [role="tablist"] { gap: 0.2rem; flex-wrap: wrap; }
        .stTabs [role="tab"] {
            background: #3a3a4e; border: none; border-radius: 10px;
            padding: 0.4rem 0.6rem; color: #cccccc !important; font-weight: 500;
            font-size: 0.85rem;
        }
        .stTabs [aria-selected="true"] { background: #f3831f; color: #ffffff !important; }
        .stButton > button {
            background: #f3831f; color: white; border: none; border-radius: 10px;
            padding: 0.5rem 1rem; font-weight: 600; transition: all 0.2s;
            width: 100%; min-height: 44px;
        }
        .stButton > button:hover { background: #d35400; }
    </style>
    """, unsafe_allow_html=True)

    init_db()
    st.title("⚓ Ordino Yağcı Planlaması")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["🚢 Gemiler", "👷 Personel", "📅 İzin", "⚙️ Çarkçı", "✦ Öneri", "📊 Bilgi"]
    )
    with tab1: _sayfa_excel()
    with tab2: _sayfa_personel()
    with tab3: _sayfa_izin()
    with tab4: _sayfa_carkci()
    with tab5: _sayfa_oneri()
    with tab6: _sayfa_bilgi()

if __name__ == "__main__":
    main()
