# Konteks Eksperimen PalmSonic untuk OpenCode

Dokumen ini adalah handoff teknis proyek per 24 September 2026. Baca dokumen
ini sebelum mengubah firmware, perekam, GUI, atau algoritme klasifikasi.

## Tujuan proyek

PalmSonic-AI mencoba merekam sinyal ultrasonik di sekitar tanaman sawit sebagai
raw PCM, kemudian menguji apakah sinyal tersebut dapat digunakan untuk analisis
tanaman. Tahap sekarang masih pilot akuisisi dan kontrol box. Belum ada bukti
bahwa sistem dapat mendeteksi keberadaan tanaman atau kondisi sehat dan sakit
secara konsisten.

## Hardware

- Core: RAK4631 dengan nRF52840.
- Base board: RAK19007.
- Mikrofon PDM ultrasonik: RAK18032, berbasis SPH0655LM4H-1.
- Jalur data: USB CDC serial ke komputer Windows.
- Port yang terakhir terdeteksi: COM11, USB VID:PID `239A:8029`.

Pembagian fungsi sistem:

```text
RAK18032          -> menangkap sinyal akustik/PDM
RAK4631           -> konversi PDM ke PCM dan stream USB
Python di laptop  -> membuat WAV, analisis, training, dan klasifikasi
```

Hardware tidak mempunyai pengetahuan bawaan tentang tanaman. RAK18032 adalah
sensor suara, bukan detektor tanaman. Klasifikasi tetap memerlukan dataset
berlabel dan model yang dilatih.

## Format data yang berjalan

- Raw PCM keluaran peripheral PDM.
- Signed 16-bit little-endian.
- Mono.
- 62.500 sampel/detik.
- WAV lossless di komputer.
- Tidak ada FFT, normalisasi, kompresi, atau filter software tambahan di alat.
- Peripheral nRF52840 tetap melakukan filter/desimasi PDM-ke-PCM; jadi ini raw
  PCM, bukan bitstream raw PDM.

Format paket USB memakai magic `SAWT`, versi 1, header 24 byte, nomor urut blok,
sample rate, jumlah sampel, gain, dan penghitung drop. Pemeriksaan langsung
terakhir menghasilkan:

```text
port       COM11
magic      SAWT
rate       62500
samples    256 per blok
gain       80
dropped    0
```

## Batas frekuensi

Mikrofon RAK18032 diklaim merespons sekitar 20-80 kHz. Firmware saat ini hanya
menghasilkan PCM 62,5 kS/s sehingga batas Nyquist adalah 31,25 kHz. Analisis
eksperimental dibatasi ke sekitar 20-28 kHz.

Mode clock PDM sekitar 4 MHz berasal dari implementasi high-rate BSP RAK dan
belum divalidasi secara metrologis. Sebelum klaim ilmiah, uji dengan sumber nada
ultrasonik yang diketahui, misalnya 20, 24, dan 28 kHz. Sistem saat ini tidak
merekam penuh sampai 80 kHz.

## Firmware

Lokasi:

```text
kodingan_hardware/RawSawitRecorder/RawSawitRecorder.ino
```

Status:

- Berhasil dikompilasi untuk `rakwireless:nrf52:WisCoreRAK4631Board`.
- Flash 66.272 byte atau 8%.
- RAM 48.672 byte atau 20%.
- Ring buffer sudah dinaikkan menjadi 64 blok, sekitar 262 ms.
- Gain tetap 80 karena rekaman terakhir tidak menunjukkan clipping bermasalah.
- Firmware terbaru perlu di-upload ulang bila perubahan ring buffer belum pernah
  diunggah setelah pengeditan.

Jangan menaikkan mode ke PCM 100/200 kS/s begitu saja. Implementasi RAK memakai
clock sekitar 8/16 MHz untuk mode tersebut, melebihi batas clock mikrofon yang
disebut sekitar 4,8 MHz.

## Perangkat lunak

Perekaman biasa:

```text
recorder.py
gui_recorder.py
Buka_Recorder_GUI.bat
```

Deteksi real-time:

```text
testing/deteksi_realtime.py
testing/Buka_Deteksi_Realtime.bat
testing/realtime_detector/config.py
testing/realtime_detector/features.py
testing/realtime_detector/protocol.py
testing/realtime_detector/recorder.py
testing/realtime_detector/gui.py
```

