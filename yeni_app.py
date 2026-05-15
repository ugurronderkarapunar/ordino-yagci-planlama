"""
Ordino Yağcı Planlaması — TEK DOSYA Streamlit uygulaması.
Çalıştır: proje kökünde `streamlit run app.py`
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# VERİTABANI YÖNETİMİ (db modülü yerine)
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).resolve().parent / "ordino.db"

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db() -> None:
    """Gerekli tabloları oluşturur."""
    conn = _get_conn()
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
            gemiden_cekilme INTEGER DEFAULT 0,
            carkci_ile_sorun INTEGER DEFAULT 0,
            carkci_sorun_notu TEXT,
            gemi_tutumu TEXT,
            izin_tercih_gunleri TEXT DEFAULT '[]',
            izin_saat_araligi TEXT,
            is_kalitesi INTEGER DEFAULT 3,
            performans_notu TEXT,
            aktif INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS izin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personel_id INTEGER NOT NULL REFERENCES personel(id),
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
    """)
    conn.commit()
    conn.close()

def sql_run(query: str, params: tuple = ()) -> None:
    conn = _get_conn()
    conn.execute(query, params)
    conn.commit()
    conn.close()

def sql_all(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = _get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows

def sql_one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    conn = _get_conn()
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row

# ---------------------------------------------------------------------------
# YAPILANDIRMA (config, constants)
# ---------------------------------------------------------------------------
DEFAULT_AYARLAR = {
    "min_dinlenme_suresi_saat": 11,
    "max_haftalik_saat": 45,
    "yillik_izin_hakki": 14,
}

def get_admin_credentials() -> tuple[str, str]:
    """Ortam değişkenlerinden veya varsayılan admin bilgilerini döndürür."""
    user = os.environ.get("ORDINO_ADMIN_USER", "admin")
    pwd = os.environ.get("ORDINO_ADMIN_PASSWORD", "ordino123")
    return user, pwd

# ---------------------------------------------------------------------------
# TARİH YARDIMCILARI (vardiya_kurallari yerine)
# ---------------------------------------------------------------------------
def gun_sayisi(bas: date, bit: date) -> int:
    """İki tarih arasındaki gün sayısını (dahil) hesaplar."""
    return (bit - bas).days + 1

def izin_pzt_3gun(bas: date) -> tuple[date, date]:
    """Pazartesi başlayan izni 3 gün (Pzt–Sal–Çar) olarak ayarlar."""
    return bas, bas + timedelta(days=2)

# ---------------------------------------------------------------------------
# ÖNERİ MOTORU (oneri_motoru)
# ---------------------------------------------------------------------------
class YagciOneri:
    """Basit bir yağcı öneri kaydı."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def to_dict_rows(oneri_list: list[YagciOneri]) -> list[dict]:
    return [vars(o) for o in oneri_list]

def onerileri_hesapla(gemi_id: int, makine_id: int, hedef_tarih: date, cikan_yagci_id: int | None = None, limit: int = 5) -> list[YagciOneri]:
    """
    Gerçek öneri mantığının basit bir yerine koyma (stub).
    Şimdilik uygun personeli döndürür; gerçek motor entegre edilmemiştir.
    """
    # Uygun personeli bul: aynı gemiye bağlı olmayan, aktif, çarkçı sorunu olmayan
    query = """
        SELECT p.id, p.ad, p.soyad, g.ad as gemi_ad, m.ad as makine_ad, p.vardiya_tipi,
               p.is_kalitesi, p.performans_notu
        FROM personel p
        LEFT JOIN gemi g ON g.id = p.gemi_id
        LEFT JOIN makine_tipi m ON m.id = p.makine_tipi_id
        WHERE p.aktif = 1 AND p.gemiden_cekilme = 0 AND p.carkci_ile_sorun = 0
          AND p.gemi_id != ?
          AND p.makine_tipi_id = ?
        ORDER BY p.is_kalitesi DESC
        LIMIT ?
    """
    rows = sql_all(query, (gemi_id, makine_id, limit))
    oneriler = []
    for i, r in enumerate(rows):
        oneri = YagciOneri(
            sira=i+1,
            personel_id=r["id"],
            ad_soyad=f"{r['ad']} {r['soyad']}",
            gemi=r["gemi_ad"],
            makine=r["makine_ad"],
            vardiya_tipi=r["vardiya_tipi"],
            uyari_8_5="8/5 uyarısı" if r["vardiya_tipi"] == "8_5" else "",
            is_kalitesi=r["is_kalitesi"],
            skor=r["is_kalitesi"],  # geçici
        )
        oneriler.append(oneri)
    return oneriler

# ---------------------------------------------------------------------------
# PLANLAMA SERVİSİ (planning_service)
# ---------------------------------------------------------------------------
def bugun_plani_olustur() -> list[dict]:
    """Bugünün planını döndürür (şimdilik boş)."""
    return []

# ---------------------------------------------------------------------------
# YAPBOZ EKRANI (ui/v8_yapboz)
# ---------------------------------------------------------------------------
def render_yapboz() -> None:
    """Yapboz sekmesi içeriği."""
    st.subheader("Yapboz (v8) — Vardiya Planı Atama")
    st.info("Bu özellik henüz tek dosyaya taşınmadı. Geliştirme aşamasında.")
    st.markdown("Burada sürükle-bırak ile yağcıların gemilere atanması sağlanacak.")

# ---------------------------------------------------------------------------
# ANA UYGULAMA
# ---------------------------------------------------------------------------
GUNLER_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _json_gunleri_metne(value: str | None) -> str:
    if not value:
        return "-"
    try:
        idx_list = json.loads(value)
        if not isinstance(idx_list, list):
            return "-"
        adlar = [GUNLER_TR[int(i)] for i in idx_list if isinstance(i, int) and 0 <= int(i) < len(GUNLER_TR)]
        return ", ".join(adlar) if adlar else "-"
    except (ValueError, TypeError, json.JSONDecodeError):
        return "-"


def _personel_label_map(rows: list) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        label = f"{r['ad']} {r['soyad']} (ID: {r['id']})"
        out[label] = int(r["id"])
    return out


def _login_form() -> None:
    st.title("Ordino — Yağcı planlaması")
    u_def, p_def = get_admin_credentials()
    with st.form("login"):
        uid = st.text_input("Kullanıcı ID")
        pwd = st.text_input("Şifre", type="password")
        ok = st.form_submit_button("Giriş")
    if ok:
        if uid == u_def and pwd == p_def:
            st.session_state["ordino_auth"] = True
            st.rerun()
        else:
            st.error("Hatalı kullanıcı veya şifre.")


def _logout() -> None:
    if st.sidebar.button("Çıkış"):
        st.session_state.pop("ordino_auth", None)
        st.rerun()


def _sayfa_excel() -> None:
    st.subheader("Gemiler — gemi ve makine tipi yönetimi")
    st.caption("Gemi eklerken makine tipini de aynı anda kaydedebilirsiniz.")

    st.markdown("#### Gemi + Makine tipi birlikte ekle")
    with st.form("gemi_makine_ekle_form", clear_on_submit=True):
        gad = st.text_input("Gemi adı", key="gemi_ad_ekle")
        gkod = st.text_input("Gemi kodu (opsiyonel)", key="gemi_kod_ekle")
        mad = st.text_input("Makine tipi adı", key="makine_ad_ekle")
        kaydet = st.form_submit_button("Gemi ekle (makine tipi ile)")
    if kaydet:
        if not gad.strip() or not mad.strip():
            st.error("Gemi adı ve makine tipi adı zorunlu.")
        else:
            try:
                sql_run("INSERT INTO gemi(ad, kod) VALUES (?, ?)", (gad.strip(), gkod.strip() or None))
            except Exception:
                st.warning("Gemi zaten kayıtlı olabilir, mevcut kayıt korundu.")
            try:
                sql_run("INSERT INTO makine_tipi(ad) VALUES (?)", (mad.strip(),))
            except Exception:
                st.warning("Makine tipi zaten kayıtlı olabilir, mevcut kayıt korundu.")
            st.success("Gemi ve makine tipi kaydı işlendi.")
            st.rerun()

    st.divider()
    st.markdown("#### Kayıtlı gemiler")
    g_rows = sql_all(
        """
        SELECT g.id, g.ad, g.kod, COUNT(p.id) AS personel_sayisi
        FROM gemi g
        LEFT JOIN personel p ON p.gemi_id = g.id
        GROUP BY g.id, g.ad, g.kod
        ORDER BY g.ad
        """
    )
    st.dataframe(pd.DataFrame([dict(r) for r in g_rows]), use_container_width=True)
    gid_sil = st.number_input("Silinecek gemi ID", min_value=1, step=1, key="gid_sil")
    if st.button("Gemiyi sil", type="secondary", key="btn_gemi_sil"):
        bagli = sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id = ?", (int(gid_sil),))
        if bagli and int(bagli["c"]) > 0:
            st.error("Bu gemiye bağlı personel var. Önce personeli güncelleyin/silin.")
        else:
            sql_run("DELETE FROM gemi WHERE id = ?", (int(gid_sil),))
            st.success("Gemi silindi.")
            st.rerun()

    st.divider()
    st.markdown("#### Kayıtlı makine tipleri")
    m_rows = sql_all(
        """
        SELECT m.id, m.ad, COUNT(p.id) AS personel_sayisi
        FROM makine_tipi m
        LEFT JOIN personel p ON p.makine_tipi_id = m.id
        GROUP BY m.id, m.ad
        ORDER BY m.ad
        """
    )
    st.dataframe(pd.DataFrame([dict(r) for r in m_rows]), use_container_width=True)
    mid_sil = st.number_input("Silinecek makine tipi ID", min_value=1, step=1, key="mid_sil")
    if st.button("Makine tipini sil", type="secondary", key="btn_makine_sil"):
        bagli = sql_one("SELECT COUNT(*) AS c FROM personel WHERE makine_tipi_id = ?", (int(mid_sil),))
        if bagli and int(bagli["c"]) > 0:
            st.error("Bu makine tipine bağlı personel var. Önce personeli güncelleyin/silin.")
        else:
            sql_run("DELETE FROM makine_tipi WHERE id = ?", (int(mid_sil),))
            st.success("Makine tipi silindi.")
            st.rerun()


def _sayfa_personel() -> None:
    st.subheader("Personel")
    rows = sql_all(
        """
        SELECT p.id, p.ad, p.soyad, g.ad AS gemi, m.ad AS makine, p.vardiya_tipi, p.vardiya_gunleri,
               p.gemiden_cekilme, p.carkci_ile_sorun, p.gemi_tutumu, p.izin_tercih_gunleri,
               p.izin_saat_araligi, p.is_kalitesi, p.performans_notu
        FROM personel p
        LEFT JOIN gemi g ON g.id = p.gemi_id
        LEFT JOIN makine_tipi m ON m.id = p.makine_tipi_id
        ORDER BY p.id DESC
        """
    )
    satirlar = [dict(r) for r in rows]
    for s in satirlar:
        s["vardiya_gunleri"] = _json_gunleri_metne(s.get("vardiya_gunleri"))
        s["izin_tercih_gunleri"] = _json_gunleri_metne(s.get("izin_tercih_gunleri"))
    st.dataframe(pd.DataFrame(satirlar), use_container_width=True)

    gemiler = sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id, ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler:
        st.warning("Önce Tanımlar sekmesinden en az bir gemi ve makine tipi ekleyin.")
        return

    with st.expander("Yeni personel"):
        c1, c2 = st.columns(2)
        ad = c1.text_input("Ad", key="p_ad")
        soyad = c2.text_input("Soyad", key="p_soyad")
        gid = st.selectbox("Gemi", options=[r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i), key="p_gemi")
        mid = st.selectbox("Makine tipi", options=[r["id"] for r in makineler], format_func=lambda i: next(r["ad"] for r in makineler if r["id"] == i), key="p_makine")
        vt = st.selectbox("Vardiya tipi", ["SABIT", "GRUPCU", "8_5"], key="p_vt")
        secilen = st.multiselect("Vardiya günleri (8/5 için boş bırakılabilir)", GUNLER_TR, default=["Pazartesi", "Çarşamba", "Cuma"], key="p_vg")
        gun_json = json.dumps([GUNLER_TR.index(x) for x in secilen]) if secilen else "[]"
        st.markdown("##### Personel profil detayları")
        gemi_tutumu = st.selectbox("Gemi içi tutum", ["Mükemmel", "İyi", "Orta", "Gelişmeli"], key="p_tutum")
        izin_gunleri = st.multiselect("Tercih edilen izin günleri", GUNLER_TR, key="p_izin_gun")
        izin_gun_json = json.dumps([GUNLER_TR.index(x) for x in izin_gunleri]) if izin_gunleri else "[]"
        c3, c4 = st.columns(2)
        izin_bas = c3.time_input("Tercih edilen izin başlangıç saati", key="p_izin_bas")
        izin_bit = c4.time_input("Tercih edilen izin bitiş saati", key="p_izin_bit")
        is_kalitesi = st.slider("İş kalitesi puanı", min_value=1, max_value=5, value=4, key="p_iskalite")
        performans_notu = st.text_area("Performans notu", placeholder="Örn: Acil durumlarda hızlı reaksiyon, ekip uyumu yüksek.", key="p_not")
        if st.button("Personel kaydet", key="btn_personel_kaydet"):
            if not ad or not soyad:
                st.error("Ad ve soyad zorunlu.")
            else:
                sql_run(
                    """INSERT INTO personel(
                           ad, soyad, gemi_id, makine_tipi_id, vardiya_tipi, vardiya_gunleri,
                           gemi_tutumu, izin_tercih_gunleri, izin_saat_araligi, is_kalitesi, performans_notu
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ad,
                        soyad,
                        int(gid),
                        int(mid),
                        vt,
                        gun_json,
                        gemi_tutumu,
                        izin_gun_json,
                        f"{izin_bas.strftime('%H:%M')} - {izin_bit.strftime('%H:%M')}",
                        int(is_kalitesi),
                        performans_notu.strip() or None,
                    ),
                )
                st.success("Kaydedildi.")
                st.rerun()

    with st.expander("Personel düzenle / sil"):
        pmap = _personel_label_map(sql_all("SELECT id, ad, soyad FROM personel ORDER BY ad, soyad"))
        if not pmap:
            st.info("Düzenleme için personel yok.")
            return
        secim = st.selectbox("Personel seç", list(pmap.keys()), key="p_duzenle_secim")
        pid = pmap[secim]
        gemiden_cekildi = st.selectbox("Gemiden çekildi mi?", ["Hayır", "Evet"], key="p_cekildi")
        carkci_sorun = st.selectbox("Çarkçı sorunu var mı?", ["Hayır", "Evet"], key="p_carkci_sorun")
        sorun_notu = ""
        if carkci_sorun == "Evet":
            sorun_notu = st.text_area("Çarkçı sorunu detayı", key="p_carkci_sorun_notu")
        c1, c2 = st.columns(2)
        if c1.button("Personel bilgisini güncelle", key="btn_personel_guncelle"):
            sql_run(
                """
                UPDATE personel
                SET gemiden_cekilme = ?, carkci_ile_sorun = ?, carkci_sorun_notu = ?
                WHERE id = ?
                """,
                (
                    1 if gemiden_cekildi == "Evet" else 0,
                    1 if carkci_sorun == "Evet" else 0,
                    sorun_notu.strip() if carkci_sorun == "Evet" and sorun_notu.strip() else None,
                    int(pid),
                ),
            )
            st.success("Personel bilgileri güncellendi.")
            st.rerun()
        if c2.button("Personeli sil", type="secondary", key="btn_personel_sil"):
            sql_run("DELETE FROM personel WHERE id = ?", (int(pid),))
            st.success("Personel silindi.")
            st.rerun()


