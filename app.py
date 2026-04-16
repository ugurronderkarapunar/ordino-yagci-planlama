"""
Ordino Yağcı Planlaması — Streamlit web uygulaması.
Çalıştır: proje kökünde `streamlit run app.py`
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src import database as db
from src.config import get_admin_credentials
from src.oneri_motoru import to_dict_rows, onerileri_hesapla
from src.vardiya_kurallari import gun_sayisi, izin_pzt_3gun

GUNLER_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# Vardiya tipleri — İZİNCİ eklendi
VARDIYA_TIPLERI = ["SABIT", "GRUPCU", "IZINCI", "8_5"]


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


# ── Çoklu makine ID listesini JSON olarak sakla/oku ──────────────────────────
def _makine_id_json(id_list: list[int]) -> str:
    return json.dumps(id_list)


def _makine_id_listesi(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
        # Geriye dönük uyum: eski kayıtlarda tek integer olabilir
        return [int(parsed)]
    except Exception:
        return []


# ── Çoklu gemi ID listesini JSON olarak sakla/oku ────────────────────────────
def _gemi_id_json(id_list: list[int]) -> str:
    return json.dumps(id_list)


def _gemi_id_listesi(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
        return [int(parsed)]
    except Exception:
        return []


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


# ── GEMİLER SAYFASI ──────────────────────────────────────────────────────────
def _sayfa_excel() -> None:
    st.subheader("Gemiler — gemi ve makine tipi yönetimi")
    st.caption("Gemi eklerken makine tipini de aynı anda kaydedebilirsiniz.")

    # ── Yeni gemi + makine tipi ──────────────────────────────────────────────
    st.markdown("#### Gemi + Makine tipi birlikte ekle")
    with st.form("gemi_makine_ekle_form", clear_on_submit=True):
        gad  = st.text_input("Gemi adı", key="gemi_ad_ekle")
        gkod = st.text_input("Gemi kodu (opsiyonel)", key="gemi_kod_ekle")
        mad  = st.text_input("Makine tipi adı", key="makine_ad_ekle")
        kaydet = st.form_submit_button("Gemi ekle (makine tipi ile)")
    if kaydet:
        if not gad.strip() or not mad.strip():
            st.error("Gemi adı ve makine tipi adı zorunlu.")
        else:
            try:
                db.sql_run("INSERT INTO gemi(ad, kod) VALUES (?, ?)", (gad.strip(), gkod.strip() or None))
            except Exception:
                st.warning("Gemi zaten kayıtlı olabilir, mevcut kayıt korundu.")
            try:
                db.sql_run("INSERT INTO makine_tipi(ad) VALUES (?)", (mad.strip(),))
            except Exception:
                st.warning("Makine tipi zaten kayıtlı olabilir, mevcut kayıt korundu.")
            st.success("Gemi ve makine tipi kaydı işlendi.")
            st.rerun()

    st.divider()

    # ── Kayıtlı gemiler ──────────────────────────────────────────────────────
    st.markdown("#### Kayıtlı gemiler")
    g_rows = db.sql_all(
        """
        SELECT g.id, g.ad, g.kod, COUNT(p.id) AS personel_sayisi
        FROM gemi g
        LEFT JOIN personel p ON p.gemi_id = g.id
        GROUP BY g.id, g.ad, g.kod
        ORDER BY g.ad
        """
    )
    st.dataframe(pd.DataFrame([dict(r) for r in g_rows]), use_container_width=True)

    # ── Gemi düzenle ────────────────────────────────────────────────────────
    with st.expander("✏️ Gemi düzenle"):
        if not g_rows:
            st.info("Düzenlenecek gemi yok.")
        else:
            g_map = {f"{r['ad']} (ID:{r['id']})": r for r in g_rows}
            g_secim = st.selectbox("Düzenlenecek gemi", list(g_map.keys()), key="gemi_duzenle_secim")
            g_sec = g_map[g_secim]
            yeni_gad  = st.text_input("Yeni gemi adı",  value=g_sec["ad"]  or "", key="gemi_yeni_ad")
            yeni_gkod = st.text_input("Yeni gemi kodu", value=g_sec["kod"] or "", key="gemi_yeni_kod")
            if st.button("Gemi adını/kodunu güncelle", key="btn_gemi_guncelle"):
                if not yeni_gad.strip():
                    st.error("Gemi adı boş olamaz.")
                else:
                    db.sql_run(
                        "UPDATE gemi SET ad = ?, kod = ? WHERE id = ?",
                        (yeni_gad.strip(), yeni_gkod.strip() or None, int(g_sec["id"])),
                    )
                    st.success("Gemi güncellendi.")
                    st.rerun()

    # ── Gemi sil ────────────────────────────────────────────────────────────
    gid_sil = st.number_input("Silinecek gemi ID", min_value=1, step=1, key="gid_sil")
    if st.button("Gemiyi sil", type="secondary", key="btn_gemi_sil"):
        bagli = db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id = ?", (int(gid_sil),))
        if bagli and int(bagli["c"]) > 0:
            st.error("Bu gemiye bağlı personel var. Önce personeli güncelleyin/silin.")
        else:
            db.sql_run("DELETE FROM gemi WHERE id = ?", (int(gid_sil),))
            st.success("Gemi silindi.")
            st.rerun()

    st.divider()

    # ── Kayıtlı makine tipleri ───────────────────────────────────────────────
    st.markdown("#### Kayıtlı makine tipleri")
    m_rows = db.sql_all(
        """
        SELECT m.id, m.ad, COUNT(p.id) AS personel_sayisi
        FROM makine_tipi m
        LEFT JOIN personel p ON p.makine_tipi_id = m.id
        GROUP BY m.id, m.ad
        ORDER BY m.ad
        """
    )
    st.dataframe(pd.DataFrame([dict(r) for r in m_rows]), use_container_width=True)

    # ── Makine tipi düzenle ──────────────────────────────────────────────────
    with st.expander("✏️ Makine tipi düzenle"):
        if not m_rows:
            st.info("Düzenlenecek makine tipi yok.")
        else:
            m_map = {f"{r['ad']} (ID:{r['id']})": r for r in m_rows}
            m_secim = st.selectbox("Düzenlenecek makine tipi", list(m_map.keys()), key="makine_duzenle_secim")
            m_sec = m_map[m_secim]
            yeni_mad = st.text_input("Yeni makine tipi adı", value=m_sec["ad"] or "", key="makine_yeni_ad")
            if st.button("Makine tipi adını güncelle", key="btn_makine_guncelle"):
                if not yeni_mad.strip():
                    st.error("Makine tipi adı boş olamaz.")
                else:
                    db.sql_run(
                        "UPDATE makine_tipi SET ad = ? WHERE id = ?",
                        (yeni_mad.strip(), int(m_sec["id"])),
                    )
                    st.success("Makine tipi güncellendi.")
                    st.rerun()

    # ── Makine tipi sil ──────────────────────────────────────────────────────
    mid_sil = st.number_input("Silinecek makine tipi ID", min_value=1, step=1, key="mid_sil")
    if st.button("Makine tipini sil", type="secondary", key="btn_makine_sil"):
        bagli = db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE makine_tipi_id = ?", (int(mid_sil),))
        if bagli and int(bagli["c"]) > 0:
            st.error("Bu makine tipine bağlı personel var. Önce personeli güncelleyin/silin.")
        else:
            db.sql_run("DELETE FROM makine_tipi WHERE id = ?", (int(mid_sil),))
            st.success("Makine tipi silindi.")
            st.rerun()


# ── PERSONEL SAYFASI ─────────────────────────────────────────────────────────
def _sayfa_personel() -> None:
    st.subheader("Personel")

    rows = db.sql_all(
        """
        SELECT p.id, p.ad, p.soyad, g.ad AS gemi, p.gemi_id_list,
               p.makine_tipi_id_list, p.vardiya_tipi, p.vardiya_gunleri,
               p.gemiden_cekilme, p.carkci_ile_sorun, p.gemi_tutumu,
               p.izin_tercih_gunleri, p.izin_saat_araligi,
               p.is_kalitesi, p.performans_notu
        FROM personel p
        LEFT JOIN gemi g ON g.id = p.gemi_id
        ORDER BY p.id DESC
        """
    )

    # Makine ve gemi id listelerini okunabilir isme çevir
    tum_makineler = {r["id"]: r["ad"] for r in db.sql_all("SELECT id, ad FROM makine_tipi")}
    tum_gemiler   = {r["id"]: r["ad"] for r in db.sql_all("SELECT id, ad FROM gemi")}

    satirlar = []
    for s in [dict(r) for r in rows]:
        s["vardiya_gunleri"]    = _json_gunleri_metne(s.get("vardiya_gunleri"))
        s["izin_tercih_gunleri"]= _json_gunleri_metne(s.get("izin_tercih_gunleri"))

        mids = _makine_id_listesi(s.get("makine_tipi_id_list"))
        s["makine_tipleri"] = ", ".join(tum_makineler.get(mid, str(mid)) for mid in mids) if mids else s.get("gemi", "-")

        gids = _gemi_id_listesi(s.get("gemi_id_list"))
        s["gemiler"] = ", ".join(tum_gemiler.get(gid, str(gid)) for gid in gids) if gids else (s.get("gemi") or "-")

        satirlar.append(s)

    st.dataframe(pd.DataFrame(satirlar), use_container_width=True)

    gemiler   = db.sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    makineler = db.sql_all("SELECT id, ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler:
        st.warning("Önce Tanımlar sekmesinden en az bir gemi ve makine tipi ekleyin.")
        return

    # ── Yeni personel ────────────────────────────────────────────────────────
    with st.expander("Yeni personel"):
        c1, c2 = st.columns(2)
        ad    = c1.text_input("Ad",    key="p_ad")
        soyad = c2.text_input("Soyad", key="p_soyad")

        vt = st.selectbox("Vardiya tipi", VARDIYA_TIPLERI, key="p_vt")

        # Çoklu makine seçimi
        makine_secim = st.multiselect(
            "Bildiği makine tipleri (birden fazla seçilebilir)",
            options=[r["id"] for r in makineler],
            format_func=lambda i: next(r["ad"] for r in makineler if r["id"] == i),
            key="p_makine_list",
        )

        # Gemi seçimi: grupcu veya izinci → çoklu; diğerleri → tekli
        if vt in ("GRUPCU", "IZINCI"):
            gemi_secim_list = st.multiselect(
                "Atandığı gemiler (birden fazla seçilebilir)",
                options=[r["id"] for r in gemiler],
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i),
                key="p_gemi_list",
            )
            gemi_id_tek = int(gemi_secim_list[0]) if gemi_secim_list else None
        else:
            gemi_secim_tek = st.selectbox(
                "Gemi",
                options=[r["id"] for r in gemiler],
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i),
                key="p_gemi_tek",
            )
            gemi_secim_list = [int(gemi_secim_tek)]
            gemi_id_tek = int(gemi_secim_tek)

        secilen = st.multiselect(
            "Vardiya günleri (8/5 için boş bırakılabilir)",
            GUNLER_TR,
            default=["Pazartesi", "Çarşamba", "Cuma"],
            key="p_vg",
        )
        gun_json = json.dumps([GUNLER_TR.index(x) for x in secilen]) if secilen else "[]"

        st.markdown("##### Personel profil detayları")
        gemi_tutumu   = st.selectbox("Gemi içi tutum", ["Mükemmel", "İyi", "Orta", "Gelişmeli"], key="p_tutum")
        izin_gunleri  = st.multiselect("Tercih edilen izin günleri", GUNLER_TR, key="p_izin_gun")
        izin_gun_json = json.dumps([GUNLER_TR.index(x) for x in izin_gunleri]) if izin_gunleri else "[]"
        c3, c4 = st.columns(2)
        izin_bas = c3.time_input("Tercih edilen izin başlangıç saati", key="p_izin_bas")
        izin_bit = c4.time_input("Tercih edilen izin bitiş saati",     key="p_izin_bit")
        is_kalitesi    = st.slider("İş kalitesi puanı", min_value=1, max_value=5, value=4, key="p_iskalite")
        performans_notu= st.text_area("Performans notu", placeholder="Örn: Acil durumlarda hızlı reaksiyon.", key="p_not")

        if st.button("Personel kaydet", key="btn_personel_kaydet"):
            if not ad or not soyad:
                st.error("Ad ve soyad zorunlu.")
            elif not makine_secim:
                st.error("En az bir makine tipi seçin.")
            else:
                # Geriye dönük uyum için ilk makine ID'sini makine_tipi_id alanına da yaz
                ilk_makine = int(makine_secim[0])
                db.sql_run(
                    """INSERT INTO personel(
                           ad, soyad, gemi_id, gemi_id_list,
                           makine_tipi_id, makine_tipi_id_list,
                           vardiya_tipi, vardiya_gunleri,
                           gemi_tutumu, izin_tercih_gunleri, izin_saat_araligi,
                           is_kalitesi, performans_notu
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ad,
                        soyad,
                        gemi_id_tek,
                        _gemi_id_json([int(x) for x in gemi_secim_list]),
                        ilk_makine,
                        _makine_id_json([int(x) for x in makine_secim]),
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

    # ── Personel düzenle / sil ───────────────────────────────────────────────
    with st.expander("Personel düzenle / sil"):
        pmap = _personel_label_map(db.sql_all("SELECT id, ad, soyad FROM personel ORDER BY ad, soyad"))
        if not pmap:
            st.info("Düzenleme için personel yok.")
            return
        secim = st.selectbox("Personel seç", list(pmap.keys()), key="p_duzenle_secim")
        pid   = pmap[secim]

        # Mevcut kaydı çek
        mevcut = db.sql_one(
            "SELECT * FROM personel WHERE id = ?", (int(pid),)
        )
        if mevcut:
            mevcut = dict(mevcut)
        else:
            mevcut = {}

        st.markdown("**Vardiya / Makine / Gemi güncelle**")

        yeni_vt = st.selectbox(
            "Vardiya tipi",
            VARDIYA_TIPLERI,
            index=VARDIYA_TIPLERI.index(mevcut.get("vardiya_tipi", "SABIT"))
            if mevcut.get("vardiya_tipi") in VARDIYA_TIPLERI else 0,
            key="p_duzenle_vt",
        )

        mevcut_makine_ids = _makine_id_listesi(mevcut.get("makine_tipi_id_list"))
        if not mevcut_makine_ids and mevcut.get("makine_tipi_id"):
            mevcut_makine_ids = [int(mevcut["makine_tipi_id"])]

        yeni_makine_secim = st.multiselect(
            "Bildiği makine tipleri",
            options=[r["id"] for r in makineler],
            default=[m for m in mevcut_makine_ids if m in [r["id"] for r in makineler]],
            format_func=lambda i: next(r["ad"] for r in makineler if r["id"] == i),
            key="p_duzenle_makine_list",
        )

        mevcut_gemi_ids = _gemi_id_listesi(mevcut.get("gemi_id_list"))
        if not mevcut_gemi_ids and mevcut.get("gemi_id"):
            mevcut_gemi_ids = [int(mevcut["gemi_id"])]

        if yeni_vt in ("GRUPCU", "IZINCI"):
            yeni_gemi_list = st.multiselect(
                "Atandığı gemiler",
                options=[r["id"] for r in gemiler],
                default=[g for g in mevcut_gemi_ids if g in [r["id"] for r in gemiler]],
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i),
                key="p_duzenle_gemi_list",
            )
            yeni_gemi_tek = int(yeni_gemi_list[0]) if yeni_gemi_list else None
        else:
            g_opts = [r["id"] for r in gemiler]
            def_idx = g_opts.index(mevcut_gemi_ids[0]) if mevcut_gemi_ids and mevcut_gemi_ids[0] in g_opts else 0
            yeni_gemi_tek_sel = st.selectbox(
                "Gemi",
                options=g_opts,
                index=def_idx,
                format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i),
                key="p_duzenle_gemi_tek",
            )
            yeni_gemi_list = [int(yeni_gemi_tek_sel)]
            yeni_gemi_tek  = int(yeni_gemi_tek_sel)

        st.markdown("**Durum güncelle**")
        gemiden_cekildi = st.selectbox("Gemiden çekildi mi?", ["Hayır", "Evet"], key="p_cekildi")
        carkci_sorun    = st.selectbox("Çarkçı sorunu var mı?", ["Hayır", "Evet"], key="p_carkci_sorun")
        sorun_notu = ""
        if carkci_sorun == "Evet":
            sorun_notu = st.text_area("Çarkçı sorunu detayı", key="p_carkci_sorun_notu")

        c1, c2 = st.columns(2)
        if c1.button("Personel bilgisini güncelle", key="btn_personel_guncelle"):
            if not yeni_makine_secim:
                st.error("En az bir makine tipi seçin.")
            else:
                ilk_makine = int(yeni_makine_secim[0])
                db.sql_run(
                    """
                    UPDATE personel
                    SET vardiya_tipi      = ?,
                        gemi_id           = ?,
                        gemi_id_list      = ?,
                        makine_tipi_id    = ?,
                        makine_tipi_id_list = ?,
                        gemiden_cekilme   = ?,
                        carkci_ile_sorun  = ?,
                        carkci_sorun_notu = ?
                    WHERE id = ?
                    """,
                    (
                        yeni_vt,
                        yeni_gemi_tek,
                        _gemi_id_json([int(x) for x in yeni_gemi_list]),
                        ilk_makine,
                        _makine_id_json([int(x) for x in yeni_makine_secim]),
                        1 if gemiden_cekildi == "Evet" else 0,
                        1 if carkci_sorun    == "Evet" else 0,
                        sorun_notu.strip() if carkci_sorun == "Evet" and sorun_notu.strip() else None,
                        int(pid),
                    ),
                )
                st.success("Personel bilgileri güncellendi.")
                st.rerun()

        if c2.button("Personeli sil", type="secondary", key="btn_personel_sil"):
            db.sql_run("DELETE FROM personel WHERE id = ?", (int(pid),))
            st.success("Personel silindi.")
            st.rerun()


