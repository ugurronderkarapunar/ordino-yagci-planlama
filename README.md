# Ordino — Yağcı planlaması (modüler)

Streamlit tabanlı vardiya planlama aracı. Veri **SQLite** üzerindedir; v8 tarafında eklenen **vardiya_plan**, **gemi_makine**, **sertifika** ve **takas** tabloları migrasyonla oluşturulur.

## Kurulum

```bash
pip install -r requirements.txt
streamlit run app.py
```

Giriş bilgileri: `.env` veya Streamlit Secrets içinde `ORDINO_ADMIN_USER` / `ORDINO_ADMIN_PASSWORD` (varsayılan `admin` / `7283` — üretimde mutlaka değiştirin).

## Modül yapısı (backend ağırlıklı)

| Yol | Açıklama |
|-----|----------|
| `src/constants.py` | Vardiya saatleri, NLP kelime listeleri, varsayılan ayarlar |
| `src/time_utils.py` | Saat çakışması ve süre (dakika) |
| `src/json_utils.py` | `gemi_id_list` / `makine_tipi_id_list` JSON yardımcıları |
| `src/database.py` | Bağlantı, şema, migrasyon, `gemi_makine` tohumlaması |
| `src/services/planning_service.py` | Plan sorguları (çakışma, izin, haftalık saat, bugünün planı) |
| `src/services/oneri_engine.py` | v8 öneri motoru (NLP + kurallar; Streamlit bağımsız) |
| `src/ui/v8_yapboz.py` | Yapboz arayüzü |
| `app.py` | Giriş, sekmeler, sidebar planlama ayarları |

## QA ve Excel raporu

```bash
python -m pytest tests -q
python scripts/qa_report_excel.py
```

Çıktı: `reports/ordino_qa_raporu.xlsx` (özet + test satırları).

## Yeni GitHub reposu

Yerelde:

```bash
gh repo create ordino-yagci-v8 --public --source=. --remote=origin --push
```

Mevcut repoyu kopyalayıp yeni remote ile:

```bash
git remote rename origin upstream
git remote add origin https://github.com/KULLANICI/ordino-yagci-v8.git
git push -u origin master
```
