# Ordino Canliya Alma

Bu proje Streamlit tabanli fullstack web uygulamasidir. Telefon, tablet ve bilgisayarda tarayici uzerinden acilir.

## 1) Yerel test

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 2) Render ile canliya alma (onerilen)

1. Projeyi GitHub'a push et.
2. [Render](https://render.com/) hesabinda **New + -> Blueprint** sec.
3. Bu repoyu sec; `render.yaml` otomatik algilanir.
4. Ortam degiskenlerini gir:
   - `ORDINO_ADMIN_USER`
   - `ORDINO_ADMIN_PASSWORD`
   - `ORDINO_DB_PATH` = `/var/data/ordino.sqlite3` (hazir geliyor)
5. Deploy bitince Render sana kalici HTTPS URL verir.

## 3) Veri kaliciligi

- `render.yaml` icindeki persistent disk nedeniyle veriler uygulama yeniden baslasa da kaybolmaz.
- Yedek almak icin `/var/data/ordino.sqlite3` dosyasini periyodik olarak disari al.

## 4) Mobil kullanim

- Uygulama responsive olacak sekilde duzenlendi.
- iPhone/Safari, Android/Chrome ve masaustu tarayicilarda ayni URL ile calisir.