# ── İZİN SAYFASI ─────────────────────────────────────────────────────────────
def _sayfa_izin() -> None:
    st.subheader("İzin takibi")
    plist = db.sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not plist:
        st.info("Önce personel ekleyin.")
        return
    pid = st.selectbox(
        "Personel",
        [r["id"] for r in plist],
        format_func=lambda i: f"{next(r['ad'] for r in plist if r['id']==i)} {next(r['soyad'] for r in plist if r['id']==i)}",
        key="izin_pid",
    )
    c1, c2 = st.columns(2)
    bas = c1.date_input("Başlangıç", value=date.today(), key="izin_bas")
    bit = c2.date_input("Bitiş",     value=date.today(), key="izin_bit")
    gun = gun_sayisi(bas, bit)
    st.write(f"Hesaplanan gün sayısı: **{gun}**")
    ucb = st.checkbox("Pazartesi vardiya günü izni → 3 gün (Pzt–Sal–Çar) uygula", key="izin_ucb")
    if ucb and bas.weekday() == 0:
        bas, bit = izin_pzt_3gun(bas)
        st.info(f"Tarihler güncellendi: {bas} → {bit}")
        gun = gun_sayisi(bas, bit)
    notlar = st.text_input("Not (isteğe bağlı)", key="izin_not")
    if st.button("İzin kaydet", key="btn_izin_kaydet"):
        db.sql_run(
            "INSERT INTO izin(personel_id, baslangic, bitis, gun_sayisi, notlar) VALUES (?,?,?,?,?)",
            (int(pid), bas.isoformat(), bit.isoformat(), int(gun), notlar or None),
        )
        st.success("İzin kaydedildi.")
        st.rerun()
    st.divider()
    st.write("Kayıtlı izinler")
    iz = db.sql_all(
        """SELECT i.id, p.ad, p.soyad, i.baslangic, i.bitis, i.gun_sayisi, i.notlar
           FROM izin i JOIN personel p ON p.id = i.personel_id ORDER BY i.baslangic DESC LIMIT 50"""
    )
    st.dataframe(pd.DataFrame([dict(r) for r in iz]), use_container_width=True)


