# PalmSonic AI — Deteksi Isi Box Sawit Real-time

Sistem deteksi akustik untuk mendeteksi **keberadaan tanaman sawit** di dalam box uji — hanya dari "pendengaran" ultrasonik 20–28 kHz, tanpa kamera.

Mikrofon ultrasonik (RAK18032 + RAK4631) mendengarkan box, dan aplikasi desktop memutuskan setiap 10 detik:

```
        KOSONG   atau   ADA TANAMAN
   (+ probabilitas 0–100% dan kualitas BAIK / LEMAH)
```

## Cara kerja

1. **Firmware RAK4631** merekam raw PCM 62.500 Hz, mono, 16-bit — tanpa filter/normalisasi di sisi alat, data dikirim apa adanya lewat USB (protokol biner berheader `SAWT` dengan penomoran paket untuk mendeteksi drop/gap).
2. **GUI real-time** memotong audio menjadi segmen 10 detik dan menghitung **kontras spektrum relatif**: energi pita 24–26 kHz dibandingkan 20–22 kHz.
3. **Model klasifikasi** (`kontras-logreg-v1`, LogisticRegression dengan bobot per sesi seimbang) mengubah kontras itu menjadi **probabilitas** — bukan sekadar ambang keras.
4. Keputusan stabil setelah 3 segmen (±30 detik), lengkap dengan indikator kualitas agar hasil ragu bisa langsung dikenali.

Evaluasi dengan **leave-one-session-out**: **9/9 sesi benar (100%)**, 98,6% per segmen.

## Fitur

- 🎙️ **Deteksi real-time** — keputusan + probabilitas setiap 10 detik
- 📊 **Probabilitas & kualitas** — setiap keputusan punya skala keyakinan (`BAIK`/`LEMAH`), bukan cuma ya/tidak
- 🎚️ **Kalibrasi otomatis** — membaca seluruh WAV referensi di folder `kosong/` dan `sawit_sehat/`, menyeimbangkan bobot antar sesi
- 📈 **Mode banding** — `bandingkan_rekaman.py` menghasilkan spektrum, metrik per pita, dan laporan perbandingan antar rekaman
- 🔌 **Robust terhadap gangguan USB** — penomoran paket, deteksi drop/gap, dan clipping dihitung langsung di GUI
- 🧪 **Tooling training** — `train_model.py` (training + evaluasi LOSO) dan `uji_model.py` (uji file WAV mana pun)
- 🧩 **Kode termodular** — package `realtime_detector/` (config, features, protocol, recorder, gui, ml)

## Struktur project

```
Project_sawit 2/
├── Panduan_PalmSonic_AI_12_Minggu.docx   # panduan eksperimen 12 minggu
├── alat/
│   ├── README.md                         # panduan alat
│   ├── recorder.py / gui_recorder.py     # perekam WAV + GUI
│   ├── kodingan_hardware/
│   │   └── RawSawitRecorder/             # firmware RAK4631
│   └── testing/
│       ├── deteksi_realtime.py           # launcher deteksi
│       ├── train_model.py                # training model
│       ├── uji_model.py                  # uji model pada WAV
│       ├── model.pkl                     # model terlatih
│       ├── realtime_detector/            # package deteksi
│       ├── kosong/                       # referensi box kosong
│       └── sawit_sehat/                  # referensi sawit sehat
```

## Cara menjalankan

### Prasyarat

```powershell
pip install -r alat/requirements.txt
```

Python 3.12+, RAK4631 terhubung via USB.

### Rekam data

```powershell
cd alat
python recorder.py --port COM11 --duration 600 --output testing\kosong\kosong_01.wav
```

### Deteksi real-time

```powershell
cd alat\testing
python deteksi_realtime.py
```

Pilih port, klik **Kalibrasi ulang**, lalu **Mulai deteksi**. Keputusan pertama muncul setelah 10 detik dan stabil setelah ±30 detik.

### Training & uji model

```powershell
python train_model.py    # training + evaluasi LOSO -> model.pkl
python uji_model.py      # uji semua WAV referensi
python uji_model.py path\ke\file.wav    # uji file tertentu
```

### Test

```powershell
python -m unittest test_realtime_detector -v
```

## Konten repo

- 📁 `alat/testing/kosong/`, `sawit_sehat/` — sesi rekaman referensi (WAV raw 62,5 kHz)
- 📁 `alat/testing/hasil/` — laporan perbandingan & laporan training (CSV, PNG, TXT)
- 📄 `alat/LAPORAN_AUDIT_SISTEM.md` — catatan teknis sistem
- 📄 `alat/Manual Book Aplikasi Deteksi Kesehatan Sawit (1).pdf` — manual aplikasi

## Teknologi

- **Hardware**: RAK4631 (nRF52840) + mikrofon ultrasonik RAK18032
- **Firmware**: Arduino (RAK nRF52 BSP), raw PCM 62.500 Hz
- **Software**: Python 3.12 · NumPy · SciPy · scikit-learn · pyserial · Tkinter