def _sayfa_izin() -> None:
    st.subheader("İzin takibi")
    plist = sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not plist:
        st.info("Önce personel ekleyin.")
        return
    pid = st.selectbox("Personel", [r["id"] for r in plist], format_func=lambda i: f"{next(r['ad'] for r in plist if r['id']==i)} {next(r['soyad'] for r in plist if r['id']==i)}", key="izin_pid")
    c1, c2 = st.columns(2)
    bas = c1.date_input("Başlangıç", value=date.today(), key="izin_bas")
    bit = c2.date_input("Bitiş", value=date.today(), key="izin_bit")
    gun = gun_sayisi(bas, bit)
    st.write(f"Hesaplanan gün sayısı: **{gun}**")
    ucb = st.checkbox("Pazartesi vardiya günü izni → 3 gün (Pzt–Sal–Çar) uygula", key="izin_ucb")
    if ucb and bas.weekday() == 0:
        bas, bit = izin_pzt_3gun(bas)
        st.info(f"Tarihler güncellendi: {bas} → {bit}")
        gun = gun_sayisi(bas, bit)
    notlar = st.text_input("Not (isteğe bağlı)", key="izin_not")
    if st.button("İzin kaydet", key="btn_izin_kaydet"):
        sql_run(
            "INSERT INTO izin(personel_id, baslangic, bitis, gun_sayisi, notlar) VALUES (?,?,?,?,?)",
            (int(pid), bas.isoformat(), bit.isoformat(), int(gun), notlar or None),
        )
        st.success("İzin kaydedildi.")
        st.rerun()
    st.divider()
    st.write("Kayıtlı izinler")
    iz = sql_all(
        """SELECT i.id, p.ad, p.soyad, i.baslangic, i.bitis, i.gun_sayisi, i.notlar
           FROM izin i JOIN personel p ON p.id = i.personel_id ORDER BY i.baslangic DESC LIMIT 50"""
    )
    st.dataframe(pd.DataFrame([dict(r) for r in iz]), use_container_width=True)


