"""
Ordino Yağcı Planlaması — Streamlit web uygulaması (tek dosya)
Çalıştır: streamlit run app.py
"""
from __future__ import annotations

import json
import sqlite3
import calendar as _cal
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import os

# ---------- VERİTABANI ----------
DB_PATH = Path(__file__).parent / "ordino.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
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
        is_kalitesi INTEGER, performans_notu TEXT, aktif INTEGER DEFAULT 1,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id),
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS izin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personel_id INTEGER, baslangic TEXT, bitis TEXT,
        gun_sayisi INTEGER, notlar TEXT, gunler_json TEXT,
        FOREIGN KEY(personel_id) REFERENCES personel(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS carkci (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT, soyad TEXT, gemi_id INTEGER,
        problemli_yagci_id INTEGER, sorun_metni TEXT,
        vardiya_notu TEXT, carkci_vardiya TEXT, vardiya_gunleri TEXT,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id),
        FOREIGN KEY(problemli_yagci_id) REFERENCES personel(id))""")

    # Eksik sütunları ekle
    c.execute("PRAGMA table_info(personel)")
    p_cols = [col[1] for col in c.fetchall()]
    for col, typ in [
        ("gemi_id_list","TEXT"),("makine_tipi_id_list","TEXT"),
        ("gemiden_cekilme","INTEGER DEFAULT 0"),("carkci_ile_sorun","INTEGER DEFAULT 0"),
        ("carkci_sorun_notu","TEXT"),("gemi_tutumu","TEXT"),
        ("izin_tercih_gunleri","TEXT"),("izin_saat_araligi","TEXT"),
        ("is_kalitesi","INTEGER"),("performans_notu","TEXT"),("aktif","INTEGER DEFAULT 1"),
    ]:
        if col not in p_cols:
            c.execute(f"ALTER TABLE personel ADD COLUMN {col} {typ}")

    c.execute("PRAGMA table_info(izin)")
    if "gunler_json" not in [col[1] for col in c.fetchall()]:
        c.execute("ALTER TABLE izin ADD COLUMN gunler_json TEXT")

    c.execute("PRAGMA table_info(carkci)")
    if "vardiya_gunleri" not in [col[1] for col in c.fetchall()]:
        c.execute("ALTER TABLE carkci ADD COLUMN vardiya_gunleri TEXT")

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
    return bool(sql_one("SELECT id FROM izin WHERE personel_id=? AND ?>=baslangic AND ?<=bitis",
                        (pid, t, t)))

# ---------- TAKVİM HTML ----------
def _takvim_html(yil: int, ay: int, isaretli: set[date]) -> str:
    son_gun = _cal.monthrange(yil, ay)[1]
    ilk_gun_haftaici = date(yil, ay, 1).weekday()  # 0=Pzt
    bugun = date.today()

    css = """
    <style>
    .cal{font-family:system-ui,sans-serif;max-width:380px;
         background:#fffaf4;border:1px solid #f0c8a0;border-radius:14px;padding:14px;}
    .cal-title{text-align:center;font-size:16px;font-weight:700;color:#7a3c00;
               margin-bottom:10px;}
    .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;}
    .cal-hdr{text-align:center;font-size:11px;font-weight:700;
             color:#cc7000;padding:4px 0;}
    .cal-cell{text-align:center;padding:8px 2px;border-radius:8px;
              font-size:13px;font-weight:500;}
    .cal-empty{background:transparent;}
    .cal-normal{background:#fff;color:#7a3c00;border:1px solid #f0c8a0;}
    .cal-izin{background:#e67e22;color:#fff;border:1px solid #c96010;font-weight:700;}
    .cal-bugun{background:#fff0d0;color:#7a3c00;border:2px solid #e67e22;font-weight:700;}
    .cal-izin.cal-bugun{background:#bf5c10;color:#fff;border:2px solid #7a3c00;}
    </style>
    """
    html = css + f'<div class="cal"><div class="cal-title">{AY_ADLARI[ay]} {yil}</div>'
    html += '<div class="cal-grid">'
    for g in ["Pt","Sa","Ça","Pe","Cu","Ct","Pz"]:
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
def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5):
    tum = sql_all("""SELECT id,ad,soyad,vardiya_tipi,gemi_id,gemi_id_list,
                            makine_tipi_id,makine_tipi_id_list,carkci_ile_sorun
                     FROM personel WHERE aktif=1""")
    sonuclar = []
    for p in tum:
        if cikan_id and p["id"] == cikan_id: continue
        if izinde_mi(p["id"], hedef_tarih): continue
        mids = _id_listesi(p.get("makine_tipi_id_list")) or ([p["makine_tipi_id"]] if p.get("makine_tipi_id") else [])
        if makine_tipi_id not in mids: continue
        if p.get("carkci_ile_sorun"): continue
        puan = {"IZINCI":100,"GRUPCU":80,"SABIT":60,"8_5":40}.get(p.get("vardiya_tipi",""),50)
        sonuclar.append({**p,"puan":puan,"uyari_8_5":p.get("vardiya_tipi")=="8_5"})
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
        })
    return rows

# ---------- SAYFA: GEMİLER ----------
def _sayfa_excel():
    st.subheader("Gemiler — gemi ve makine tipi yönetimi")
    with st.form("gemi_ekle_form", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        gad  = c1.text_input("Gemi adı")
        gkod = c2.text_input("Gemi kodu (opsiyonel)")
        mad  = c3.text_input("Makine tipi adı")
        if st.form_submit_button("➕ Gemi + Makine tipi ekle"):
            if not gad.strip() or not mad.strip():
                st.error("Gemi adı ve makine tipi adı zorunlu.")
            else:
                try: sql_run("INSERT INTO gemi(ad,kod) VALUES(?,?)",(gad.strip(),gkod.strip() or None))
                except: st.warning("Gemi zaten kayıtlı.")
                try: sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(mad.strip(),))
                except: st.warning("Makine tipi zaten kayıtlı.")
                st.success("İşlendi."); st.rerun()

    st.divider()
    st.markdown("#### Kayıtlı gemiler")
    g_rows = sql_all("""SELECT g.id,g.ad,g.kod,COUNT(p.id) AS personel_sayisi
        FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad""")
    st.dataframe(pd.DataFrame(g_rows), use_container_width=True)

    with st.expander("✏️ Gemi düzenle"):
        if g_rows:
            g_map = {f"{r['ad']} (ID:{r['id']})": r for r in g_rows}
            gs = st.selectbox("Gemi", list(g_map.keys()), key="gd_sec")
            gr = g_map[gs]
            na = st.text_input("Yeni ad",  value=gr["ad"]  or "", key="gd_ad")
            nk = st.text_input("Yeni kod", value=gr["kod"] or "", key="gd_kod")
            if st.button("Güncelle", key="btn_gd"):
                if not na.strip(): st.error("Ad boş olamaz.")
                else:
                    sql_run("UPDATE gemi SET ad=?,kod=? WHERE id=?",(na.strip(),nk.strip() or None,gr["id"]))
                    st.success("Güncellendi."); st.rerun()
        else: st.info("Gemi yok.")

    gid_sil = st.number_input("Silinecek gemi ID", min_value=1, step=1, key="gid_sil")
    if st.button("Gemiyi sil", type="secondary", key="btn_gsil"):
        b = sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id=?",(int(gid_sil),))
        if b and b["c"]>0: st.error("Bağlı personel var.")
        else: sql_run("DELETE FROM gemi WHERE id=?",(int(gid_sil),)); st.success("Silindi."); st.rerun()

    st.divider()
    st.markdown("#### Kayıtlı makine tipleri")
    m_rows = sql_all("""SELECT m.id,m.ad,COUNT(p.id) AS personel_sayisi
        FROM makine_tipi m LEFT JOIN personel p ON p.makine_tipi_id=m.id GROUP BY m.id ORDER BY m.ad""")
    st.dataframe(pd.DataFrame(m_rows), use_container_width=True)

    with st.expander("✏️ Makine tipi düzenle"):
        if m_rows:
            m_map = {f"{r['ad']} (ID:{r['id']})": r for r in m_rows}
            ms = st.selectbox("Makine tipi", list(m_map.keys()), key="md_sec")
            mr = m_map[ms]
            nm = st.text_input("Yeni ad", value=mr["ad"] or "", key="md_ad")
            if st.button("Güncelle", key="btn_md"):
                if not nm.strip(): st.error("Ad boş olamaz.")
                else:
                    sql_run("UPDATE makine_tipi SET ad=? WHERE id=?",(nm.strip(),mr["id"]))
                    st.success("Güncellendi."); st.rerun()
        else: st.info("Makine tipi yok.")

    mid_sil = st.number_input("Silinecek makine tipi ID", min_value=1, step=1, key="mid_sil")
    if st.button("Makine tipini sil", type="secondary", key="btn_msil"):
        b = sql_one("SELECT COUNT(*) AS c FROM personel WHERE makine_tipi_id=?",(int(mid_sil),))
        if b and b["c"]>0: st.error("Bağlı personel var.")
        else: sql_run("DELETE FROM makine_tipi WHERE id=?",(int(mid_sil),)); st.success("Silindi."); st.rerun()

# ---------- SAYFA: PERSONEL ----------
def _sayfa_personel():
    st.subheader("Personel")
    rows = sql_all("""SELECT p.id,p.ad,p.soyad,g.ad AS gemi,p.gemi_id_list,
               p.makine_tipi_id_list,p.vardiya_tipi,p.vardiya_gunleri,
               p.gemiden_cekilme,p.carkci_ile_sorun,p.gemi_tutumu,
               p.izin_tercih_gunleri,p.izin_saat_araligi,p.is_kalitesi,p.performans_notu
        FROM personel p LEFT JOIN gemi g ON g.id=p.gemi_id ORDER BY p.id DESC""")
    tum_mak = {r["id"]:r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
    tum_gem = {r["id"]:r["ad"] for r in sql_all("SELECT id,ad FROM gemi")}
    satirlar=[]
    for s in rows:
        s["vardiya_gunleri"]     = _json_gunleri_metne(s.get("vardiya_gunleri"))
        s["izin_tercih_gunleri"] = _json_gunleri_metne(s.get("izin_tercih_gunleri"))
        mids = _id_listesi(s.get("makine_tipi_id_list"))
        s["makine_tipleri"] = ", ".join(tum_mak.get(m,str(m)) for m in mids) if mids else "-"
        gids = _id_listesi(s.get("gemi_id_list"))
        s["gemiler"] = ", ".join(tum_gem.get(g,str(g)) for g in gids) if gids else (s.get("gemi") or "-")
        satirlar.append(s)
    st.dataframe(pd.DataFrame(satirlar), use_container_width=True)

    gemiler   = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler:
        st.warning("Önce Gemiler sekmesinden gemi ve makine tipi ekleyin."); return

    with st.expander("➕ Yeni personel ekle"):
        c1,c2 = st.columns(2)
        ad    = c1.text_input("Ad",    key="p_ad")
        soyad = c2.text_input("Soyad", key="p_soyad")
        vt    = st.selectbox("Vardiya tipi", VARDIYA_TIPLERI, key="p_vt")
        mak_sec = st.multiselect("Bildiği makine tipleri",
            options=[r["id"] for r in makineler],
            format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i), key="p_mak")
        if vt in ("GRUPCU","IZINCI"):
            gem_list = st.multiselect("Atandığı gemiler",
                options=[r["id"] for r in gemiler],
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="p_gem_list")
            gem_tek = int(gem_list[0]) if gem_list else None
        else:
            gem_tek_sel = st.selectbox("Gemi",
                options=[r["id"] for r in gemiler],
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="p_gem_tek")
            gem_list = [int(gem_tek_sel)]; gem_tek = int(gem_tek_sel)
        secilen  = st.multiselect("Vardiya günleri", GUNLER_TR,
                                  default=["Pazartesi","Çarşamba","Cuma"], key="p_vg")
        gun_json = json.dumps([GUNLER_TR.index(x) for x in secilen]) if secilen else "[]"
        st.markdown("##### Profil")
        gemi_tutumu  = st.selectbox("Gemi içi tutum",["Mükemmel","İyi","Orta","Gelişmeli"],key="p_tutum")
        izin_g       = st.multiselect("Tercih edilen izin günleri", GUNLER_TR, key="p_ig")
        izin_g_json  = json.dumps([GUNLER_TR.index(x) for x in izin_g]) if izin_g else "[]"
        c3,c4 = st.columns(2)
        izin_bas = c3.time_input("İzin başlangıç saati",key="p_ib")
        izin_bit = c4.time_input("İzin bitiş saati",    key="p_it")
        is_kal   = st.slider("İş kalitesi (1-5)",1,5,4,key="p_ik")
        p_not    = st.text_area("Performans notu",key="p_not")
        if st.button("Personel kaydet",key="btn_p_kaydet"):
            if not ad or not soyad: st.error("Ad ve soyad zorunlu.")
            elif not mak_sec:       st.error("En az bir makine tipi seçin.")
            else:
                sql_run("""INSERT INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,
                    makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,gemi_tutumu,
                    izin_tercih_gunleri,izin_saat_araligi,is_kalitesi,performans_notu)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ad,soyad,gem_tek,_gemi_id_json(gem_list),int(mak_sec[0]),
                     _makine_id_json(mak_sec),vt,gun_json,gemi_tutumu,izin_g_json,
                     f"{izin_bas.strftime('%H:%M')} - {izin_bit.strftime('%H:%M')}",is_kal,p_not.strip() or None))
                st.success("Kaydedildi."); st.rerun()

    with st.expander("✏️ Personel düzenle / sil"):
        pmap = _personel_label_map(sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad,soyad"))
        if not pmap: st.info("Personel yok."); return
        secim  = st.selectbox("Personel seç", list(pmap.keys()), key="p_d_sec")
        pid    = pmap[secim]
        mevcut = sql_one("SELECT * FROM personel WHERE id=?",(pid,))
        if not mevcut: return
        yeni_vt = st.selectbox("Vardiya tipi", VARDIYA_TIPLERI,
            index=VARDIYA_TIPLERI.index(mevcut["vardiya_tipi"]) if mevcut.get("vardiya_tipi") in VARDIYA_TIPLERI else 0,
            key="p_d_vt")
        mevcut_mids = _id_listesi(mevcut.get("makine_tipi_id_list")) or ([mevcut["makine_tipi_id"]] if mevcut.get("makine_tipi_id") else [])
        yeni_mak = st.multiselect("Bildiği makine tipleri",
            options=[r["id"] for r in makineler],
            default=[m for m in mevcut_mids if m in [r["id"] for r in makineler]],
            format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i), key="p_d_mak")
        mevcut_gids = _id_listesi(mevcut.get("gemi_id_list")) or ([mevcut["gemi_id"]] if mevcut.get("gemi_id") else [])
        if yeni_vt in ("GRUPCU","IZINCI"):
            yeni_gem_list = st.multiselect("Atandığı gemiler",
                options=[r["id"] for r in gemiler],
                default=[g for g in mevcut_gids if g in [r["id"] for r in gemiler]],
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="p_d_gem_list")
            yeni_gem_tek = int(yeni_gem_list[0]) if yeni_gem_list else None
        else:
            g_opts  = [r["id"] for r in gemiler]
            def_idx = g_opts.index(mevcut_gids[0]) if mevcut_gids and mevcut_gids[0] in g_opts else 0
            yeni_gem_sel = st.selectbox("Gemi", options=g_opts, index=def_idx,
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="p_d_gem_tek")
            yeni_gem_list = [int(yeni_gem_sel)]; yeni_gem_tek = int(yeni_gem_sel)
        cekildi = st.selectbox("Gemiden çekildi mi?",["Hayır","Evet"],key="p_d_cek")
        ck_sor  = st.selectbox("Çarkçı sorunu var mı?",["Hayır","Evet"],key="p_d_ck")
        ck_not  = st.text_area("Sorun detayı",key="p_d_cknot") if ck_sor=="Evet" else ""
        c1,c2 = st.columns(2)
        if c1.button("Güncelle",key="btn_p_gunc"):
            if not yeni_mak: st.error("En az bir makine tipi seçin.")
            else:
                sql_run("""UPDATE personel SET vardiya_tipi=?,gemi_id=?,gemi_id_list=?,
                    makine_tipi_id=?,makine_tipi_id_list=?,gemiden_cekilme=?,
                    carkci_ile_sorun=?,carkci_sorun_notu=? WHERE id=?""",
                    (yeni_vt,yeni_gem_tek,_gemi_id_json(yeni_gem_list),int(yeni_mak[0]),
                     _makine_id_json(yeni_mak),1 if cekildi=="Evet" else 0,
                     1 if ck_sor=="Evet" else 0,ck_not.strip() or None,pid))
                st.success("Güncellendi."); st.rerun()
        if c2.button("Personeli sil",type="secondary",key="btn_p_sil"):
            sql_run("DELETE FROM personel WHERE id=?",(pid,))
            st.success("Silindi."); st.rerun()

# ---------- SAYFA: İZİN ----------
def _sayfa_izin():
    st.subheader("İzin Yönetimi")

    plist = sql_all("SELECT id,ad,soyad,vardiya_gunleri FROM personel WHERE aktif=1 ORDER BY ad")
    if not plist: st.info("Önce personel ekleyin."); return

    # ── YENİ İZİN ──────────────────────────────────────────────────────────
    st.markdown("#### Yeni izin ekle")
    col_form, col_cal = st.columns([1,1])

    with col_form:
        secim = st.selectbox("Personel", plist,
                             format_func=lambda p: f"{p['ad']} {p['soyad']}", key="izin_p")
        pid   = secim["id"]
        st.caption(f"Vardiya günleri: {_json_gunleri_metne(secim.get('vardiya_gunleri'))}")

        bas = st.date_input("Başlangıç", value=date.today(), key="iz_bas", format="DD.MM.YYYY")
        bit = st.date_input("Bitiş",     value=date.today(), key="iz_bit", format="DD.MM.YYYY")

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
                st.success(f"{secim['ad']} {secim['soyad']} → {gun} günlük izin kaydedildi.")
                st.rerun()

    # ── TAKVİM ──────────────────────────────────────────────────────────────
    with col_cal:
        st.markdown("**📅 İzin takvimi**")
        bugun = date.today()

        # Ay seçimi
        ay_list = []
        for delta in range(-2, 5):
            d = date(bugun.year, bugun.month, 1) + timedelta(days=32*delta)
            ay_list.append(date(d.year, d.month, 1))
        ay_list = sorted(set(ay_list))
        ay_labels = {d: f"{AY_ADLARI[d.month]} {d.year}" for d in ay_list}
        secili_ay = st.selectbox("Ay", options=ay_list,
                                 format_func=lambda d: ay_labels[d],
                                 index=2, key="iz_takvim_ay")

        # Seçili personelin bu aydaki izin günleri
        p_izinler = sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=?", (pid,))
        isaretli  = set()
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
        if isaretli:
            st.caption(f"🟠 = izinli  ·  Bu ayda {len(isaretli)} izin günü")

    st.divider()

    # ── KAYITLI İZİNLER — FİLTRE + SİLME ────────────────────────────────
    st.markdown("#### Kayıtlı izinler")

    filtre_opts = [{"id":0,"ad":"Tümü","soyad":""}] + plist
    filtre = st.selectbox("Personel filtresi", filtre_opts,
                          format_func=lambda p: "Tümü" if p["id"]==0 else f"{p['ad']} {p['soyad']}",
                          key="iz_filtre")

    q_base = """SELECT i.id, p.ad, p.soyad, i.baslangic, i.bitis, i.gun_sayisi, i.notlar
                FROM izin i JOIN personel p ON p.id=i.personel_id"""
    if filtre["id"] == 0:
        izinler = sql_all(q_base + " ORDER BY i.baslangic DESC LIMIT 100")
    else:
        izinler = sql_all(q_base + " WHERE i.personel_id=? ORDER BY i.baslangic DESC", (filtre["id"],))

    if not izinler:
        st.info("İzin kaydı yok.")
        return

    bugun_str = date.today().isoformat()
    for iz in izinler:
        aktif   = iz["baslangic"] <= bugun_str <= iz["bitis"]
        gelecek = iz["baslangic"] > bugun_str
        durum   = "🟠 **Aktif**" if aktif else ("🔵 Yaklaşan" if gelecek else "✅ Tamamlandı")

        c1, c2, c3 = st.columns([4, 2, 1])
        c1.markdown(
            f"**{iz['ad']} {iz['soyad']}**  \n"
            f"📅 {iz['baslangic']} → {iz['bitis']}  ·  {iz['gun_sayisi']} gün"
            + (f"  \n📝 _{iz['notlar']}_" if iz.get("notlar") else "")
        )
        c2.markdown(durum)
        # ── SİLME: unique key için izin ID kullan ─────────────────────
        if c3.button("🗑️", key=f"iz_sil_{iz['id']}", help="Bu izni sil"):
            sql_run("DELETE FROM izin WHERE id=?", (iz["id"],))
            st.success("İzin silindi.")
            st.rerun()
        st.markdown("---")

# ---------- SAYFA: ÇARKÇI ----------
def _sayfa_carkci():
    st.subheader("Çarkçı kayıtları")
    gemiler  = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    yagcilar = sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")
    if not gemiler or not yagcilar: st.warning("Gemi ve personel gerekli."); return
    c1,c2 = st.columns(2)
    with c1:
        ad    = st.text_input("Çarkçı adı",   key="ck_ad")
        soyad = st.text_input("Çarkçı soyadı",key="ck_soyad")
        gid   = st.selectbox("Gemi",[r["id"] for r in gemiler],
                             format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i),key="ck_gemi")
        ck_vt = st.selectbox("Çarkçının vardiyası", VARDIYA_TIPLERI, key="ck_vt")
        ck_g  = st.multiselect("Çarkçının vardiya günleri", GUNLER_TR, key="ck_gunler")
    with c2:
        yid_opts = [("(Seçilmedi)",None)] + [(f"{p['ad']} {p['soyad']}",p["id"]) for p in yagcilar]
        yid_sec  = st.selectbox("Sorunlu yağcı",yid_opts,format_func=lambda x:x[0],key="ck_yagci")
        sorun = st.text_area("Sorun / açıklama",key="ck_sorun")
        vn    = st.text_input("Vardiya notu",   key="ck_vnot")
    if st.button("Çarkçı kaydı oluştur",key="btn_ck"):
        if not ad or not soyad: st.error("Ad ve soyad zorunlu.")
        else:
            gun_j = json.dumps([GUNLER_TR.index(g) for g in ck_g]) if ck_g else "[]"
            pid_p = yid_sec[1]
            sql_run("""INSERT INTO carkci(ad,soyad,gemi_id,problemli_yagci_id,sorun_metni,
                       vardiya_notu,carkci_vardiya,vardiya_gunleri) VALUES(?,?,?,?,?,?,?,?)""",
                    (ad,soyad,gid,pid_p,sorun,vn,ck_vt,gun_j))
            if pid_p:
                sql_run("UPDATE personel SET carkci_ile_sorun=1,carkci_sorun_notu=? WHERE id=?",
                        (sorun.strip() or None,pid_p))
                st.success("Kaydedildi; yağcı öneri motorunda elendi.")
            else: st.success("Çarkçı kaydı oluşturuldu.")
            st.rerun()
    st.divider()
    cr = sql_all("""SELECT c.id,c.ad,c.soyad,g.ad AS gemi,c.carkci_vardiya,c.vardiya_gunleri,
               p.ad||' '||p.soyad AS yagci,c.sorun_metni
        FROM carkci c LEFT JOIN gemi g ON g.id=c.gemi_id
        LEFT JOIN personel p ON p.id=c.problemli_yagci_id ORDER BY c.id DESC LIMIT 30""")
    for r in cr: r["vardiya_gunleri"] = _json_gunleri_metne(r.get("vardiya_gunleri"))
    st.dataframe(pd.DataFrame(cr), use_container_width=True)

# ---------- SAYFA: ÖNERİ ----------
def _sayfa_oneri():
    st.subheader("Yağcı öneri sistemi")
    gemiler   = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler: st.warning("Gemi ve makine tipi gerekli."); return

    # Bugün izinli personeli banner olarak göster
    izinli_ids = bugun_izinli_ids()
    if izinli_ids:
        izinli_rows = sql_all(
            f"SELECT ad,soyad FROM personel WHERE id IN ({','.join('?'*len(izinli_ids))})",
            tuple(izinli_ids))
        st.warning("🟠 **Bugün izinli:** " + ", ".join(f"{r['ad']} {r['soyad']}" for r in izinli_rows))

    gid = st.selectbox("Gemi",[r["id"] for r in gemiler],
                       format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i),key="on_gemi")
    mid = st.selectbox("Makine tipi",[r["id"] for r in makineler],
                       format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i),key="on_mak")
    ht  = st.date_input("Hedef tarih",value=date.today(),key="on_ht",format="DD.MM.YYYY")

    # Çıkan yağcı listesi — izinliler otomatik önce gelir, işaretlenir
    tum_p = sql_all("SELECT id,ad,soyad,gemi_id,gemi_id_list FROM personel WHERE aktif=1 ORDER BY ad")
    gemi_p = [p for p in tum_p
              if p["gemi_id"]==gid or gid in _id_listesi(p.get("gemi_id_list"))]

    cik_opts = [("(Çıkan yağcı yok)", None)]
    # İzinlileri başa al
    for p in sorted(gemi_p, key=lambda x: (0 if x["id"] in izinli_ids else 1, x["ad"])):
        flag = " 🟠 İZİNDE" if p["id"] in izinli_ids else ""
        cik_opts.append((f"{p['ad']} {p['soyad']}{flag}", p["id"]))

    # İzinli biri varsa onu default seç
    def_idx = 0
    for i,(lbl,pid) in enumerate(cik_opts):
        if pid in izinli_ids: def_idx=i; break

    cik_sec = st.selectbox("Çıkan yağcı", cik_opts,
                           format_func=lambda x: x[0], index=def_idx, key="on_cikan")
    cik_id  = cik_sec[1]

    if st.button("🔍 Önerileri hesapla", key="btn_on"):
        out  = onerileri_hesapla(gid, mid, ht, cik_id, limit=5)
        rows = to_dict_rows(out)
        if not rows: st.warning("Uygun aday bulunamadı.")
        else:
            st.success(f"{len(rows)} aday:")
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            for r in rows:
                if r.get("uyari_8_5"):
                    st.warning(f"⚠️ {r['ad_soyad']} — 8/5 personeli, vardiya uyumunu kontrol edin.")

