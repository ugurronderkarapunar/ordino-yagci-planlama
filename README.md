# Ordino — Yağcı planlaması

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.40%2B-FF4B4B?logo=streamlit)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite)

Streamlit + SQLite ile gemi–makine–personel vardiya planı. Bu dalda **modüler backend** (`src/services`, `src/database` migrasyonları) ve **Yapboz (v8)** sekmesi kullanılır; giriş `.env` / Secrets ile yapılır.

## Kurulum

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Modül yapısı

| Yol | Açıklama |
|-----|----------|
| `src/constants.py` | Vardiya saatleri, NLP listeleri, varsayılan ayarlar |
| `src/time_utils.py` | Saat çakışması ve süre |
| `src/json_utils.py` | Liste JSON alanları |
| `src/database.py` | WAL, migrasyon, `vardiya_plan` / `gemi_makine` / tohumlama |
| `src/services/planning_service.py` | Plan sorguları |
| `src/services/oneri_engine.py` | v8 öneri motoru (Streamlit bağımsız) |
| `src/ui/v8_yapboz.py` | Yapboz arayüzü |
| `app.py` | Kimlik doğrulama, sekmeler, sidebar planlama ayarları |

## QA ve Excel

```bash
python -m pytest tests -q
python scripts/qa_report_excel.py
```

Çıktı: `reports/ordino_qa_raporu.xlsx` (git’e alınmaz; `*.xlsx` ignore).

## Yeni GitHub reposu

```bash
gh repo create ordino-yagci-v8 --public --source=. --remote=origin --push
```

veya yeni boş repo oluşturup:

```bash
git remote add yeni https://github.com/KULLANICI/REPO.git
git push yeni master
```
