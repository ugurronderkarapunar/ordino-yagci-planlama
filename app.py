"""
Ordino Yağcı Planlaması — Tüm Özellikler Dahil (puan_kirma hatası düzeltildi)
Çalıştır: streamlit run app.py
"""
from __future__ import annotations

import json
import sqlite3
import calendar as _cal
from datetime import date, timedelta
from pathlib import Path
import io

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import os

# ---------- VERİTABANI ----------
DB_PATH = Path(__file__).parent / "ordino.db"

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

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS gemi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT UNIQUE NOT NULL, kod TEXT)""")

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

    # Eksik sütunları ekle (personel)
    c.execute("PRAGMA table_info(personel)")
    p_cols = [col[1] for col in c.fetchall()]
    personel_columns = [
        ("gemi_id_list", "TEXT"),
        ("makine_tipi_id_list", "TEXT"),
        ("gemiden_cekilme", "INTEGER DEFAULT 0"),
        ("carkci_ile_sorun", "INTEGER DEFAULT 0"),
        ("carkci_sorun_notu", "TEXT"),
        ("gemi_tutumu", "TEXT"),
        ("izin_tercih_gunleri", "TEXT"),
        ("izin_saat_araligi", "TEXT"),
        ("is_kalitesi", "INTEGER"),
        ("performans_notu", "TEXT"),
        ("aktif", "INTEGER DEFAULT 1")
    ]
    for col, typ in personel_columns:
        if col not in p_cols:
            try:
                c.execute(f"ALTER TABLE personel ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # Sütun zaten varsa hata verme

    # Eksik sütunları ekle (izin)
    c.execute("PRAGMA table_info(izin)")
    if "gunler_json" not in [col[1] for col in c.fetchall()]:
        try:
            c.execute("ALTER TABLE izin ADD COLUMN gunler_json TEXT")
        except sqlite3.OperationalError:
            pass

    # Eksik sütunları ekle (carkci)
    c.execute("PRAGMA table_info(carkci)")
    c_cols = [col[1] for col in c.fetchall()]
    if "vardiya_gunleri" not in c_cols:
        try:
            c.execute("ALTER TABLE carkci ADD COLUMN vardiya_gunleri TEXT")
        except sqlite3.OperationalError:
            pass
    if "puan_kirma" not in c_cols:
        try:
            c.execute("ALTER TABLE carkci ADD COLUMN puan_kirma INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

# ---------- KONFİG ----------
load_dotenv()
def get_admin_credentials():
    if hasattr(st, "secrets") and "ORDINO_ADMIN_USER" in st.secrets:
        return st.secrets["ORDINO_ADMIN_USER"], st.secrets["ORDINO_ADMIN_PASSWORD"]
    return os.getenv("ORDINO_ADMIN_USER","admin"), os.getenv("ORDINO_ADMIN_PASSWORD","123456")

# ---------- YARDIMCI ----------
GUNLER_TR = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
AY_ADLARI = ["","Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
             "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
VARDIYA_TIPLERI = ["SABIT","GRUPCU","IZINCI","8_5"]

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

# ---------- TAKVİM HTML ----------
def _takvim_html(yil: int, ay: int, isaretli: set[date]) -> str:
    son_gun = _cal.monthrange(yil, ay)[1]
    ilk_gun_haftaici = date(yil, ay, 1).weekday()
    bugun = date.today()
    css = """
    <style>
    .cal{font-family:system-ui,sans-serif;max-width:400px;margin:0 auto;
         background:#fff;border-radius:16px;padding:16px;box-shadow:0 2px 10px rgba(0,0,0,0.05);}
    .cal-title{text-align:center;font-size:18px;font-weight:600;color:#1a1a1a;margin-bottom:12px;}
    .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}
    .cal-hdr{text-align:center;font-size:12px;font-weight:600;color:#666;padding:6px 0;}
    .cal-cell{text-align:center;padding:10px 2px;border-radius:10px;font-size:14px;font-weight:500;}
    .cal-empty{background:transparent;}
    .cal-normal{background:#f9f9f9;color:#333;}
    .cal-izin{background:#f3831f;color:#fff;font-weight:600;box-shadow:0 2px 5px rgba(243,131,31,0.3);}
    .cal-bugun{background:#fff;color:#f3831f;border:2px solid #f3831f;font-weight:700;}
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

# ---------- ÖNERİ MOTORU ----------
def vardiya_plani_kontrol(gemi_id, makine_tipi_id, tarih):
    t_str = tarih.isoformat()
    row = sql_one("SELECT personel_id FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", 
                  (gemi_id, makine_tipi_id, t_str))
    return row["personel_id"] if row else None

def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5):
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
        mids = _id_listesi(p.get("makine_tipi_id_list")) or ([p["makine_tipi_id"]] if p.get("makine_tipi_id") else [])
        if makine_tipi_id not in mids: continue
        gids = _id_listesi(p.get("gemi_id_list")) or ([p.get("gemi_id")] if p.get("gemi_id") else [])
        if gemi_id not in gids: continue
        if p.get("carkci_ile_sorun"): continue
        vardiya_puan = {"IZINCI":100,"GRUPCU":80,"SABIT":60,"8_5":40}.get(p.get("vardiya_tipi",""),50)
        kalite_puan = (p.get("is_kalitesi") or 3) * 10
        toplam_puan = vardiya_puan + kalite_puan
        sonuclar.append({**p, "puan": toplam_puan, "uyari_8_5": p.get("vardiya_tipi")=="8_5", "zaten_atanmis": False})
    sonuclar.sort(key=lambda x: -x["puan"])
    return sonuclar[:limit]

def to_dict_rows(oneriler):
    tum_mak = {r["id"]: r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
    rows = []
    for o in oneriler:
        mids = _id_listesi(o.get("makine_tipi_id_list")) or ([o["makine_tipi_id"]] if o.get("makine_tipi_id") else [])
        rows.append({
            "id": o["id"],
            "ad_soyad": f"{o['ad']} {o['soyad']}",
            "vardiya": o.get("vardiya_tipi","-"),
            "makine": ", ".join(tum_mak.get(m,str(m)) for m in mids),
            "puan": o["puan"],
            "uyari_8_5": o.get("uyari_8_5",False),
            "zaten_atanmis": o.get("zaten_atanmis", False)
        })
    return rows

# ---------- SAYFA: GEMİLER ----------
def _sayfa_excel():
    st.subheader("🚢 Gemiler & Makine Yönetimi")
    with st.form("gemi_ekle_form", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        gad  = c1.text_input("Gemi Adı")
        gkod = c2.text_input("Gemi Kodu (opsiyonel)")
        mad  = c3.text_input("Makine Tipi Adı")
        if st.form_submit_button("➕ Ekle"):
            if not gad.strip() or not mad.strip():
                st.error("Gemi adı ve makine tipi adı zorunlu.")
            else:
                try: sql_run("INSERT INTO gemi(ad,kod) VALUES(?,?)",(gad.strip(),gkod.strip() or None))
                except: st.warning("Gemi zaten kayıtlı.")
                try: sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(mad.strip(),))
                except: st.warning("Makine tipi zaten kayıtlı.")
                st.success("Başarıyla eklendi.")
                st.rerun()

    st.divider()
    g_rows = sql_all("""SELECT g.id,g.ad,g.kod,COUNT(p.id) AS personel_sayisi
        FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad""")
    st.dataframe(pd.DataFrame(g_rows), use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        with st.expander("✏️ Gemi Düzenle / Sil"):
            if g_rows:
                g_map = {f"{r['ad']} (ID:{r['id']})": r for r in g_rows}
                gs = st.selectbox("Gemi Seç", list(g_map.keys()), key="gd_sec")
                gr = g_map[gs]
                na = st.text_input("Yeni Ad", value=gr["ad"] or "", key="gd_ad")
                nk = st.text_input("Yeni Kod", value=gr["kod"] or "", key="gd_kod")
                if st.button("Güncelle", key="btn_gd"):
                    if not na.strip(): st.error("Ad boş olamaz.")
                    else:
                        sql_run("UPDATE gemi SET ad=?,kod=? WHERE id=?",(na.strip(),nk.strip() or None,gr["id"]))
                        st.success("Güncellendi."); st.rerun()
                if st.button("Gemiyi Sil", type="secondary", key="btn_gsil"):
                    b = sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id=?",(int(gr['id']),))
                    if b and b["c"]>0: 
                        st.error("Bu gemiye bağlı personel var. Önce onları güncelleyin.")
                    else:
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
                    if b and b["c"]>0: 
                        st.error("Bu makine tipine bağlı personel var.")
                    else:
                        sql_run("DELETE FROM vardiya_plan WHERE makine_tipi_id=?",(int(mr['id']),))
                        sql_run("DELETE FROM makine_tipi WHERE id=?",(int(mr['id']),))
                        st.success("Silindi."); st.rerun()
            else: st.info("Makine tipi yok.")

# ---------- SAYFA: PERSONEL ----------
def _sayfa_personel():
    st.subheader("👷 Personel Yönetimi")
    gemiler   = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")

    st.caption("Hızlı Filtrele:")
    cols = st.columns(len(VARDIYA_TIPLERI)+1)
    if cols[0].button("Tümü", key="f_hepsi"):
        st.session_state.filtre_vt = None
    for i, vt in enumerate(VARDIYA_TIPLERI):
        if cols[i+1].button(vt, key=f"f_{vt}"):
            st.session_state.filtre_vt = vt

    filtre_vt = st.session_state.get("filtre_vt", None)

    query = """SELECT p.id,p.ad,p.soyad,g.ad AS gemi,p.gemi_id_list,
               p.makine_tipi_id_list,p.vardiya_tipi,p.vardiya_gunleri,
               p.gemiden_cekilme,p.carkci_ile_sorun,p.gemi_tutumu,
               p.izin_tercih_gunleri,p.izin_saat_araligi,p.is_kalitesi,p.performans_notu
        FROM personel p LEFT JOIN gemi g ON g.id=p.gemi_id"""
    params = ()
    if filtre_vt:
        query += " WHERE p.vardiya_tipi = ?"
        params = (filtre_vt,)
    query += " ORDER BY p.id DESC"
    rows = sql_all(query, params)

    for s in rows:
        s["vardiya_gunleri"] = _json_gunleri_metne(s.get("vardiya_gunleri"))
        s["izin_tercih_gunleri"] = _json_gunleri_metne(s.get("izin_tercih_gunleri"))
        mids = _id_listesi(s.get("makine_tipi_id_list"))
        s["makine_tipleri"] = ", ".join([str(m) for m in mids if m]) if mids else "-"
        gids = _id_listesi(s.get("gemi_id_list"))
        s["gemiler"] = ", ".join([str(g) for g in gids if g]) if gids else (s.get("gemi") or "-")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if not gemiler or not makineler:
        st.warning("Önce Gemiler sekmesinden gemi ve makine tipi ekleyin."); return

    with st.expander("➕ Yeni Personel Ekle"):
        c1,c2 = st.columns(2)
        ad    = c1.text_input("Ad", key="p_ad")
        soyad = c2.text_input("Soyad", key="p_soyad")
        vt    = st.selectbox("Vardiya Tipi", VARDIYA_TIPLERI, key="p_vt")
        mak_sec = st.multiselect("Bildiği Makine Tipleri", [r["id"] for r in makineler],
                                 format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i), key="p_mak")
        if vt in ("GRUPCU","IZINCI"):
            gem_list = st.multiselect("Atandığı Gemiler", [r["id"] for r in gemiler],
                                      format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="p_gem_list")
            gem_tek = int(gem_list[0]) if gem_list else None
        else:
            gem_tek_sel = st.selectbox("Gemi", [r["id"] for r in gemiler],
                                     format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="p_gem_tek")
            gem_list = [int(gem_tek_sel)]
            gem_tek = int(gem_tek_sel)
        secilen  = st.multiselect("Vardiya Günleri", GUNLER_TR, default=["Pazartesi","Çarşamba","Cuma"], key="p_vg")
        gun_json = json.dumps([GUNLER_TR.index(x) for x in secilen])
        st.markdown("##### Profil")
        c3, c4 = st.columns(2)
        is_kal   = c3.slider("İş Kalitesi (1-5)",1,5,3,key="p_ik")
        gemi_tutumu = c4.selectbox("Gemi İçi Tutum",["Mükemmel","İyi","Orta","Gelişmeli"],key="p_tutum")
        izin_g = st.multiselect("Tercih Edilen İzin Günleri", GUNLER_TR, key="p_ig")
        izin_g_json = json.dumps([GUNLER_TR.index(x) for x in izin_g]) if izin_g else "[]"
        izin_bas = c3.time_input("İzin Başlangıç Saati", value=None, key="p_ib")
        izin_bit = c4.time_input("İzin Bitiş Saati", value=None, key="p_it")
        p_not    = st.text_area("Performans Notu", key="p_not")
        if st.button("Personel Kaydet", key="btn_p_kaydet"):
            if not ad or not soyad: st.error("Ad ve soyad zorunlu.")
            elif not mak_sec: st.error("En az bir makine tipi seçin.")
            else:
                try:
                    sql_run("""INSERT INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,
                        makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,gemi_tutumu,
                        izin_tercih_gunleri,izin_saat_araligi,is_kalitesi,performans_notu)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (ad,soyad,gem_tek,_gemi_id_json(gem_list),int(mak_sec[0]),
                         _makine_id_json(mak_sec),vt,gun_json,gemi_tutumu,izin_g_json,
                         f"{izin_bas.strftime('%H:%M')} - {izin_bit.strftime('%H:%M')}" if izin_bas and izin_bit else None,
                         is_kal, p_not.strip() or None))
                    st.success("Kaydedildi."); st.rerun()
                except Exception as e:
                    st.error(f"Kayıt hatası: {e}")

    with st.expander("✏️ Personel Düzenle / Sil"):
        pmap = _personel_label_map(sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad,soyad"))
        if not pmap: st.info("Personel yok."); return
        secim = st.selectbox("Personel Seç", list(pmap.keys()), key="p_d_sec")
        pid   = pmap[secim]
        mevcut = sql_one("SELECT * FROM personel WHERE id=?",(pid,))
        if not mevcut: return
        yeni_vt = st.selectbox("Vardiya Tipi", VARDIYA_TIPLERI,
                               index=VARDIYA_TIPLERI.index(mevcut["vardiya_tipi"]) if mevcut.get("vardiya_tipi") in VARDIYA_TIPLERI else 0, key="p_d_vt")
        mevcut_mids = _id_listesi(mevcut.get("makine_tipi_id_list")) or [mevcut["makine_tipi_id"]]
        yeni_mak = st.multiselect("Bildiği Makine Tipleri", [r["id"] for r in makineler],
                                  default=[m for m in mevcut_mids if m in [r["id"] for r in makineler]],
                                  format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i), key="p_d_mak")
        c1, c2 = st.columns(2)
        if c1.button("Güncelle", key="btn_p_gunc"):
            if not yeni_mak: st.error("En az bir makine tipi seçin.")
            else:
                try:
                    sql_run("""UPDATE personel SET vardiya_tipi=?, makine_tipi_id_list=?,
                        makine_tipi_id=? WHERE id=?""",
                        (yeni_vt, _makine_id_json(yeni_mak), int(yeni_mak[0]), pid))
                    st.success("Güncellendi."); st.rerun()
                except Exception as e:
                    st.error(f"Güncelleme hatası: {e}")
        if c2.button("Personeli Sil", type="secondary", key="btn_p_sil"):
            sql_run("DELETE FROM izin WHERE personel_id=?",(pid,))
            sql_run("DELETE FROM vardiya_plan WHERE personel_id=?",(pid,))
            sql_run("DELETE FROM personel WHERE id=?",(pid,))
            st.success("Personel ve ilişkili izinler silindi."); st.rerun()

# ---------- SAYFA: İZİN ----------
def _sayfa_izin():
    st.subheader("📅 İzin Yönetimi")
    plist = sql_all("SELECT id,ad,soyad,vardiya_gunleri FROM personel WHERE aktif=1 ORDER BY ad")
    if not plist: st.info("Önce personel ekleyin."); return

    col_form, col_cal = st.columns([1,1])
    with col_form:
        secim = st.selectbox("Personel", plist, format_func=lambda p: f"{p['ad']} {p['soyad']}", key="izin_p")
        pid   = secim["id"]
        bas   = st.date_input("Başlangıç", value=date.today(), key="iz_bas", format="DD.MM.YYYY")
        bit   = st.date_input("Bitiş", value=date.today(), key="iz_bit", format="DD.MM.YYYY")
        if bit >= bas:
            gun = gun_sayisi(bas, bit)
            st.info(f"📅 {gun} gün  ({bas.strftime('%d.%m.%Y')} – {bit.strftime('%d.%m.%Y')})")
        else:
            st.error("Bitiş başlangıçtan önce olamaz."); gun = 0
        notlar = st.text_area("Not", key="iz_not", height=80)
        if st.button("✅ İzin Kaydet", key="btn_iz_kaydet"):
            if gun <= 0: st.error("Geçersiz tarih aralığı.")
            else:
                sql_run("INSERT INTO izin(personel_id,baslangic,bitis,gun_sayisi,notlar) VALUES(?,?,?,?,?)",
                        (pid, bas.isoformat(), bit.isoformat(), gun, notlar or None))
                st.success(f"İzin kaydedildi."); st.rerun()

    with col_cal:
        bugun = date.today()
        ay_labels = {}
        ay_dates = []
        for delta in range(-2, 5):
            d = date(bugun.year, bugun.month, 1) + timedelta(days=32*delta)
            d = date(d.year, d.month, 1)
            if d not in ay_labels:
                ay_dates.append(d)
                ay_labels[f"{AY_ADLARI[d.month]} {d.year}"] = d
        secili_label = st.selectbox("Ay", list(ay_labels.keys()), index=2, key="iz_takvim_ay")
        secili_ay = ay_labels[secili_label]
        p_izinler = sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=?", (pid,))
        isaretli = set()
        for iz in p_izinler:
            try:
                d = date.fromisoformat(iz["baslangic"])
                b = date.fromisoformat(iz["bitis"])
                while d <= b:
                    if d.year == secili_ay.year and d.month == secili_ay.month:
                        isaretli.add(d)
                    d += timedelta(days=1)
            except: pass
        st.markdown(_takvim_html(secili_ay.year, secili_ay.month, isaretli), unsafe_allow_html=True)

    st.divider()
    st.markdown("#### Kayıtlı İzinler")
    izinler = sql_all("""SELECT i.id, p.ad, p.soyad, i.baslangic, i.bitis, i.gun_sayisi, i.notlar
                         FROM izin i JOIN personel p ON p.id=i.personel_id ORDER BY i.baslangic DESC LIMIT 100""")
    if not izinler:
        st.info("İzin kaydı yok.")
        return
    for iz in izinler:
        col1, col2, col3 = st.columns([4, 2, 1])
        col1.markdown(f"**{iz['ad']} {iz['soyad']}**  \n📅 {iz['baslangic']} → {iz['bitis']}  ·  {iz['gun_sayisi']} gün")
        col2.markdown("🟠 Aktif" if iz["baslangic"] <= date.today().isoformat() <= iz["bitis"] else "✅ Tamamlandı")
        if col3.button("🗑️", key=f"iz_sil_{iz['id']}", help="Sil"):
            sql_run("DELETE FROM izin WHERE id=?", (iz["id"],))
            st.success("İzin silindi."); st.rerun()

# ---------- SAYFA: ÇARKÇI ----------
def _sayfa_carkci():
    st.subheader("⚙️ Çarkçı Kayıtları")
    gemiler  = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    yagcilar = sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")
    if not gemiler or not yagcilar: st.warning("Gemi ve personel gerekli."); return
    c1,c2 = st.columns(2)
    with c1:
        ad    = st.text_input("Çarkçı Adı", key="ck_ad")
        soyad = st.text_input("Çarkçı Soyadı", key="ck_soyad")
        gid   = st.selectbox("Gemi",[r["id"] for r in gemiler],
                             format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i),key="ck_gemi")
        ck_vt = st.selectbox("Çarkçının Vardiyası", VARDIYA_TIPLERI, key="ck_vt")
        ck_g  = st.multiselect("Çarkçının Vardiya Günleri", GUNLER_TR, key="ck_gunler")
    with c2:
        yid_opts = [("(Seçilmedi)",None)] + [(f"{p['ad']} {p['soyad']}",p["id"]) for p in yagcilar]
        yid_sec  = st.selectbox("Sorunlu Yağcı",yid_opts,format_func=lambda x:x[0],key="ck_yagci")
        sorun = st.text_area("Sorun / Açıklama",key="ck_sorun")
        vn    = st.text_input("Vardiya Notu",key="ck_vnot")
        puan_kirma = st.slider("Puan Kırma (0-5)", 0, 5, 0, key="ck_puan")
    if st.button("Çarkçı Kaydı Oluştur",key="btn_ck"):
        if not ad or not soyad: st.error("Ad ve soyad zorunlu.")
        else:
            gun_j = json.dumps([GUNLER_TR.index(g) for g in ck_g]) if ck_g else "[]"
            pid_p = yid_sec[1]
            sql_run("""INSERT INTO carkci(ad,soyad,gemi_id,problemli_yagci_id,sorun_metni,
                       vardiya_notu,carkci_vardiya,vardiya_gunleri,puan_kirma) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (ad,soyad,gid,pid_p,sorun,vn,ck_vt,gun_j,puan_kirma))
            if pid_p:
                mevcut_puan = sql_one("SELECT is_kalitesi FROM personel WHERE id=?", (pid_p,))
                if mevcut_puan:
                    yeni_puan = max(1, (mevcut_puan["is_kalitesi"] or 3) - puan_kirma)
                    sql_run("UPDATE personel SET is_kalitesi=?, carkci_ile_sorun=1, carkci_sorun_notu=? WHERE id=?",
                            (yeni_puan, sorun.strip() or None, pid_p))
                st.success("Kaydedildi; yağcının puanı düşürüldü ve öneri motorunda elendi.")
            else:
                st.success("Çarkçı kaydı oluşturuldu.")
            st.rerun()

    st.divider()
    cr = sql_all("""SELECT c.id,c.ad,c.soyad,g.ad AS gemi,c.carkci_vardiya,c.vardiya_gunleri,
               p.ad||' '||p.soyad AS yagci,c.sorun_metni,c.puan_kirma
        FROM carkci c LEFT JOIN gemi g ON g.id=c.gemi_id
        LEFT JOIN personel p ON p.id=c.problemli_yagci_id ORDER BY c.id DESC LIMIT 30""")
    for r in cr: r["vardiya_gunleri"] = _json_gunleri_metne(r.get("vardiya_gunleri"))
    st.dataframe(pd.DataFrame(cr), use_container_width=True, hide_index=True)

# ---------- SAYFA: ÖNERİ ----------
def _sayfa_oneri():
    st.subheader("✦ Yağcı Öneri ve Vardiya Planı")
    gemiler   = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler: st.warning("Gemi ve makine tipi gerekli."); return

    izinli_ids = bugun_izinli_ids()
    if izinli_ids:
        izinli_rows = sql_all(f"SELECT ad,soyad FROM personel WHERE id IN ({','.join('?'*len(izinli_ids))})", tuple(izinli_ids))
        st.warning("🟠 Bugün izinli: " + ", ".join(f"{r['ad']} {r['soyad']}" for r in izinli_rows))

    gid = st.selectbox("Gemi",[r["id"] for r in gemiler],
                       format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i),key="on_gemi")
    mid = st.selectbox("Makine Tipi",[r["id"] for r in makineler],
                       format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i),key="on_mak")
    ht  = st.date_input("Hedef Tarih",value=date.today(),key="on_ht",format="DD.MM.YYYY")

    tum_p = sql_all("SELECT id,ad,soyad,gemi_id,gemi_id_list FROM personel WHERE aktif=1 ORDER BY ad")
    gemi_p = [p for p in tum_p if p["gemi_id"]==gid or gid in _id_listesi(p.get("gemi_id_list"))]
    cik_opts = [("(Çıkan yağcı yok)", None)]
    for p in sorted(gemi_p, key=lambda x: (0 if x["id"] in izinli_ids else 1, x["ad"])):
        flag = " 🟠 İZİNDE" if p["id"] in izinli_ids else ""
        cik_opts.append((f"{p['ad']} {p['soyad']}{flag}", p["id"]))
    def_idx = 0
    for i,(lbl,pid) in enumerate(cik_opts):
        if pid in izinli_ids: def_idx=i; break
    cik_sec = st.selectbox("Çıkan Yağcı", cik_opts, format_func=lambda x: x[0], index=def_idx, key="on_cikan")
    cik_id  = cik_sec[1]

    if st.button("🔍 Önerileri Hesapla", key="btn_on"):
        out = onerileri_hesapla(gid, mid, ht, cik_id, limit=5)
        rows = to_dict_rows(out)
        if not rows:
            st.warning("Uygun aday bulunamadı.")
        else:
            for r in rows:
                if r.get("zaten_atanmis"):
                    st.success(f"Bu gemi, makine ve tarih için zaten atanmış: {r['ad_soyad']}")
                    break
            else:
                st.success(f"{len(rows)} aday:")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                for r in rows:
                    if r.get("uyari_8_5"):
                        st.warning(f"⚠️ {r['ad_soyad']} — 8/5 personeli, vardiya uyumunu kontrol edin.")

    st.divider()
    st.markdown("#### Vardiya Ata")
    personel_sec = st.selectbox("Personel Seç", [f"{p['ad']} {p['soyad']}" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")], key="vardiya_p")
    if st.button("✅ Bu Vardiyayı Kaydet", key="btn_vardiya_kaydet"):
        p_sec = sql_one("SELECT id FROM personel WHERE ad||' '||soyad=?", (personel_sec,))
        if p_sec:
            mevcut = vardiya_plani_kontrol(gid, mid, ht)
            if mevcut and mevcut != p_sec["id"]:
                st.error(f"Bu gemi, makine tipi ve tarih için zaten başka bir personel atanmış (ID: {mevcut}).")
            else:
                sql_run("INSERT INTO vardiya_plan(personel_id, gemi_id, makine_tipi_id, tarih) VALUES(?,?,?,?)",
                        (p_sec["id"], gid, mid, ht.isoformat()))
                st.success("Vardiya plana kaydedildi.")

# ---------- SAYFA: BİLGİ ----------
def _sayfa_bilgi():
    st.subheader("📊 Durum Özeti ve Grafikler")
    def cnt(q,p=()): return (sql_one(q,p) or {"c":0})["c"]
    col1, col2, col3 = st.columns(3)
    col1.metric("Toplam Personel", cnt("SELECT COUNT(*) AS c FROM personel"))
    col2.metric("Toplam Gemi", cnt("SELECT COUNT(*) AS c FROM gemi"))
    col3.metric("Bugün İzinde", cnt("SELECT COUNT(*) AS c FROM izin WHERE date('now') BETWEEN baslangic AND bitis"))

    # Gemilere göre personel dağılımı (bar chart)
    gemi_bazli = sql_all("""SELECT g.ad AS gemi, COUNT(p.id) AS sayi
        FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY sayi DESC""")
    if gemi_bazli:
        df = pd.DataFrame(gemi_bazli).set_index('gemi')
        st.subheader("Gemilere Göre Personel Dağılımı")
        st.bar_chart(df, use_container_width=True)

    # Vardiya tiplerine göre dağılım (bar chart)
    vardiya_dagilim = sql_all("SELECT vardiya_tipi, COUNT(*) AS sayi FROM personel WHERE aktif=1 GROUP BY vardiya_tipi")
    if vardiya_dagilim:
        df2 = pd.DataFrame(vardiya_dagilim).set_index('vardiya_tipi')
        st.subheader("Vardiya Tiplerine Göre Personel")
        st.bar_chart(df2, use_container_width=True)

    # Bugün izinde olanlar
    izinliler = sql_all("""SELECT p.ad,p.soyad,i.baslangic,i.bitis,i.gun_sayisi
        FROM izin i JOIN personel p ON p.id=i.personel_id
        WHERE date('now') BETWEEN i.baslangic AND i.bitis ORDER BY p.ad""")
    if izinliler:
        st.markdown("#### 🟠 Bugün İzinde Olan Personel")
        st.dataframe(pd.DataFrame(izinliler), use_container_width=True, hide_index=True)

    # Vardiya planı dışa aktar
    st.divider()
    st.markdown("#### 📥 Vardiya Planı Excel Çıktısı")
    plan = sql_all("""SELECT v.tarih, g.ad AS gemi, m.ad AS makine, p.ad||' '||p.soyad AS personel
        FROM vardiya_plan v
        JOIN gemi g ON v.gemi_id=g.id
        JOIN makine_tipi m ON v.makine_tipi_id=m.id
        JOIN personel p ON v.personel_id=p.id
        ORDER BY v.tarih DESC""")
    if plan:
        df_plan = pd.DataFrame(plan)
        st.dataframe(df_plan, use_container_width=True, hide_index=True)
        towrite = io.BytesIO()
        df_plan.to_excel(towrite, index=False, sheet_name='Vardiya Planı')
        towrite.seek(0)
        st.download_button(
            label="📥 Excel Olarak İndir",
            data=towrite,
            file_name=f"vardiya_plani_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Henüz vardiya planı kaydı yok.")

# ---------- ANA ----------
def main():
    st.set_page_config(page_title="Ordino Yağcı", page_icon="⚓", layout="centered", initial_sidebar_state="collapsed")
    st.markdown("""
    <style>
        .stApp { background: #f5f7fa; }
        .main .block-container {
            background: #ffffff; border-radius: 20px; padding: 2rem 1.5rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05); margin-top: 20px;
        }
        h2, h3 { color: #1a1a1a !important; }
        .stTabs [role="tablist"] { gap: 0.5rem; }
        .stTabs [role="tab"] {
            background: #f0f2f6; border: none; border-radius: 12px;
            padding: 0.6rem 1rem; color: #4a5568; font-weight: 500;
        }
        .stTabs [aria-selected="true"] {
            background: #f3831f; color: #ffffff !important;
        }
        .stButton > button {
            background: #f3831f; color: white; border: none; border-radius: 12px;
            padding: 0.5rem 1rem; font-weight: 600; transition: all 0.2s;
        }
        .stButton > button:hover { background: #d35400; box-shadow: 0 4px 10px rgba(243,131,31,0.4); }
        .stDataFrame { font-size: 14px; }
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