# ---------- SAYFA: BİLGİ ----------
def _sayfa_bilgi():
    st.subheader("Durum özeti")
    def cnt(q,p=()): return (sql_one(q,p) or {"c":0})["c"]
    st.markdown(f"""
| Metrik | Değer |
|---|---|
| Toplam personel | **{cnt("SELECT COUNT(*) AS c FROM personel")}** |
| Toplam gemi | **{cnt("SELECT COUNT(*) AS c FROM gemi")}** |
| Toplam izin kaydı | **{cnt("SELECT COUNT(*) AS c FROM izin")}** |
| Bugün izinde | **{cnt("SELECT COUNT(*) AS c FROM izin WHERE date('now') BETWEEN baslangic AND bitis")}** |
| Sabit | **{cnt("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi='SABIT'")}** |
| Grupçu | **{cnt("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi='GRUPCU'")}** |
| İzinci | **{cnt("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi='IZINCI'")}** |
| Tersane (8/5) | **{cnt("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi='8_5'")}** |
    """)
    gemi_bazli = sql_all("""SELECT g.ad AS gemi,COUNT(p.id) AS personel_sayisi
        FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad""")
    st.markdown("#### Gemilerde personel dağılımı")
    st.dataframe(pd.DataFrame(gemi_bazli), use_container_width=True)
    izinliler = sql_all("""SELECT p.ad,p.soyad,i.baslangic,i.bitis,i.gun_sayisi
        FROM izin i JOIN personel p ON p.id=i.personel_id
        WHERE date('now') BETWEEN i.baslangic AND i.bitis ORDER BY p.ad""")
    if izinliler:
        st.markdown("#### 🟠 Bugün izinde olan personel")
        st.dataframe(pd.DataFrame(izinliler), use_container_width=True)