`testing/cek_isi_box.py` lama sudah dihapus karena perekaman dan deteksi telah
disatukan ke GUI real-time.

Port serial hanya dapat dibuka satu program. Jika muncul `PermissionError(13)
Access is denied`, tutup GUI PalmSonic lain, Arduino Serial Monitor, Serial
Plotter, atau proses Python lain yang sedang memakai COM11.

## Data referensi yang tersedia

Referensi kosong:

```text
testing/kosong/Kosong.wav
testing/kosong/kosong_02.wav
```

Referensi tanaman:

```text
testing/sawit_sehat/sawit.wav
testing/sawit_sehat/sawit_02.wav
```

Jumlah kalibrasi saat ini hanya dua sesi per kelas. Ini terlalu sedikit untuk
menyatakan akurasi penggunaan umum.

## Hasil eksperimen awal

Energi absolut tidak konsisten antar-sesi:

| Rekaman | Kondisi | Median energi empat pita 20-28 kHz dalam dBFS |
|---|---|---|
| `Kosong.wav` | kosong | -66,44; -77,09; -67,03; -79,42 |
| `sawit.wav` | tanaman | -64,09; -77,27; -63,27; -75,83 |
| `kosong_02.wav` | kosong | -49,59; -62,92; -52,64; -69,18 |
| `sawit_02.wav` | tanaman | -71,41; -77,07; -63,03; -76,62 |

Pada pasangan lama tanaman lebih keras, tetapi pada pasangan baru rekaman kosong
jauh lebih keras. Karena itu volume absolut tidak boleh digunakan untuk
menentukan keberadaan tanaman.

Fitur pilot terakhir memakai selisih energi relatif:

```text
kontras = energi 24-26 kHz - energi 20-22 kHz
```

Referensi yang tersedia sempat menunjukkan:

| Rekaman | Kontras median |
|---|---:|
| kosong lama | -0,57 dB |
| kosong baru | -3,08 dB |
| tanaman lama | +0,84 dB |
| tanaman baru | +8,41 dB |

Atas dasar itu detektor pilot memakai batas 0 dB: negatif menjadi `KOSONG`,
positif menjadi `ADA TANAMAN`. Beberapa percobaan bernama jelas cocok:

| Rekaman uji, bukan kalibrasi | Prediksi |
|---|---|
| `realtim_kosong.wav` | KOSONG |
| `realtime_kosong.wav` | KOSONG |
| `realtime_ada.wav` | ADA TANAMAN |
| `realtime_ada1.wav` | ADA TANAMAN |
| `realtime_ada3.wav` | ADA TANAMAN |

Namun dua rekaman berikut kemudian selalu diprediksi tanaman:

| Rekaman | Kontras | Prediksi |
|---|---:|---|
| `realtime_20260924_174035.wav` | +2,16 dB | ADA TANAMAN |
| `realtime_20260924_174135.wav` | +7,35 dB | ADA TANAMAN |

Nama kedua file tidak mencatat kondisi sebenarnya. Pengguna melaporkan GUI
cenderung selalu mendeteksi tanaman. Jika file tersebut dibuat saat box kosong,
berarti distribusi fitur kosong dan tanaman saling tumpang-tindih. Jangan
memasukkan kedua file ini ke training sebelum label sebenarnya dikonfirmasi.

## Kesimpulan diagnosis

Tidak ada bukti bahwa firmware menukar label kosong dan tanaman. Firmware hanya
mengirim sampel PCM dan tidak pernah mengetahui label. Kesalahan klasifikasi
berada pada model/data eksperimen.

Detektor sekarang bukan model AI yang sudah dilatih. Ia hanya heuristic pilot
dengan satu kontras spektral dan dataset sangat kecil. Mengubah threshold terus
agar cocok dengan satu rekaman tidak menyelesaikan masalah dan akan menyebabkan
rekaman lain terbalik.

Pola sinyal dapat dipengaruhi oleh:

- pot dan tanah;
- resonansi acoustic box;
- posisi dan orientasi mikrofon;
- posisi kabel dan laptop;
- noise elektronik atau USB;
- waktu perekaman dan lingkungan;
- proses biologis tanaman, bila sinyalnya memang cukup kuat.