# ── ÇARKÇI SAYFASI ───────────────────────────────────────────────────────────
def _sayfa_carkci() -> None:
    st.subheader("Çarkçı kayıtları")
    gemiler = db.sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    yagcilar = db.sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not gemiler or not yagcilar:
        st.warning("Gemi ve personel gerekli.")
        return
    ad   = st.text_input("Çarkçı adı",   key="carkci_ad")
    soyad= st.text_input("Çarkçı soyadı",key="carkci_soyad")
    gid  = st.selectbox("Gemi", [r["id"] for r in gemiler],  format_func=lambda i: next(r["ad"] for r in gemiler  if r["id"] == i), key="carkci_gemi")
    carkci_vardiya = st.selectbox("Çarkçının vardiyası", VARDIYA_TIPLERI, key="carkci_vardiya")
    yid  = st.selectbox(
        "Sorunlu yağcı (personel)",
        [r["id"] for r in yagcilar],
        format_func=lambda i: f"{next(r['ad'] for r in yagcilar if r['id']==i)} {next(r['soyad'] for r in yagcilar if r['id']==i)}",
        key="carkci_yagci",
    )
    sorun = st.text_area("Sorun / açıklama", key="carkci_sorun")
    vn    = st.text_input("Çarkçı vardiya notu", key="carkci_not")
    if st.button("Çarkçı kaydı oluştur ve yağcıyı öneri dışı bırak", key="btn_carkci_kaydet"):
        db.sql_run(
            """INSERT INTO carkci(ad, soyad, gemi_id, problemli_yagci_id, sorun_metni, vardiya_notu, carkci_vardiya)
               VALUES (?,?,?,?,?,?,?)""",
            (ad, soyad, int(gid), int(yid), sorun, vn, carkci_vardiya),
        )
        db.sql_run("UPDATE personel SET carkci_ile_sorun = 1, carkci_sorun_notu = ? WHERE id = ?", (sorun.strip() or None, int(yid)))
        st.success("Kaydedildi; yağcı öneri motorunda elendi.")
        st.rerun()
    st.divider()
    cr = db.sql_all(
        """SELECT c.id, c.ad, c.soyad, g.ad AS gemi, c.carkci_vardiya, p.ad || ' ' || p.soyad AS yagci, c.sorun_metni
           FROM carkci c
           LEFT JOIN gemi g ON g.id = c.gemi_id
           LEFT JOIN personel p ON p.id = c.problemli_yagci_id
           ORDER BY c.id DESC LIMIT 30"""
    )
    st.dataframe(pd.DataFrame([dict(r) for r in cr]), use_container_width=True)


