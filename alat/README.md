# Perekam Suara Sawit Raw - RAK4631 + RAK18032

Proyek ini sekarang mengambil keluaran peripheral PDM secara langsung sebagai **PCM signed 16-bit, mono, 62.500 sampel/detik**, lalu mengirimkannya melalui USB ke komputer. Data tidak melewati FFT, filter software tambahan, normalisasi, kompresi, penghilangan DC, atau pemrosesan aplikasi lain. `recorder.py` menyimpan sampel tersebut sebagai WAV yang siap dianalisis.

Istilah **raw** di proyek ini berarti raw PCM keluaran peripheral. Ini bukan bitstream PDM mentah: peripheral nRF52840 tetap melakukan filter/desimasi PDM-ke-PCM yang memang wajib untuk menghasilkan sampel WAV.

## Yang diperbaiki

Kode lama bukan perekam raw. Kode tersebut:

- mengubah setiap blok menjadi hasil FFT;
- hanya mencetak 500 nilai spektrum sebagai teks;
- memberi jeda 100 ms untuk setiap nilai dan jeda tambahan antarsiklus;
- memakai buffer tunggal, sehingga blok baru mudah menimpa data yang belum diproses;
- menyebut 48 kHz, sedangkan konfigurasi BSP RAK menghasilkan sekitar 50 kS/s;
- tidak membuat file audio dan tidak melaporkan data yang hilang.

Perubahan sekarang:

- FFT dan `ApproxFFT.ino` dihapus sepenuhnya;
- keluaran adalah sampel PCM asli dari driver PDM, bukan nilai frekuensi;
- sample rate menggunakan mode high-rate BSP RAK: clock PDM sekitar 4 MHz / rasio 64 = **62,5 kS/s**;
- gain hardware disetel ke 80 (maksimum driver) untuk sinyal lemah;
- buffer cincin 64 blok (sekitar 262 ms) membantu menyerap gangguan USB/Windows sesaat;
- setiap blok memiliki nomor urut dan penghitung drop;
- stream memakai format biner efisien, bukan angka teks;
- skrip komputer membuat WAV, menghitung peak/clipping, dan memperingatkan jika ada blok hilang.

## Batas hardware yang wajib dipahami

RAK18032 memiliki respons mikrofon ultrasonik yang disebut 20-80 kHz dan menerima clock maksimal 4,8 MHz. BSP RAK yang dipakai menyediakan mode high-rate khusus sekitar 4 MHz. Pada rasio desimasi 64, hasilnya 62,5 kS/s, sehingga batas Nyquist hanya **31,25 kHz**.

Catatan penting: nilai clock 4 MHz tersebut berasal dari implementasi vendor RAK dan berada di luar pilihan clock PDM yang tercantum pada spesifikasi publik nRF52840. Firmware sudah berhasil dikompilasi dan rekaman berjalan, tetapi ketepatan respons frekuensinya belum boleh dianggap terkalibrasi. Uji nada ultrasonik yang frekuensinya diketahui (misalnya 20, 24, dan 28 kHz) tetap wajib sebelum membuat klaim ilmiah.

Artinya, kombinasi RAK4631 + driver PDM ini dapat merekam wilayah sekitar 20-31,25 kHz, tetapi **tidak dapat merekam penuh sampai 80 kHz**. Mode `PCM_100000` dan `PCM_200000` memang ada di library, tetapi menghasilkan clock 8 MHz dan 16 MHz - melewati spesifikasi 4,8 MHz mikrofon. Mode itu sengaja tidak dipakai karena data dapat menjadi tidak valid.

Untuk penelitian sampai 80 kHz, target minimal adalah ADC/antarmuka PDM yang menghasilkan PCM minimal 160 kS/s (lebih baik 192 kS/s) tanpa memberi clock mikrofon di atas 4,8 MHz. Ini memerlukan hardware/driver lain; bukan sesuatu yang bisa diperbaiki hanya dengan FFT.

## Isi proyek

