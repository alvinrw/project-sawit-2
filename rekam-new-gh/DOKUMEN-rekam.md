# rekam.py — Dokumen Pemakaian (petunjuk project rekaman)

> **Untuk operator (teman/kolektor):** baca `BACA-DULU.md` di folder ini.
> Dokumen ini untuk researcher/pengawal rekaman.

Jalan: klik `MULAI-rekam.bat` (Windows) atau `bash MULAI-rekam.sh` (Linux).
Tanpa `.venv`, jalankan langsung `python rekam-new/scripts/rekam.py`.

> **Scope aktif:** folder ini hanya untuk merekam raw WAV, kontrol sesi, dan
> pencatatan rekaman. Model ML, fitur, training, split, evaluasi, dan prediksi
> dibangun terpisah **setelah seluruh rekaman selesai**; jangan memulai pekerjaan
> ML dari dokumen atau folder ini kecuali user secara eksplisit memulai fase ML.

## Kosong vs kontrol (beda, jangan ketukar)
- Jenis `kosong` = koleksi data box kosong sebagai kelas dataset
  (di `data/raw_audio/kosong/`). Tetap direkam seperti jenis lain.
- Kontrol = SELALU box kosong tanpa tanaman/pot, direkam sebagai patokan
  sesi berjalan (di `data/controls/<jenis>/hari-N/`). Tidak pernah masuk
  data latih.

## Mode Data (kumpulin suara per jenis)
Isi: Jenis (6 pilihan) + Plants (angka) + Hari ke (angka) + Sesi (1/2/3) +
Durasi (pilih 10/15/20/25/30/60/120/300/600 detik, **atau ketik angka bebas**
misal 45) + Port (auto-isi saat tombol ditekan) + Operator (opsional).
Tekan Rekam. Durasi selalu dicatat dalam detik, termasuk di nama file
(`..._600s_...`), supaya nama file tetap urut dan tidak ambigu.
Status yang ditampilkan ke operator memakai satuan manusia (60 → "1 menit",
600 → "10 menit").
File data: `rekam-new/data/raw_audio/<jenis>/hari-<N>/<jenis>_P<plant>_hari<N>_sesi<M>_<dur>s_<stamp>.wav`
Contoh: `air-kekeringan_P1_hari1_sesi1_20s_20260927_093000.wav`
Kalau plant+hari+sesi itu sudah ada file: muncul peringatan, boleh lanjut
(pengulangan itu sah) atau batal.

## Kontrol yang belum ada (popup tiga pilihan)
Saat Mode Data ditekan tapi kontrol box kosong untuk kategori+hari+sesi itu
belum ada, aplikasi menampilkan popup dengan tiga tombol eksplisit:
**Rekam kontrol dulu** (disarankan), **Batal**, dan
**Lanjut tanpa kontrol**. Tidak ada tombol yang langsung mulai merekam
diam-diam; menutup popup dengan X diperlakukan sebagai Batal dan tidak
membuat file. Memilih "Rekam kontrol dulu" memindahkan mode ke Kontrol Sesi
sambil mempertahankan Jenis, Hari, Sesi, dan Durasi, lalu menunggu operator
menekan Rekam. Alasan kenapa: kontrol kosong adalah pembanding QC; rekaman
tanpa kontrol jadi sulit dipakai saat analisis nanti.

## Mode Kontrol Sesi (patokan, bukan data latih)
Pilih mode Kontrol Sesi: Plants disembunyikan, Jenis tetap dipilih (kontrol
milik kategori itu). Isi Hari + Sesi + Durasi.
Kontrol ikut sesi: 1=awal, 2=tengah, 3=akhir.
File: `rekam-new/data/controls/<jenis>/hari-<N>/kontrol-sesi<M>_hari<N>_<dur>s_<stamp>.wav`
Hari ganti tapi kontrol sesi itu belum ada: warning, boleh lanjut.
Kalau sesi menunjukkan masalah rekaman, hentikan dulu dan periksa setup.
Jangan langsung rekam ulang saat box/mikrofon/pot masih dibersihkan.