# ── ÖNERİ SAYFASI ────────────────────────────────────────────────────────────
def _sayfa_oneri() -> None:
    st.subheader("Yağcı öneri (en fazla 5, skor 5 en iyi)")
    gemiler   = db.sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    makineler = db.sql_all("SELECT id, ad FROM makine_tipi ORDER BY ad")
    plist     = db.sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not gemiler or not makineler:
        st.warning("Gemi ve makine tipi gerekli.")
        return
    gid = st.selectbox("Gemi",        [r["id"] for r in gemiler],   format_func=lambda i: next(r["ad"] for r in gemiler   if r["id"] == i), key="oneri_gemi")
    mid = st.selectbox("Makine tipi", [r["id"] for r in makineler], format_func=lambda i: next(r["ad"] for r in makineler if r["id"] == i), key="oneri_makine")
    ht  = st.date_input("Hedef tarih", value=date.today(), key="oneri_hedef_tarih")
    cikis_gemi = st.selectbox(
        "Çıkan yağcının gemisi",
        [r["id"] for r in gemiler],
        format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i),
        key="oneri_cikan_gemi",
    )
    filtreli = db.sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 AND gemi_id = ? ORDER BY ad", (int(cikis_gemi),))
    cik_labels = ["(Çıkan yağcı yok)"] + [f"{r['ad']} {r['soyad']}" for r in filtreli]
    cik_sel    = st.selectbox("Çıkan yağcı", cik_labels, key="oneri_cikan_yagci")
    st.text_input("Çıkan yağcı serbest notu", key="oneri_cikan_not", placeholder="Opsiyonel: dış kaynaktan gelen isim/not")
    cik = None if cik_sel == "(Çıkan yağcı yok)" else next(int(r["id"]) for r in filtreli if f"{r['ad']} {r['soyad']}" == cik_sel)
    if st.button("Önerileri hesapla", key="btn_oneri_hesapla"):
        out  = onerileri_hesapla(int(gid), int(mid), ht, cik, limit=5)
        rows = to_dict_rows(out)
        if not rows:
            st.warning("Uygun aday bulunamadı (kurallar veya veri eksik).")
        else:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            for r in rows:
                if r.get("uyari_8_5"):
                    st.warning(f"8/5 uyarısı: {r['ad_soyad']}")