Perbedaan box kosong dan box berisi pot+tanaman belum membuktikan suara biologis
tanaman.

## Isi panduan eksperimen asli

Sumber utama:

```text
../Panduan_PalmSonic_AI_12_Minggu.docx
```

Panduan tersebut tidak menyatakan hardware langsung melakukan klasifikasi.
Urutannya adalah:

- Minggu 1-4: akuisisi audio dan kontrol background.
- Minggu 5: QC, sinkronisasi metadata, dan label final.
- Minggu 6: preprocessing serta noise-aware event detection.
- Minggu 7: ekstraksi fitur dan spectrogram.
- Minggu 8: validasi biologis dan temporal.
- Minggu 9: training SVM, Random Forest, dan XGBoost.
- Minggu 10: CNN spectrogram dan fusion.
- Minggu 11: locked test dan generalisasi.

Panduan merencanakan 240 bibit, minimum tiga rekaman valid per bibit, kontrol
empty-box pada awal/tengah/akhir sesi, dan pembagian train/test berdasarkan
`plant_id`. Detektor biner kosong/tanaman yang ada sekarang hanya alat pilot dan
bukan model akhir dalam panduan.

## Langkah yang direkomendasikan berikutnya

1. Hentikan penyesuaian threshold berdasarkan satu file.
2. Verifikasi alat dengan nada ultrasonik 20, 24, dan 28 kHz yang diketahui.
3. Kunci posisi sensor, kabel, box, laptop, dan sumber daya.
4. Buat tiga kondisi kontrol:
   - box kosong;
   - pot + tanah tanpa tanaman;
   - pot + tanaman.
5. Rekam minimal 10-20 sesi independen per kondisi untuk pilot, masing-masing
   60-120 detik.
6. Acak/selang-seling urutan kondisi dan tunggu 2-5 menit setelah isi box
   berubah.
7. Catat kondisi pada nama file dan metadata; jangan memakai nama timestamp
   tanpa label.
8. Pisahkan sesi train, validation, dan locked test sebelum training.
9. Mulai dengan baseline sederhana seperti logistic regression/SVM/Random
   Forest menggunakan fitur spektral, event rate, SNR, dan artifact flag.
10. Nilai confusion matrix pada sesi yang benar-benar tidak ikut training.

Training tidak menjamin keberhasilan. Jika setelah kontrol ketat distribusi
kosong, pot, dan tanaman tetap tumpang-tindih, berarti sinyal yang ditangkap pada
20-28 kHz belum cukup untuk tugas tersebut. Pertimbangkan piezo/contact sensor,
perekam ultrasonik full-band, atau raw PDM dengan hardware lain.

## Pengujian kode yang tersedia

Jalankan:

```powershell
python -m unittest -v testing\test_realtime_detector.py
```

Tes saat terakhir diperiksa:

- parser paket biner;
- seluruh sesi referensi;
- validasi leave-one-session-out;
- invariansi terhadap perubahan level umum +20 dB;
- percobaan bernama jelas yang tidak ikut kalibrasi.

Tes tersebut menguji konsistensi kode pada file yang sudah ada, bukan akurasi
ilmiah atau generalisasi ke sesi baru.

## Dokumen lain

- `README.md`: cara firmware, upload, dan perekaman raw PCM.
- `testing/README.md`: cara pengujian dan GUI real-time.
- `LAPORAN_AUDIT_SISTEM.md`: audit teknis dan hasil sebelumnya.
- `alternatif.md`: opsi hardware untuk bandwidth lebih tinggi.

## Instruksi untuk agent berikutnya

- Jangan mengklaim alat sudah dapat mendeteksi tanaman secara andal.
- Jangan mengubah label atau memindahkan WAV tanpa mengetahui kondisi sebenarnya.
- Jangan memasukkan file evaluasi ke kalibrasi hanya agar tes terlihat benar.
- Jangan menaikkan sample rate firmware melewati batas mikrofon tanpa desain raw
  PDM yang tervalidasi.
- Pertahankan file WAV asli; hasil preprocessing harus ditulis ke file baru.
- Gunakan pemisahan train/test berdasarkan sesi dan `plant_id`, bukan potongan
  audio acak.
- Laporkan ketidakpastian dan kegagalan eksperimen apa adanya.