## Aturan sesi (wajib)
Tanpa alas seragam, tutup box + diamkan 2 menit, laptop/kabel jangan disentuh.
Durasi default 20 detik (sementara, **belum dikunci**). Operator boleh memilih
sampai 600 detik atau mengetik angka bebas. Batas durasi hanya dibatasi kode,
bukan pilot: yang sudah diverifikasi sungguhan hanya rekam **60 detik** (tepat
60,000000 detik, 3.750.000 frame, drop 0, gap 0, tanpa drift DC). Durasi
lebih dari itu belum diuji, jadi Operator bertanggung jawab memastikan ruang
disk dan laptop tidak tidur selama rekaman panjang.
Sample rate rekam dikunci 62.500 Hz,
jadi rentang tersimpan adalah 0–31,25 kHz. **Pita analisis belum ditentukan**:
kalibrasi nada ultrasonik belum dilakukan, jadi jangan pakai hasil rekaman ini
untuk menyimpulkan apa pun soal pita frekuensi tertentu.
Kondisi tiap pot dari FP/atasan — tanpa label mereka = latihan, bukan latih.

## Tombol alat
Folder ini hanya untuk merekam. **Tidak ada tombol upload firmware dan tidak
ada tombol cek alat**: firmware baseline dikunci dan tidak boleh diubah dari
aplikasi ini. Folder `rekam-new/` berjalan mandiri — tidak butuh Arduino IDE
maupun clone repositori referensi. Protokol SAWT v1 ada di
`rekam-new/scripts/sawt_protocol.py` dan `sawt_protocol.h` di sisi firmware.

- Hanya ada tiga tombol: **Rekam**, **Berhenti**, **Buka folder hasil**.
- Saat rekam berjalan, tombol Rekam nonaktif dan hanya Berhenti yang hidup,
  agar port tidak dipakai dua proses. Saat popup keputusan terbuka, keduanya
  nonaktif.
- Buka folder hasil memakai file manager sistem, jalan di Windows, macOS, dan
  Linux.
- Berhenti atau tutup aplikasi saat rekam: program menghentikan alat lebih dulu.
  Rekaman yang belum selesai menjadi file `.wav.partial` di folder hasilnya.
- Bila alat tidak mengirim audio selama 5 detik saat mulai atau di tengah rekam,
  program berhenti dan menampilkan lokasi partial serta arahan pemeriksaan.
- Kontrol duplikat (sesi+hari sama) ikut warning seperti data.

## Jaminan tiap rekaman
Tidak pernah overwrite (tabrakan nama = ditolak). Rekaman bersih menjadi
`.wav`; rekaman putus tetap sebagai `.wav.partial` di folder yang sama.
Tiap rekaman selesai/gagal yang ditangani operator menambah 1 baris
di `rekam-new/metadata/captures/keseluruhan.csv` (SATU master, tidak dipecah):
waktu, mode, jenis, plant,
hari, sesi, posisi, durasi, file, sha256, sampel, peak, gain, clip%, drop, gap, operator, box,
status (bersih / gagal-dihapus / gagal-dibiarkan / putus-dihapus / putus-dibiarkan,
beserta alasan). Gain TEREKAM per file;
berubah tengah jalan = error + file ditolak.
Peringatan otomatis: blok hilang (drop/gap) atau clipping >0,01% → popup
menampilkan path file, tombol Buka folder, serta tombol hapus hanya setelah
operator menyatakan setup sudah dibersihkan. Tidak ada rekam ulang otomatis:
bersihkan setup, tutup box, diamkan 2 menit, lalu tekan Rekam sendiri.
Drop/gap: cek kabel USB/port/Serial Monitor. Clipping/sinyal aneh: cek
mikrofon, box, pot/tanaman, dan benda asing seperti serangga.
Saat aplikasi dibuka, `.wav.partial` lama hanya diberi peringatan lengkap
dengan path dan pilihan Buka folder/Hapus/Tutup; file tidak dihapus otomatis
dan peringatan tidak memblokir rekaman baru. Partial sisa crash sebelumnya
belum pernah punya baris CSV, jadi jejaknya adalah peringatan startup ini —
sebab itu jangan dihapus diam-diam di luar aplikasi.
Bila CSV gagal ditulis, aplikasi menampilkan popup "Gagal menulis CSV" berisi
path dan status yang seharusnya tercatat; status di file tetap kosong dan
tidak boleh dianggap sah sampai dicatat manual.
Firmware tetap baseline 62.500 Hz — rekam.py tidak mengubah kodingan alat.
Monitor live update 0,5 detik: angka (peak kini/maks, clipping %, gain,
drop, gap) + peak bar. Satu-satunya perekam: `rekam-new/scripts/rekam.py`.
Folder ini hanya untuk rekaman; pekerjaan model ML dikerjakan terpisah setelah
rekaman selesai.