def _sayfa_carkci() -> None:
    st.subheader("Çarkçı kayıtları")
    gemiler = sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    yagcilar = sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not gemiler or not yagcilar:
        st.warning("Gemi ve personel gerekli.")
        return
    ad = st.text_input("Çarkçı adı", key="carkci_ad")
    soyad = st.text_input("Çarkçı soyadı", key="carkci_soyad")
    gid = st.selectbox("Gemi", [r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i), key="carkci_gemi")
    carkci_vardiya = st.selectbox("Çarkçının vardiyası", ["SABIT", "GRUPCU", "8_5"], key="carkci_vardiya")
    yid = st.selectbox("Sorunlu yağcı (personel)", [r["id"] for r in yagcilar], format_func=lambda i: f"{next(r['ad'] for r in yagcilar if r['id']==i)} {next(r['soyad'] for r in yagcilar if r['id']==i)}", key="carkci_yagci")
    sorun = st.text_area("Sorun / açıklama", key="carkci_sorun")
    vn = st.text_input("Çarkçı vardiya notu", key="carkci_not")
    if st.button("Çarkçı kaydı oluştur ve yağcıyı öneri dışı bırak", key="btn_carkci_kaydet"):
        sql_run(
            """INSERT INTO carkci(ad, soyad, gemi_id, problemli_yagci_id, sorun_metni, vardiya_notu, carkci_vardiya)
               VALUES (?,?,?,?,?,?,?)""",
            (ad, soyad, int(gid), int(yid), sorun, vn, carkci_vardiya),
        )
        sql_run("UPDATE personel SET carkci_ile_sorun = 1, carkci_sorun_notu = ? WHERE id = ?", (sorun.strip() or None, int(yid)))
        st.success("Kaydedildi; yağcı öneri motorunda elendi.")
        st.rerun()
    st.divider()
    cr = sql_all(
        """SELECT c.id, c.ad, c.soyad, g.ad AS gemi, c.carkci_vardiya, p.ad || ' ' || p.soyad AS yagci, c.sorun_metni
           FROM carkci c
           LEFT JOIN gemi g ON g.id = c.gemi_id
           LEFT JOIN personel p ON p.id = c.problemli_yagci_id
           ORDER BY c.id DESC LIMIT 30"""
    )
    st.dataframe(pd.DataFrame([dict(r) for r in cr]), use_container_width=True)


