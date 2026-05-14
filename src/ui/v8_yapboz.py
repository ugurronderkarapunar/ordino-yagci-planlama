"""İnteraktif Yapboz — gemi/makine/personel vardiya ataması (v8)."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import streamlit as st

from src import database as db
from src.constants import DEFAULT_AYARLAR, VARDIYA_RENKLERI, VARDIYA_SAATLERI
from src.json_utils import id_listesi
from src.services import planning_service as ps
from src.services.oneri_engine import onerileri_hesapla_v8


def _btn(label: str, key: str, caption: str, **kwargs):
    if "type" not in kwargs:
        kwargs["type"] = "primary"
    clicked = st.button(label, key=key, **kwargs)
    st.caption(caption)
    return clicked


def render_yapboz() -> None:
    st.subheader("İnteraktif Yapboz (v8)")
    if "yapboz_sec_tarih" not in st.session_state:
        st.session_state.yapboz_sec_tarih = date.today()

    c_tarih, c_btns = st.columns([3, 1])
    with c_tarih:
        sec_tarih = st.date_input(
            "Tarih",
            value=st.session_state.yapboz_sec_tarih,
            key="yapboz_sec_tarih",
        )
    with c_btns:
        st.write("")
        hc1, hc2 = st.columns(2)
        if hc1.button("⬅️ Hafta", key="yapboz_hafta_geri"):
            st.session_state.yapboz_sec_tarih = sec_tarih - timedelta(days=7)
            st.rerun()
        if hc2.button("Hafta ➡️", key="yapboz_hafta_ileri"):
            st.session_state.yapboz_sec_tarih = sec_tarih + timedelta(days=7)
            st.rerun()

    gemiler = db.sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    tum_mak = db.sql_all("SELECT id, ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not tum_mak:
        st.warning("Gemi ve makine ekleyin.")
        return

    ayarlar = st.session_state.get("ayarlar", DEFAULT_AYARLAR)

    col1, col2 = st.columns(2)
    with col1:
        if _btn(
            "Tüm atamaları temizle",
            key="yapboz_temizle",
            caption="Seçili tarihteki tüm vardiyaları siler",
            type="secondary",
        ):
            db.sql_run("DELETE FROM vardiya_plan WHERE tarih=?", (sec_tarih.isoformat(),))
            st.toast("Tüm atamalar temizlendi.", icon="🧹")
            st.rerun()
    with col2:
        if _btn(
            "Hepsini otomatik doldur",
            key="yapboz_otomatik",
            caption="Boş pozisyonları öneri motoru ile doldurur",
        ):
            with st.spinner("Otomatik dolduruluyor..."):
                for gemi in gemiler:
                    for gm in db.sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],)):
                        mak_id = int(gm["makine_tipi_id"])
                        if ps.vardiya_plani_kontrol(int(gemi["id"]), mak_id, sec_tarih) is None:
                            oneri = onerileri_hesapla_v8(
                                int(gemi["id"]),
                                mak_id,
                                sec_tarih,
                                limit=1,
                                ayarlar=ayarlar,
                            )
                            if oneri and not oneri[0].get("zaten_atanmis"):
                                vt = str(oneri[0].get("vardiya_tipi") or "SABIT")
                                b, e = VARDIYA_SAATLERI.get(vt, ("08:00", "08:00"))
                                try:
                                    db.sql_run(
                                        "INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                        (int(oneri[0]["id"]), int(gemi["id"]), mak_id, sec_tarih.isoformat(), b, e),
                                    )
                                except sqlite3.IntegrityError:
                                    pass
            st.toast("Boş pozisyonlar dolduruldu.", icon="🤖")
            st.rerun()

    izinli = ps.bugun_izinli_ids(sec_tarih)

    for gemi in gemiler:
        gemi_mak = db.sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],))
        if not gemi_mak:
            continue
        g_mak_ids = {int(r["makine_tipi_id"]) for r in gemi_mak}
        g_makineler = [m for m in tum_mak if int(m["id"]) in g_mak_ids]
        atanan = db.sql_one(
            "SELECT COUNT(*) AS c FROM vardiya_plan WHERE gemi_id=? AND tarih=?",
            (gemi["id"], sec_tarih.isoformat()),
        )
        atanan_count = int(atanan["c"]) if atanan else 0
        toplam_poz = len(g_makineler)
        doluluk = "✅" if atanan_count == toplam_poz else ("🟡" if atanan_count > 0 else "🔴")
        with st.expander(f"{doluluk} {gemi['ad']} — {atanan_count}/{toplam_poz} dolu", expanded=(atanan_count < toplam_poz)):
            cols = st.columns(max(len(g_makineler), 1))
            for i, mak in enumerate(g_makineler):
                with cols[i]:
                    mevcut = ps.vardiya_plani_kontrol(int(gemi["id"]), int(mak["id"]), sec_tarih)
                    st.markdown(f"**{mak['ad']}**")
                    if mevcut is not None:
                        p = db.sql_one(
                            "SELECT id, ad, soyad, vardiya_tipi, durum, is_kalitesi FROM personel WHERE id=?",
                            (mevcut,),
                        )
                        if p:
                            renk = VARDIYA_RENKLERI.get(str(p["vardiya_tipi"]), "#3a3a4e")
                            opacity = {1: 0.5, 2: 0.6, 3: 0.75, 4: 0.9, 5: 1.0}.get(int(p["is_kalitesi"] or 3), 0.8)
                            st.markdown(
                                f"<div style='background:{renk};padding:8px;border-radius:8px;color:white;"
                                f"text-align:center;font-weight:bold;opacity:{opacity}'>{p['ad']} {p['soyad']}<br>"
                                f"({p['vardiya_tipi']}) {p.get('durum', '')}<br>⭐{p['is_kalitesi']}</div>",
                                unsafe_allow_html=True,
                            )
                        cx, cd = st.columns(2)
                        with cx:
                            if _btn("Çıkar", key=f"c_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="Vardiyadan çıkarır", type="secondary"):
                                db.sql_run(
                                    "DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",
                                    (gemi["id"], mak["id"], sec_tarih.isoformat()),
                                )
                                st.toast("Personel çıkarıldı", icon="❌")
                                st.rerun()
                        with cd:
                            if _btn("Değiştir", key=f"deg_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="Çıkarıp öneri listesi açar"):
                                db.sql_run(
                                    "DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",
                                    (gemi["id"], mak["id"], sec_tarih.isoformat()),
                                )
                                st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = onerileri_hesapla_v8(
                                    int(gemi["id"]), int(mak["id"]), sec_tarih, limit=5, ayarlar=ayarlar
                                )
                                st.rerun()
                    else:
                        st.warning("Boş")
                        hedef_gun = sec_tarih.weekday()
                        uygun: list[str] = ["Seçiniz..."]
                        for p in db.sql_all(
                            "SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR IFNULL(durum,'Gemide') IN ('Gemide','İskelede'))"
                        ):
                            if int(p["id"]) in izinli:
                                continue
                            if str(p.get("vardiya_tipi") or "") != "IZINCI":
                                gj = p.get("vardiya_gunleri")
                                if gj:
                                    try:
                                        import json

                                        il = json.loads(str(gj))
                                        if isinstance(il, list) and il and hedef_gun not in il:
                                            continue
                                    except (json.JSONDecodeError, TypeError, ValueError):
                                        pass
                            mids = id_listesi(p.get("makine_tipi_id_list"))
                            if mids and int(mak["id"]) not in mids:
                                continue
                            if mids and not ps.sertifika_gecerli_mi(int(p["id"]), int(mak["id"]), sec_tarih):
                                continue
                            gids = id_listesi(p.get("gemi_id_list"))
                            if p.get("gemi_id"):
                                gids.append(int(p["gemi_id"]))
                            if gids and int(gemi["id"]) not in gids:
                                continue
                            if int(p.get("carkci_ile_sorun") or 0):
                                continue
                            uygun.append(f"{p['ad']} {p['soyad']} ({p.get('durum', '')})")
                        if len(uygun) > 1:
                            sec = st.selectbox("Manuel seç", uygun, key=f"s_{gemi['id']}_{mak['id']}_{sec_tarih}")
                            if sec != "Seçiniz...":
                                pid_row = db.sql_one("SELECT id, vardiya_tipi FROM personel WHERE ad || ' ' || soyad = ?", (sec.split(" (")[0],))
                                if pid_row:
                                    b, e = VARDIYA_SAATLERI.get(str(pid_row["vardiya_tipi"]), ("08:00", "08:00"))
                                    if ps.iki_gun_ust_uste_mi(int(pid_row["id"]), sec_tarih):
                                        st.warning("Bu personel bir önceki gün de çalışmış.")
                                    try:
                                        db.sql_run(
                                            "INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                            (int(pid_row["id"]), int(gemi["id"]), int(mak["id"]), sec_tarih.isoformat(), b, e),
                                        )
                                        st.toast("Personel atandı.")
                                        st.rerun()
                                    except sqlite3.IntegrityError:
                                        st.error("Bu atama zaten mevcut.")
                        else:
                            st.caption("Uygun personel yok.")
                        if _btn("Öneri al (5)", key=f"onerbtn_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="En uygun 5 aday"):
                            st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = onerileri_hesapla_v8(
                                int(gemi["id"]), int(mak["id"]), sec_tarih, limit=5, ayarlar=ayarlar
                            )
                            st.rerun()
                        key_on = f"oneriler_{gemi['id']}_{mak['id']}"
                        if key_on in st.session_state and st.session_state[key_on]:
                            st.markdown("**Önerilen:**")
                            for o in st.session_state[key_on]:
                                co1, co2 = st.columns([4, 1])
                                with co1:
                                    st.write(f"{o['ad']} {o['soyad']} ({o['vardiya_tipi']}) — {o['puan']}")
                                with co2:
                                    if _btn("Ata", key=f"ata_{gemi['id']}_{mak['id']}_{o['id']}", caption="Seçilen adayı atar"):
                                        if o.get("zaten_atanmis"):
                                            st.error("Zaten atanmış.")
                                        else:
                                            b, e = VARDIYA_SAATLERI.get(str(o["vardiya_tipi"]), ("08:00", "08:00"))
                                            try:
                                                db.sql_run(
                                                    "INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                    (int(o["id"]), int(gemi["id"]), int(mak["id"]), sec_tarih.isoformat(), b, e),
                                                )
                                                del st.session_state[key_on]
                                                st.toast(f"{o['ad']} {o['soyad']} atandı.")
                                                st.rerun()
                                            except sqlite3.IntegrityError:
                                                st.error("Bu atama zaten mevcut.")