# ── BİLGİ SAYFASI ────────────────────────────────────────────────────────────
def _sayfa_bilgi() -> None:
    st.subheader("Bilgi ve canlı durum özeti")
    toplam_personel  = int((db.sql_one("SELECT COUNT(*) AS c FROM personel") or {"c": 0})["c"])
    toplam_gemi      = int((db.sql_one("SELECT COUNT(*) AS c FROM gemi")      or {"c": 0})["c"])
    toplam_izin_kaydi= int((db.sql_one("SELECT COUNT(*) AS c FROM izin")      or {"c": 0})["c"])
    aktif_izinde     = int((db.sql_one("SELECT COUNT(*) AS c FROM izin WHERE date('now') BETWEEN baslangic AND bitis") or {"c": 0})["c"])
    sabit   = int((db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi = 'SABIT'"  ) or {"c": 0})["c"])
    grupcu  = int((db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi = 'GRUPCU' ") or {"c": 0})["c"])
    izinci  = int((db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi = 'IZINCI' ") or {"c": 0})["c"])
    tersane = int((db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE vardiya_tipi = '8_5'    ") or {"c": 0})["c"])
    st.markdown(
        f"""
- Toplam personel: **{toplam_personel}**
- Toplam gemi: **{toplam_gemi}**
- Toplam izin kaydı: **{toplam_izin_kaydi}**
- Şu an izinde olan personel: **{aktif_izinde}**
- Sabit vardiya: **{sabit}**
- Grupçu: **{grupcu}**
- İzinci: **{izinci}**
- Tersane (8/5): **{tersane}**
        """
    )
    gemi_bazli = db.sql_all(
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


# ── ANA FONKSİYON ─────────────────────────────────────────────────────────────
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
        h1, h2, h3, h4, p, li, label, span, div { color: #2f251b !important; }
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
        [data-baseweb="select"] input { color: #2f251b !important; }
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
        .stAlert { border-radius: 10px; }
        @media (max-width: 768px) {
          .block-container { padding: 0.8rem 0.7rem 1.2rem; }
          .stDataFrame { font-size: 13px; }
          h1, h2, h3 { line-height: 1.2; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    db.init_db()
    if not st.session_state.get("ordino_auth"):
        _login_form()
        return
    _logout()
    st.sidebar.caption("Şifreyi değiştirmek için `.env` veya Streamlit Cloud Secrets içinde `ORDINO_ADMIN_PASSWORD` düzenleyin.")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["Gemiler", "Personel", "İzin", "Çarkçı", "Öneri", "Bilgi"]
    )
    with tab1: _sayfa_excel()
    with tab2: _sayfa_personel()
    with tab3: _sayfa_izin()
    with tab4: _sayfa_carkci()
    with tab5: _sayfa_oneri()
    with tab6: _sayfa_bilgi()


main()