def _sayfa_oneri() -> None:
    st.subheader("Yağcı öneri (en fazla 5, skor 5 en iyi)")
    gemiler = sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id, ad FROM makine_tipi ORDER BY ad")
    plist = sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not gemiler or not makineler:
        st.warning("Gemi ve makine tipi gerekli.")
        return
    gid = st.selectbox("Gemi", [r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i), key="oneri_gemi")
    mid = st.selectbox("Makine tipi", [r["id"] for r in makineler], format_func=lambda i: next(r["ad"] for r in makineler if r["id"] == i), key="oneri_makine")
    ht = st.date_input("Hedef tarih", value=date.today(), key="oneri_hedef_tarih")
    cikis_gemi = st.selectbox("Çıkan yağcının gemisi", [r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i), key="oneri_cikan_gemi")
    filtreli = sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 AND gemi_id = ? ORDER BY ad", (int(cikis_gemi),))
    cik_labels = ["(Çıkan yağcı yok)"] + [f"{r['ad']} {r['soyad']}" for r in filtreli]
    cik_sel = st.selectbox("Çıkan yağcı", cik_labels, key="oneri_cikan_yagci")
    st.text_input("Çıkan yağcı serbest notu", key="oneri_cikan_not", placeholder="Opsiyonel: dış kaynaktan gelen isim/not")
    cik = None if cik_sel == "(Çıkan yağcı yok)" else next(int(r["id"]) for r in filtreli if f"{r['ad']} {r['soyad']}" == cik_sel)
    if st.button("Önerileri hesapla", key="btn_oneri_hesapla"):
        out = onerileri_hesapla(int(gid), int(mid), ht, cik, limit=5)
        rows = to_dict_rows(out)
        if not rows:
            st.warning("Uygun aday bulunamadı (kurallar veya veri eksik).")
        else:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            for r in rows:
                if r.get("uyari_8_5"):
                    st.warning(f"8/5 uyarısı: {r['ad_soyad']}")