# ---------- ANA ----------
def main():
    st.set_page_config(page_title="Ordino Yağcı Planlaması",page_icon="⚓",
                       layout="wide",initial_sidebar_state="collapsed")
    st.markdown("""<style>
    .stApp{background:linear-gradient(160deg,#fffaf4 0%,#fff0dc 100%);}
    [data-testid="stAppViewContainer"] .main .block-container{
      background:rgba(255,255,255,0.97);border-radius:14px;
      padding:1rem 1.2rem 1.5rem;border:1px solid #ffd2a1;
      box-shadow:0 8px 28px rgba(28,17,8,0.15);}
    .stTabs [role="tablist"]{overflow-x:auto;gap:.4rem;padding-bottom:.3rem;}
    .stTabs [role="tab"]{padding:.5rem .9rem;background:#fff5ea;
      border:1px solid #ffcb97;border-radius:8px;color:#5a320a;font-weight:600;}
    .stTabs [aria-selected="true"]{background:#f3831f!important;
      color:#fff!important;border-color:#f3831f!important;}
    .stButton button{background:#f3831f;color:#fff;border:1px solid #d66d12;
      border-radius:10px;font-weight:600;min-height:40px;}
    .stButton button:hover{background:#d96f14;}
    </style>""", unsafe_allow_html=True)

    init_db()
    # Kimlik doğrulama kaldırıldı – direkt uygulama başlar
    tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs(
        ["🚢 Gemiler","👷 Personel","📅 İzin","⚙️ Çarkçı","✦ Öneri","📊 Bilgi"])
    with tab1: _sayfa_excel()
    with tab2: _sayfa_personel()
    with tab3: _sayfa_izin()
    with tab4: _sayfa_carkci()
    with tab5: _sayfa_oneri()
    with tab6: _sayfa_bilgi()

if __name__ == "__main__":
    main()