```text
alat/
|- kodingan_hardware/
|  `- RawSawitRecorder/
|     `- RawSawitRecorder.ino   # firmware alat
|- recorder.py                  # USB serial ke WAV
|- gui_recorder.py              # GUI perekam WAV
|- testing/                     # perbandingan dan deteksi isi box real-time
|- LAPORAN_AUDIT_SISTEM.md      # diagnosis, perubahan, dan batas sistem
|- requirements.txt             # pyserial
|- README.md
`- Manual Book ...pdf           # manual lama/original
```

## Persiapan Arduino IDE

1. Pasang RAK4631 pada slot core RAK19007 dan RAK18032 pada slot IO. Kencangkan modul sebelum memberi daya.
2. Instal Arduino IDE 2.x dari situs resmi Arduino.
3. Buka **File > Preferences**.
4. Tambahkan URL berikut ke **Additional Boards Manager URLs**:

   ```text
   https://raw.githubusercontent.com/RAKwireless/RAKwireless-Arduino-BSP-Index/main/package_rakwireless_index.json
   ```

5. Buka **Tools > Board > Boards Manager**, cari `RAKwireless`, lalu instal paket WisBlock/RAK4631.
6. Buka **Library Manager**, cari dan instal **RAKwireless Audio Library**. Jika tidak muncul, unduh ZIP dari <https://github.com/RAKWireless/RAKwireless-Audio-library> lalu pilih **Sketch > Include Library > Add .ZIP Library**.

## Cara update/upload firmware

1. Hubungkan USB-C RAK19007 langsung ke komputer. Hindari hub USB yang tidak stabil.
2. Buka file `kodingan_hardware/RawSawitRecorder/RawSawitRecorder.ino` di Arduino IDE.
3. Pilih board **RAK4631** pada **Tools > Board**.
4. Pilih port alat pada **Tools > Port**.
5. Tutup Serial Monitor dan Serial Plotter jika sedang terbuka.
6. Klik **Verify**. Jika berhasil, klik **Upload**.
7. Tunggu sampai Arduino IDE menampilkan upload selesai. LED hijau akan menyala saat `recorder.py` benar-benar sedang merekam.

Jika port bootloader tidak muncul atau upload gagal, tekan tombol reset dua kali dengan cepat. Pilih port baru yang muncul, lalu upload lagi. Setelah firmware berjalan, jangan memakai Serial Plotter: datanya biner dan memang akan terlihat acak.

## Cara merekam WAV raw

### Menggunakan GUI Windows

Pastikan Serial Monitor dan Serial Plotter tertutup, kemudian jalankan:

```powershell
python gui_recorder.py
```

Di Windows, GUI juga dapat dibuka dengan klik dua kali `Buka_Recorder_GUI.bat`.

Pilih port bertuliskan `USB Serial Device`, tentukan durasi dan nama file WAV,
lalu klik **Mulai merekam**. GUI menampilkan peak saat ini, peak maksimum,
persentase clipping, drop alat, gap USB, dan gain firmware secara langsung.

Jika indikator clipping berwarna merah, jangan gunakan rekaman sebagai dataset.
Turunkan `PDM_GAIN` pada firmware, upload ulang, kemudian lakukan tes baru.

### Menggunakan PowerShell

Buka PowerShell di folder proyek ini, lalu jalankan:

```powershell
python -m pip install -r requirements.txt
python recorder.py --port COM5 --duration 180 --output data\sawit_01.wav
```

Ganti `COM5` dengan port alat. Jika hanya ada satu port serial, `--port` boleh dihilangkan:

```powershell
python recorder.py --duration 180 --output data\sawit_01.wav
```

Untuk merekam sampai dihentikan dengan `Ctrl+C`:

```powershell
python recorder.py --port COM5 --duration 0
```

Output normal di akhir rekaman seharusnya menunjukkan:

```text
drop alat 0, gap 0
```

Nilai selain nol berarti ada audio yang hilang. Jangan gunakan rekaman itu sebagai data latih tanpa menandainya.

## Mengatur gain tanpa merusak data raw

Firmware memakai `PDM_GAIN = 80`, yaitu maksimum driver, agar sinyal ultrasonik lemah lebih mudah tertangkap. Ini adalah gain hardware sebelum sampel PCM dibuat; tidak ada penguatan software setelah perekaman.

Perhatikan nilai `peak` dan `clipping` dari `recorder.py`:

- peak ideal sering berada kira-kira antara 5.000 dan 30.000;
- peak mendekati 32.767 dan clipping lebih dari 0,01% berarti gain terlalu tinggi;
- ubah `PDM_GAIN` di bagian atas firmware dari `80` ke `60`, `40`, atau lebih rendah, lalu upload ulang;
- jangan menormalisasi tiap rekaman jika amplitudo akan dipakai sebagai fitur model.

Lakukan uji diam 30 detik dan uji pada batang sawit 3 menit. Gunakan gain, jarak, tekanan sensor, posisi, waktu, dan orientasi yang sama untuk seluruh dataset.

## Penempatan dan prosedur dataset

1. Letakkan port bawah mikrofon sedekat mungkin ke sumber, tanpa menutup lubangnya.
2. Gunakan dudukan/kopling yang konsisten; memegang alat dengan tangan dapat memasukkan getaran dan suara gesekan.
3. Rekam latar belakang pada lokasi yang sama sebelum merekam sawit.
4. Catat ID pohon, kondisi sehat/sakit, waktu, cuaca, posisi pengukuran, gain, dan jarak.
5. Rekam beberapa pengulangan per pohon. Jangan membagi potongan dari pohon yang sama ke data train dan test karena dapat menyebabkan kebocoran data.
6. Jauhkan laptop/power supply berisik dari sensor dan coba daya baterai bila noise USB dominan.

## Troubleshooting

### WAV kosong atau program menunggu terus

- Pastikan firmware baru sudah ter-upload.
- Pastikan port benar dan tidak sedang dipakai Arduino Serial Monitor.
- Tekan reset satu kali, lalu jalankan ulang `recorder.py`.
- Periksa RAK18032 benar-benar terpasang di slot IO dan `WB_IO2` aktif.

### Drop/gap bukan nol

- Gunakan kabel USB data yang pendek dan baik.
- Tutup Serial Monitor, Serial Plotter, dan program lain yang membuka port.
- Sambungkan langsung ke port komputer, bukan hub.
- Hentikan pekerjaan berat di komputer selama perekaman.

### Peak selalu nol atau sangat kecil

- Lepas daya, pasang ulang sensor, lalu kencangkan sekrupnya.
- Pastikan lubang mikrofon tidak tertutup.
- Uji dengan sumber ultrasonik yang diketahui; suara bicara bukan uji yang baik karena RAK18032 dirancang terutama untuk 20-80 kHz.
- Ingat bahwa konfigurasi ini hanya menangkap sampai sekitar 31,25 kHz.

### Clipping tinggi

Turunkan `PDM_GAIN`, upload ulang, dan rekam ulang. Data yang sudah clipping tidak dapat dipulihkan dengan software.

## Format stream untuk integrasi aplikasi lain

Setiap paket terdiri dari header little-endian 24 byte lalu 512 byte PCM:

| Offset | Tipe | Isi |
|---:|---|---|
| 0 | 4 byte | magic ASCII `SAWT` |
| 4 | uint8 | versi protokol = 1 |
| 5 | uint8 | flags, saat ini 0 |
| 6 | uint16 | ukuran header = 24 |
| 8 | uint32 | nomor urut blok |
| 12 | uint32 | sample rate = 62500 |
| 16 | uint16 | jumlah sampel = 256 |
| 18 | uint16 | nilai gain PDM |
| 20 | uint32 | total blok yang dibuang |
| 24 | int16[256] | PCM mono signed little-endian |

Kirim karakter `R` ke port untuk memulai sesi baru dan `S` untuk berhenti.

## Rujukan teknis

- RAKwireless Audio Library: <https://github.com/RAKWireless/RAKwireless-Audio-library>
- RAK nRF52 Arduino BSP: <https://github.com/RAKWireless/RAK-nRF52-Arduino>
- Dokumentasi RAK18032: <https://docs.rakwireless.com/product-categories/wisblock/rak18032/quickstart/>
