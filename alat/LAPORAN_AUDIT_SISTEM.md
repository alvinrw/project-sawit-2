# Laporan Audit PalmSonic

Tanggal audit: 24 September 2026

## Kesimpulan utama

Kesalahan label terbalik berasal dari algoritme deteksi lama, bukan karena data
kosong dan tanaman tertukar di firmware. Model lama membandingkan energi absolut
pada empat pita frekuensi. Level rekaman pada sesi baru berubah sangat besar,
sehingga perubahan lingkungan, posisi, resonansi box, atau noise elektronik
lebih dominan daripada perbedaan isi box.

Detektor sudah diubah untuk membandingkan **kontras spektrum relatif 24-26 kHz
terhadap 20-22 kHz**, bukan volume absolut. Kalibrasi juga sekarang
menyeimbangkan setiap sesi/file agar rekaman yang lebih panjang tidak
mendominasi model. Rekaman referensi dan percobaan baru sekarang kembali
dikenali sesuai kelasnya.

## Bukti penyebab kesalahan

Median energi pita 20-22, 22-24, 24-26, dan 26-28 kHz menunjukkan perubahan
level besar antarhari:

| Rekaman | Label sebenarnya | Median energi empat pita (dBFS) |
|---|---|---|
| `Kosong.wav` | kosong | -66,44; -77,09; -67,03; -79,42 |
| `sawit.wav` | tanaman | -64,09; -77,27; -63,27; -75,83 |
| `kosong_02.wav` | kosong | -49,59; -62,92; -52,64; -69,18 |
| `sawit_02.wav` | tanaman | -71,41; -77,07; -63,03; -76,62 |

Pada pasangan pertama tanaman lebih keras daripada kosong, sedangkan pada
pasangan kedua kondisi kosong jauh lebih keras. Karena itu volume absolut tidak
boleh dijadikan penentu isi box.

Salah satu bentuk spektrum yang konsisten pada data saat ini adalah selisih
energi 24-26 kHz terhadap 20-22 kHz:

| Rekaman | Selisih relatif |
|---|---:|
| kosong lama | -0,57 dB |
| kosong baru | -3,08 dB |
| tanaman lama | +0,84 dB |
| tanaman baru | +8,41 dB |

Ini adalah pola empiris alat/box saat ini, bukan bukti bahwa tanaman secara
biologis menghasilkan frekuensi tertentu.

## Perubahan yang dilakukan

### Detektor real-time

- Menghapus ketergantungan pada level suara absolut.
- Menggunakan kontras relatif 24-26 kHz terhadap 20-22 kHz. Batas saat ini
  0,00 dB: negatif diklasifikasikan kosong dan positif tanaman.
- Menyeimbangkan pusat kelas berdasarkan median setiap sesi/file.
- Menambahkan validasi leave-one-session-out.
- Keputusan tetap biner: `KOSONG` atau `ADA TANAMAN`.
- Menambahkan kualitas `SEMENTARA`, `BAIK`, atau `LEMAH`. Label `LEMAH` jangan
  dipakai sebagai kebenaran data.
- Port otomatis dibatasi ke USB VID RAK/Adafruit agar Bluetooth COM tidak
  terpilih tanpa sengaja.
- Kode panjang sudah dipisah ke paket `testing/realtime_detector/`; launcher
  `deteksi_realtime.py` kini hanya delapan baris.
- `cek_isi_box.py` lama dihapus karena fungsinya sudah disatukan ke GUI.

### Data kalibrasi

Dua rekaman real-time yang sudah diketahui kondisi sebenarnya dipindahkan ke
folder referensi yang benar:

- `realtime_koson.wav` menjadi `kosong/kosong_02.wav`;
- `realtime_adaisinya.wav` menjadi `sawit_sehat/sawit_02.wav`.

Kalibrasi sekarang terdiri dari 2 WAV kosong (30 segmen) dan 2 WAV tanaman
(26 segmen). Validasi lintas sesi pada data yang sangat kecil ini menghasilkan
100%. Angka tersebut hanya membuktikan perbaikan bekerja pada empat sesi yang
tersedia; **bukan** estimasi akurasi lapangan.

### Firmware dan perekaman

- Data tetap raw PCM signed 16-bit, mono, 62.500 sampel/detik.
- Tidak ada FFT, normalisasi, filter software tambahan, atau kompresi di
  firmware. Raw PCM bukan raw PDM; peripheral nRF52840 tetap melakukan
  filter/desimasi PDM-ke-PCM yang wajib untuk membentuk sampel audio.
- Nomor urut paket, drop alat, dan gap USB tetap diperiksa.
- Ring buffer dinaikkan dari 16 menjadi 64 blok, sekitar 262 ms, agar lebih tahan
  terhadap jeda singkat USB/Windows.
- Gain 80 dipertahankan. Rekaman menunjukkan clipping sekitar 0,0001-0,0003%,
  terutama transien awal, sehingga tidak ada bukti gain menyebabkan label
  terbalik. Turunkan gain hanya bila clipping berulang melebihi 0,01%.

Firmware baru sudah berhasil dikompilasi untuk RAK4631: flash 66.272 byte (8%)
dan RAM 48.672 byte (20%). Firmware belum diunggah otomatis ke alat; upload
ulang diperlukan agar buffer 64 blok aktif.

