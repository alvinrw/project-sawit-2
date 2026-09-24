# Pengujian Box Kosong dan Sawit Sehat

Folder ini digunakan untuk membandingkan rekaman acoustic box kosong dengan rekaman acoustic box berisi pot dan tanaman sawit sehat.

## Struktur folder

```text
testing/
|- kosong/                 # WAV acoustic box kosong
|- sawit_sehat/            # WAV pot + tanaman sawit sehat
|- hasil/                  # Dibuat otomatis oleh skrip
|- bandingkan_rekaman.py
`- README.md
```

## 1. Rekam acoustic box kosong

Dari folder utama `alat`, jalankan:

```powershell
python recorder.py --port COM5 --duration 600 --output testing\kosong\kosong_01.wav
```

Ganti `COM5` dengan port alat. Jangan mengubah posisi mikrofon setelah rekaman ini.

## 2. Rekam sawit sehat

Masukkan pot dan tanaman sawit sehat. Tempatkan sensor sekitar 2 cm dari bagian tanaman yang diuji, tutup box, lalu diamkan selama 2-5 menit. Setelah itu jalankan:

```powershell
python recorder.py --port COM5 --duration 600 --output testing\sawit_sehat\sawit_sehat_01.wav
```

Selama kedua perekaman, gunakan posisi sensor, gain, durasi, dan kondisi ruangan yang sama. Jangan menyentuh box, pot, tanaman, meja, atau kabel.

Pastikan keluaran `recorder.py` menunjukkan:

```text
drop alat 0
gap 0
clipping mendekati 0%
```

## 3. Jalankan perbandingan

```powershell
python testing\bandingkan_rekaman.py
```

Hasil akan muncul di `testing/hasil/`:

- `ringkasan.csv`: metrik setiap WAV;
- `perbandingan_spektrum.png`: spektrum box kosong dan sawit sehat;
- `perbandingan_metric.png`: energi 20-28 kHz dan kandidat event per menit;
- `laporan.txt`: ringkasan dan interpretasi awal.

Analisis spektrum dan kandidat event mengabaikan 0,1 detik pertama setiap WAV
untuk mencegah transien saat PDM mulai dianggap sebagai klik tanaman. File WAV
asli tidak dipotong atau diubah.

Satu file per folder sudah dapat dianalisis, tetapi hasil lebih kuat jika setiap kondisi direkam beberapa kali. Beri nama berurutan seperti `kosong_02.wav` dan `sawit_sehat_02.wav`; skrip otomatis membaca seluruh WAV.

Perbandingan ini hanya menguji apakah box kosong berbeda dari box berisi pot dan sawit sehat. Perbedaan belum membuktikan bahwa suaranya berasal dari proses biologis tanaman, karena pot, tanah, dan perubahan pantulan di dalam box juga dapat memengaruhi hasil.

## GUI deteksi real-time

Kalibrasi, perekaman WAV raw, dan deteksi sudah disatukan dalam satu aplikasi.
Tutup GUI recorder biasa, Serial Monitor, dan Serial Plotter, kemudian klik dua
kali:

```text
Buka_Deteksi_Realtime.bat
```

Atau dari PowerShell di folder `testing`:

```powershell
python .\deteksi_realtime.py
```

GUI memilih port USB RAK4631, membaca semua WAV dalam folder `kosong` dan
`sawit_sehat` sebagai kalibrasi, serta menyimpan rekaman baru sebagai WAV raw.
Keputusan diperbarui setiap 10 detik dan menjadi stabil setelah sekitar 30
detik.

Model tidak lagi memakai keras-lemahnya rekaman secara absolut. Setiap segmen
memakai **kontras relatif energi 24-26 kHz terhadap 20-22 kHz**, sehingga
perubahan volume umum antarsesi tidak langsung membalik label. Pada referensi
saat ini nilai negatif konsisten dengan kosong dan nilai positif konsisten
dengan tanaman. Setiap file WAV dianggap satu sesi dan mendapat bobot yang
sama, walaupun durasinya berbeda.
GUI juga menampilkan akurasi validasi lintas sesi saat sedikitnya tersedia dua
WAV independen untuk masing-masing kelas.

Keluaran selalu biner: `KOSONG` atau `ADA TANAMAN`. Bila jarak kedua kelas
sangat dekat, GUI tetap memberikan label terdekat tetapi menampilkan peringatan
bahwa selisihnya tipis. Detektor hanya berlaku untuk box, posisi sensor, gain,
dan kondisi perekaman yang sama dengan data referensi.

`BAIK` bukan berarti keputusan biologis sudah terbukti; artinya pola cukup dekat
dengan salah satu referensi. Label dengan kualitas `LEMAH` tetap biner sesuai
permintaan, tetapi jangan dipakai sebagai ground truth atau data latih.

Saat ini referensi berisi dua sesi per kelas. Validasi lintas sesi internal
mencapai 100%, tetapi angka ini **bukan akurasi penggunaan umum** karena empat
sesi masih terlalu sedikit. Targetkan sedikitnya 10 sesi independen per kelas,
direkam bergantian dan pada waktu berbeda.

### Struktur kode hasil refactor

```text
testing/
|- deteksi_realtime.py          # launcher pendek
|- Buka_Deteksi_Realtime.bat    # buka GUI dengan klik dua kali
`- realtime_detector/
   |- config.py                 # konstanta dan struktur kalibrasi
   |- features.py               # FFT, fitur, kalibrasi, klasifikasi
   |- protocol.py               # parser paket biner RAK4631
   |- recorder.py               # thread rekam WAV dan deteksi live
   |- gui.py                    # tampilan serta kontrol aplikasi
   |- __init__.py
   `- __main__.py
```
