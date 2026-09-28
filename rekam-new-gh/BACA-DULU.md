# Rekam Sawit — panduan untuk operator

Aplikasi perekam suara tumbuhan sawit. Folder ini **mandiri**: tidak butuh
Arduino IDE, tidak butuh folder lain, tidak butuh internet setelah dipasang.

## Yang Anda butuh

| Kebutuhan | Keterangan |
|---|---|
| Laptop | Windows 10/11 atau Linux (Ubuntu/Debian/Fedora) |
| Alat perekam | RAK4631 + RAK19007 + RAK18032, firmware sudah terpasang |
| Kabel | USB-C ke laptop, **jangan cabut** saat merekam |
| Python 3.10+ | Hanya untuk memasang, dan hanya sekali |

## Cara pakai

### Langkah 1 — Pasang (sekali saja)

**Windows:** klik ganda `PASANG.bat`
**Linux:** buka terminal di folder ini, ketik `bash PASANG.sh`

Tunggu sampai muncul "SELESAI". Butuh koneksi internet hanya di langkah ini.

### Langkah 2 — Merekam

**Windows:** klik ganda `MULAI-rekam.bat`
**Linux:** `bash MULAI-rekam.sh`

### Langkah 3 — Mengisi isian

| Isian | Isi apa |
|---|---|
| Mode | **Data** untuk kelas seperti air-kekeringan, atau **Kontrol Sesi** untuk box kosong |
| Jenis | Kondisi yang sedang direkam |
| Plants | Nomor pot dari FP (hanya mode Data) |
| Hari ke | Hari ke-berapa pengumpulan data |
| Sesi | 1 = awal, 2 = tengah, 3 = akhir |
| Durasi | Berapa detik rekaman. Pilih dari daftar (10 sampai 600 detik) **atau ketik angka sendiri**, misalnya 45. |
| Port | Kosongkan saja, diisi otomatis |
| Operator | Nama Anda (boleh dikosongkan) |

Klik **Rekam**, lalu tunggu sampai muncul "Rekaman bersih".

## Aturan wajib saat merekam

1. **Tutup Serial Monitor** (Arduino IDE) sebelum merekam. Serial Monitor
   memakai port yang sama dan akan mengunci perekam.
2. **Jangan buka dua aplikasi** yang memakai port USB ini.
3. **Jangan cabut kabel** dan jangan sentuh laptop.
4. **Tutup box, diamkan 2 menit**, baru rekam. Ini memberi waktu mesin dan
   box akustik untuk rehat.
5. **Rekam kontrol box kosong di awal, tengah, dan akhir setiap sesi.** Tanpa
   kontrol, data Anda tidak bisa dipakai pembanding. Kalau Anda menekan Rekam
   tanpa kontrol, pilih **Rekam kontrol dulu** — aplikasinya akan membantu
   pindah mode secara otomatis.

### Soal durasi

Durasi bisa dari 10 detik sampai 10 menit, atau angka bebas yang Anda ketik.
Ingat patokannya: rekaman **10 menit** menghasilkan file sekitar **72 MB**.
Satu sesi dengan 1 tanaman + 2 kontrol jadi sekitar 215 MB. Pastikan laptop
anda masih punya ruang yang cukup sebelum memulai sesi panjang.
6. Kalau sedang mengumpulkan data kondisi Air, **pH harus dijaga Normal**.
   Kalau mengumpulkan data pH, **Air harus dijaga Normal**. Jangan dua-duanya
   berubah sekaligus.

## Kalau ada masalah

### "Alat tidak ketemu. Colok USB lalu isi Port manual."

Judul jendela: **Port**.

- Cabut-kolok kabel USB, tunggu 5 detik, kolok lagi.
- Tutup Serial Monitor dan semua jendela Arduino IDE.
- Coba port USB lain di laptop.
- Kalau tetap tidak ketemu, isi kolom **Port** manual, misalnya `COM15`
  (Windows) atau `/dev/ttyACM0` (Linux). Di Linux, cari dengan:
  `ls /dev/ttyACM*` atau `dmesg | tail`.

### "Alat tidak mengirim audio dalam batas waktu"

- Kabel USB longgar atau port bermasalah. Ganti kabel/port.
- Tutup Serial Monitor.
- Periksa mikrofon masih terpasang firmly di RAK18032.

### Popup "Belum ada kontrol"

Muncul kalau Anda menekan Rekam untuk data, tapi kontrol box kosong untuk
sesi itu belum ada. Ada tiga pilihan, dan **tidak ada tombol yang langsung
mulai merekam secara diam-diam**:

- **Rekam kontrol dulu** — mode otomatis berubah jadi Kontrol Sesi. Tinggal
  klik Rekam lagi. Ini pilihan yang disarankan.
- **Lanjut tanpa kontrol** — rekam data saja. Pilih ini hanya kalau memang
  yakin, misalnya kontrolnya sudah Anda rekam sebelumnya tapi di folder lain.
- **Batal** — tidak jadi merekam, tidak ada file yang dibuat.

Kalau Anda menutup popup dengan tanda silang (X), itu dianggap **Batal**.

### "Rekaman bermasalah" (popup muncul)

Popup selalu menampilkan **lokasi file** dan tombol **Buka folder**.

- **Penting:** file **tidak** dihapus otomatis.
- Periksa dulu kotaknya, mikrofon, atau kabel sesuai pesan di popup.
- Kalau sudah yakin masalahnya tidak akan terulang, klik tombol hapus.
- Kalau mau menyimpan file tersebut sebagai bukti, klik **Tutup**.
- **Jangan ada rekam ulang otomatis.** Bersihkan setup, diamkan 2 menit,
  lalu tekan **Rekam** sendiri.

### Popup "Rekaman putus sebelumnya" saat aplikasi dibuka

Artinya ada rekaman yang tidak selesai dari sesi sebelumnya (misalnya laptop
mati mendadak). Aplikasi menunjukkan lokasinya. Buka foldernya, putuskan mau
dihapus atau disimpan, baru mulai sesi baru.

### Rekaman terputus setelah selesai (file `.wav.partial`)

Kalau Anda menekan **Berhenti** di tengah jalan, file memang sengaja
disimpan sebagai `.wav.partial` supaya tidak ada data yang hilang diam-diam.
Tersebut file **bukan** data yang bisa dipakai.

## Ke mana hasil rekaman

Semua rekaman otomatis tersimpan di folder `data/` pada folder ini:

```
data/
  raw_audio/<jenis>/hari-<N>/       rekaman data
  controls/<jenis>/hari-<N>/        rekaman kontrol box kosong
  data/pilot_test/                  rekaman uji coba, bukan data
metadata/captures/keseluruhan.csv   daftar semua rekaman
```

Kirim **dua folder** ini kembali: `data/` dan `metadata/`. Yang wajib
`data/raw_audio/` dan `data/controls/`; `data/pilot_test/` boleh dikosongkan
atau tidak dikirim. **Jangan** mengubah nama file atau memindahkan file secara
manual — daftar di CSV harus cocok dengan file yang ada.

## Yang TIDAK boleh dilakukan

- **Jangan** mengedit firmware. Firmware sudah dikunci dan tidak boleh diubah.
- **Jangan** mengganti sample rate. Rekaman selalu 62.500 Hz (rentang 0–31,25 kHz).
- **Jangan** menyimpulkan sesuatu soal pita frekuensi tertentu dari rekaman ini.
  Belum ada kalibrasi nada ultrasonik, jadi pita analisisnya belum diketahui.
- **Jangan** menghapus file rekaman di luar aplikasi.
- **Jangan** merekam tanpa label kondisi yang jelas dari FP/atasan.