## Audit kemampuan frekuensi hardware

RAK18032 memang menggunakan mikrofon ultrasonik dengan klaim respons sekitar
20-80 kHz. Namun file PCM saat ini hanya 62,5 kS/s, sehingga batas Nyquist-nya
31,25 kHz dan analisis dibatasi secara konservatif ke 20-28 kHz. Sistem ini
tidak merekam penuh sampai 80 kHz.

Mode sekitar 4 MHz yang digunakan berasal dari modifikasi high-rate pada BSP
RAK. Pilihan clock publik pada spesifikasi nRF52840 tidak mencantumkan 4 MHz.
Karena itu sistem dapat dipakai untuk eksperimen, tetapi skala frekuensi dan
respons amplitudonya wajib diuji memakai sumber ultrasonik dengan frekuensi
yang diketahui sebelum dipakai untuk klaim ilmiah.

## Hasil verifikasi perangkat lunak

- Empat sesi referensi dikenali sesuai kelas dan berkualitas `BAIK`.
- Empat percobaan baru yang tidak menjadi data kalibrasi juga benar:
  `realtime_kosong.wav` menjadi `KOSONG`, sedangkan `realtime_ada.wav`,
  `realtime_ada1.wav`, dan `realtime_ada3.wav` menjadi `ADA TANAMAN`.
- Perubahan level seragam +20 dB tidak mengubah label.
- Parser paket biner lulus pengujian.
- Validasi lintas sesi lulus.
- Total: 5 pengujian otomatis lulus.
- Firmware RAK4631 berhasil dikompilasi tanpa error.
- COM11 berhasil dibuka setelah GUI lama ditutup. Firmware mengirim header
  `SAWT`, 62.500 sampel/detik, 256 sampel/blok, gain 80, dan drop 0.

### Temuan percobaan lanjutan

Dua rekaman baru tanpa label pada nama file, `realtime_20260924_174035.wav` dan
`realtime_20260924_174135.wav`, mempunyai kontras relatif masing-masing sekitar
+2,16 dB dan +7,35 dB sehingga detektor memberi label `ADA TANAMAN`. Jika kedua
rekaman tersebut sebenarnya dibuat saat box kosong, maka distribusi kosong dan
tanaman sudah saling tumpang-tindih. Dalam kondisi itu ambang sederhana tidak
dapat memberikan klasifikasi yang sah; dataset multi-sesi berlabel dan kontrol
eksperimen harus dibuat sebelum model dilatih. Kedua file ini tidak dimasukkan
ke kalibrasi karena label sebenarnya belum dicatat pada nama/foldernya.

## Prosedur uji berikutnya yang wajib

1. Upload firmware terbaru, lalu pastikan `drop 0`, `gap 0`, dan clipping di
   bawah 0,01%.
2. Kunci posisi sensor, kabel, box, laptop, dan sumber daya. Jangan memegang box
   ketika merekam.
3. Setelah memasukkan atau mengeluarkan pot, tunggu 2-5 menit.
4. Tambahkan kelas kontrol **pot + tanah tanpa tanaman**. Tanpa kontrol ini,
   sistem hanya membedakan perubahan isi/resonansi box, bukan keberadaan tanaman.
5. Rekam sedikitnya 10 sesi independen untuk setiap kelas, masing-masing
   60-240 detik, pada waktu atau hari berbeda.
6. Acak atau selang-seling urutan, misalnya kosong, pot, tanaman, lalu ulangi.
   Jangan selalu merekam semua kosong terlebih dahulu.
7. Simpan sesi uji di folder terpisah dan jangan memasukkannya ke folder
   kalibrasi sebelum akurasi dihitung. Ini mencegah kebocoran data.
8. Uji nada yang diketahui, misalnya 20, 24, dan 28 kHz. Lebih baik bandingkan
   dengan perekam ultrasonik referensi.

Untuk penelitian selanjutnya, klasifikasi “sehat/sakit” harus dibagi berdasarkan
identitas tanaman, bukan potongan audio. Semua potongan dari satu tanaman hanya
boleh berada pada train atau test, tidak keduanya.

## Cara menjalankan

Tutup Arduino Serial Monitor, Serial Plotter, dan GUI recorder lain. Dari folder
`testing`, klik `Buka_Deteksi_Realtime.bat` atau jalankan:

```powershell
python .\deteksi_realtime.py
```

Untuk mengaktifkan buffer firmware baru, buka
`kodingan_hardware/RawSawitRecorder/RawSawitRecorder.ino` di Arduino IDE, pilih
board RAK4631 dan port alat, klik Verify, lalu Upload.

## Rujukan teknis

- RAKwireless Audio Library: <https://github.com/RAKWireless/RAKwireless-Audio-library>
- RAK nRF52 Arduino BSP: <https://github.com/RAKWireless/RAK-nRF52-Arduino>
- Nordic nRF52840 Product Specification:
  <https://docs-be.nordicsemi.com/bundle/nRF52840_PS_v1.8/raw/resource/enus/nRF52840_PS_v1.8.pdf>
- Dokumentasi RAK18032:
  <https://docs.rakwireless.com/product-categories/wisblock/rak18032/quickstart/>