def _sayfa_bilgi() -> None:
    st.subheader("Bilgi ve canlı durum özeti")
    toplam_personel = int((sql_one("SELECT COUNT(*) AS c FROM personel") or {"c": 0})["c"])
    toplam_gemi = int((sql_one("SELECT COUNT(*) AS c FROM gemi") or {"c": 0})["c"])
    toplam_izin_kaydi = int((sql_one("SELECT COUNT(*) AS c FROM izin") or {"c": 0})["c"])
    aktif_izinde = int(
        (
            sql_one(
                "SELECT COUNT(*) AS c FROM izin WHERE date('now') BETWEEN baslangic AND bitis"
            )
            or {"c": 0}
        )["c"]
    )
    plan_bugun = bugun_plani_olustur()
    sabit = int((sql_one("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi = 'SABIT'") or {"c": 0})["c"])
    tersane = int((sql_one("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi = '8_5'") or {"c": 0})["c"])
    st.markdown(
        f"""
- Toplam personel: **{toplam_personel}**
- Toplam gemi: **{toplam_gemi}**
- Toplam izin kaydı: **{toplam_izin_kaydi}**
- Şu an izinde olan personel: **{aktif_izinde}**
- Sabit vardiya personeli: **{sabit}**
- Tersane (8/5) personeli: **{tersane}**
        """
    )
    gemi_bazli = sql_all(
        """
        SELECT g.ad AS gemi, COUNT(p.id) AS personel_sayisi
        FROM gemi g
        LEFT JOIN personel p ON p.gemi_id = g.id
        GROUP BY g.id, g.ad
        ORDER BY g.ad
        """
    )
    st.markdown("#### Gemilerde personel dağılımı")
    st.dataframe(pd.DataFrame([dict(r) for r in gemi_bazli]), use_container_width=True)
    st.markdown("#### Bugünün gemi–makine planı (vardiya_plan)")
    if plan_bugun:
        st.dataframe(pd.DataFrame(plan_bugun), use_container_width=True)
    else:
        st.caption("Bugün için gemi_makine veya vardiya_plan kaydı yok; Yapboz sekmesinden atama yapın.")


def main() -> None:
    st.set_page_config(
        page_title="Ordino Yağcı Planlaması",
        page_icon="⚓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        .stApp {
          background-image:
            linear-gradient(rgba(22, 15, 8, 0.32), rgba(22, 15, 8, 0.32)),
            linear-gradient(160deg, rgba(255, 247, 239, 0.78) 0%, rgba(255, 224, 191, 0.72) 45%, rgba(255, 210, 161, 0.72) 100%),
            url("https://commons.wikimedia.org/wiki/Special:FilePath/Ferry_%C5%9EH-DURUSU_approaching_Yenikap%C4%B1_Ferry_Terminal,_Istanbul,_March_2024_01.jpg");
          background-size: cover;
          background-repeat: no-repeat;
          background-position: center center;
          background-attachment: fixed;
          color: #2f251b;
        }
        [data-testid="stAppViewContainer"] .main .block-container {
          background: rgba(255, 255, 255, 0.96);
          border-radius: 14px;
          padding: 1rem 1rem 1.2rem;
          border: 1px solid #ffd2a1;
          box-shadow: 0 12px 34px rgba(28, 17, 8, 0.22);
        }
        h1, h2, h3, h4, p, li, label, span, div {
          color: #2f251b !important;
        }
        [data-testid="stForm"] {
          background: #fffaf4;
          border: 1px solid #ffd8b0;
          border-radius: 12px;
          padding: 0.9rem 1rem 0.4rem;
        }
        [data-testid="stExpander"] {
          border: 1px solid #ffd8b0;
          border-radius: 12px;
          background: #fffdf9;
        }
        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        .stDateInput > div > div {
          background: #fff8f0;
          border-color: #f4bf8a !important;
          border-radius: 10px;
        }
        [data-baseweb="input"] input,
        [data-baseweb="select"] input {
          color: #2f251b !important;
        }
        html, body, [class*="css"] { font-size: 16px; }
        .stTabs [role="tablist"] {
          overflow-x: auto;
          white-space: nowrap;
          gap: 0.45rem;
          padding-bottom: 0.35rem;
        }
        .stTabs [role="tab"] {
          padding: 0.55rem 0.95rem;
          background: #fff5ea;
          border: 1px solid #ffcb97;
          border-radius: 8px;
          color: #5a320a;
          font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
          background: #f3831f !important;
          color: #ffffff !important;
          border-color: #f3831f !important;
          box-shadow: 0 4px 12px rgba(243, 131, 31, 0.35);
        }
        .stButton button {
          width: 100%;
          min-height: 44px;
          background: #f3831f;
          color: #ffffff;
          border: 1px solid #d66d12;
          border-radius: 10px;
          font-weight: 600;
          transition: all 0.15s ease-in-out;
        }
        .stButton button:hover {
          background: #d96f14;
          border-color: #bf5f10;
          color: #ffffff;
          transform: translateY(-1px);
        }
        .stDataFrame, .stTable {
          background: #ffffff;
          border-radius: 10px;
          border: 1px solid #f7d7b4;
        }
        [data-testid="stSidebar"] {
          background: linear-gradient(180deg, #fff3e3 0%, #ffe7cc 100%);
          border-left: 1px solid #ffd1a0;
        }
        .stAlert {
          border-radius: 10px;
        }
        @media (max-width: 768px) {
          .block-container { padding: 0.8rem 0.7rem 1.2rem; }
          .stDataFrame { font-size: 13px; }
          h1, h2, h3 { line-height: 1.2; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    init_db()
    if "ayarlar" not in st.session_state:
        st.session_state.ayarlar = dict(DEFAULT_AYARLAR)
    if not st.session_state.get("ordino_auth"):
        _login_form()
        return
    _logout()
    st.sidebar.caption("Şifreyi değiştirmek için yerelde `.env` veya Streamlit Cloud’da Secrets içinde `ORDINO_ADMIN_PASSWORD` düzenleyin.")
    with st.sidebar.expander("Planlama ayarları (v8 motor)", expanded=False):
        ay = st.session_state.ayarlar
        md = st.number_input("Min. dinlenme (saat)", min_value=4, max_value=24, value=int(ay.get("min_dinlenme_suresi_saat", 11)), key="ay_md")
        mh = st.number_input("Max haftalık saat", min_value=20, max_value=80, value=int(ay.get("max_haftalik_saat", 45)), key="ay_mh")
        if st.button("Ayarları kaydet", key="ay_kaydet"):
            st.session_state.ayarlar = {"min_dinlenme_suresi_saat": md, "max_haftalik_saat": mh, "yillik_izin_hakki": int(ay.get("yillik_izin_hakki", 14))}
            st.success("Güncellendi.")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        ["Gemiler", "Personel", "İzin", "Çarkçı", "Öneri", "Yapboz (v8)", "Bilgi"]
    )
    with tab1:
        _sayfa_excel()
    with tab2:
        _sayfa_personel()
    with tab3:
        _sayfa_izin()
    with tab4:
        _sayfa_carkci()
    with tab5:
        _sayfa_oneri()
    with tab6:
        render_yapboz()
    with tab7:
        _sayfa_bilgi()


if __name__ == "__main__":
    main()
