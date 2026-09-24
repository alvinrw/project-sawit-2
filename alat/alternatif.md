# Alternatif Pengembangan Perekam Ultrasonik PalmSonic AI

## 1. Apa yang sedang dicoba

Proyek PalmSonic-AI mencoba merekam emisi akustik atau klik ultrasonik dari tanaman sawit, kemudian menggunakan hasil rekaman tersebut sebagai data untuk analisis sinyal dan pelatihan model kecerdasan buatan.

Target akhirnya bukan sekadar menghasilkan file audio. Sistem harus dapat:

1. merekam sampel suara mentah tanpa FFT, filter, normalisasi, atau kompresi pada alat;
2. menjaga amplitudo dan urutan waktu sampel;
3. mendeteksi bila ada data yang hilang;
4. menyimpan hasil sebagai WAV lossless;
5. membandingkan background dengan tanaman;
6. membedakan kondisi tanaman setelah tersedia data biologis yang cukup;
7. menghasilkan dataset yang dapat diuji dan direproduksi.

Tahap pertama yang sedang dilakukan sekarang adalah pilot sederhana:

- merekam acoustic box kosong;
- merekam acoustic box berisi pot dan sawit sehat;
- membandingkan spektrum, energi 20–28 kHz, dan kandidat klik;
- memastikan alat tidak menghasilkan drop, gap, atau clipping.

Pilot ini belum bertujuan membedakan sehat dan sakit. Pilot hanya menjawab pertanyaan awal: **apakah rekaman box berisi sawit mempunyai pola yang berbeda dari noise dasar box kosong?**

## 2. Kondisi hardware saat ini

Hardware yang tersedia adalah:

- RAK18032 sebagai mikrofon PDM ultrasonik;
- RAK4631 dengan mikrokontroler nRF52840 sebagai core;
- RAK19007 sebagai base board;
- USB sebagai jalur pengiriman data ke komputer.

RAK18032 menggunakan mikrofon SPH0655LM4H-1. Berdasarkan spesifikasi pada manual alat, bagian mikrofonnya mempunyai respons ultrasonik sekitar 20–80 kHz dan menerima clock PDM hingga sekitar 4,8 MHz.

Dengan kata lain, **mikrofonnya memang dirancang untuk ultrasonik**. Masalah utama bukan karena RAK18032 hanya mikrofon suara manusia.

## 3. Letak masalah sebenarnya

Mikrofon PDM tidak langsung mengeluarkan angka PCM seperti isi WAV. Mikrofon mengeluarkan aliran bit PDM yang sangat cepat. Core harus memberi clock kepada mikrofon, membaca bit tersebut, lalu melakukan filter dan desimasi untuk menghasilkan PCM.

Jalur PDM bawaan RAK4631 memakai rasio desimasi tertentu. Firmware stabil saat ini menggunakan:

- clock PDM: sekitar 4 MHz;
- rasio desimasi: 64;
- hasil PCM: 4.000.000 / 64 = 62.500 sampel/detik;
- batas Nyquist: 62.500 / 2 = 31.250 Hz.

Karena filter membutuhkan jarak dari batas Nyquist, rentang analisis konservatifnya sekitar 20–28 kHz.

Jadi kondisinya adalah:

> Mikrofon secara fisik mampu merespons sampai sekitar 80 kHz, tetapi converter PDM bawaan RAK4631 hanya menghasilkan PCM yang aman sampai sekitar 31,25 kHz.

Ini seperti kamera yang sensornya mampu melihat gerakan cepat, tetapi perekamnya hanya mengambil sedikit frame per detik. Kemampuan sensor tidak seluruhnya masuk ke file.

## 4. Mengapa sample rate tidak boleh sekadar dinaikkan

Untuk menyimpan frekuensi 80 kHz, sample rate PCM harus lebih dari dua kali frekuensi tersebut:

```text
sample rate minimum = 2 × 80 kHz = 160 kS/s
```

Dalam praktiknya lebih aman memakai 192 atau 200 kS/s agar filter anti-alias memiliki ruang.

Library RAK untuk nRF52840 memang mempunyai nama mode `PCM_100000` dan `PCM_200000`. Namun implementasinya menaikkan clock PDM menjadi sekitar 8 MHz dan 16 MHz. Angka tersebut melebihi batas clock mikrofon sekitar 4,8 MHz.

Jika mode tersebut dipaksakan:

- WAV mungkin tetap terbentuk;
- angka sample rate mungkin tertulis 100 atau 200 kHz;
- mikrofon bekerja di luar spesifikasi;
- noise dan respons frekuensi tidak dapat dipercaya;
- frekuensi yang terukur dapat salah;
- model AI berisiko mempelajari artefak alat.

Karena itu firmware stabil tidak menggunakan mode tersebut.

## 5. Status firmware yang tersedia

Firmware `RawSawitRecorder` saat ini sudah benar untuk fungsi berikut:

- PCM raw signed 16-bit;
- mono;
- 62.500 sampel/detik;
- tanpa FFT;
- tanpa filter software;
- tanpa normalisasi;
- tanpa kompresi;
- stream biner yang lebih efisien daripada teks;
- nomor urut blok dan penghitung data yang hilang;
- penyimpanan WAV melalui `recorder.py`;
- pemeriksaan peak, clipping, drop, dan gap.

Firmware ini dapat dipakai untuk pilot eksperimental 20–28 kHz. Mode 4 MHz berasal dari BSP khusus RAK dan perlu diverifikasi dengan sumber nada ultrasonik yang diketahui sebelum ketepatan frekuensinya dijadikan dasar klaim ilmiah. Firmware ini belum dapat digunakan untuk menyatakan bahwa seluruh rentang 20–80 kHz sudah direkam.

## 6. Semua opsi yang realistis

### Opsi A — Uji alat sekarang pada 20–28 kHz

Tetap gunakan RAK4631, RAK18032, firmware saat ini, dan folder `testing`.

Langkahnya:

1. rekam box kosong;
2. rekam box berisi pot dan sawit sehat;
3. jalankan `testing/bandingkan_rekaman.py`;
4. periksa drop, gap, clipping, spektrum, dan kandidat event;
5. ulangi beberapa kali sebelum mengambil keputusan.

**Kelebihan:** tidak perlu membeli hardware, dapat dilakukan sekarang, dan cukup untuk membuktikan pipeline raw bekerja.

**Kekurangan:** hanya menguji bagian bawah wilayah ultrasonik. Sinyal di atas sekitar 31 kHz tidak tercatat.

**Kapan dipilih:** selalu dilakukan terlebih dahulu, bahkan jika nantinya hardware diganti. Hasilnya menjadi baseline sistem.

### Opsi B — Tetap memakai RAK4631 tetapi menangkap PDM mentah

Converter PDM bawaan tidak digunakan. RAK4631 diprogram untuk:

1. menghasilkan clock kontinu sekitar 4 MHz;
2. membaca setiap bit PDM mentah;
3. mengemas delapan bit PDM menjadi satu byte;
4. menyimpan ke buffer DMA;
5. mengirim data mentah melalui USB;
6. membiarkan komputer melakukan low-pass filter dan desimasi;
7. menghasilkan WAV PCM sekitar 200 kS/s.

Perkiraan aliran datanya:

```text
4.000.000 bit/detik ÷ 8 = sekitar 500.000 byte/detik
```

**Kelebihan:** mempertahankan semua hardware yang ada dan clock mikrofon tetap aman.

**Kekurangan:** driver sangat khusus, kontinuitas clock harus dijaga, USB dan DMA harus stabil, filter PDM-ke-PCM harus dibuat dan divalidasi, serta implementasinya tidak lagi memakai driver audio standar.

**Risiko:** secara teori memungkinkan, tetapi keberhasilannya baru dapat dibuktikan setelah implementasi dan pengujian fisik menggunakan sumber ultrasonik yang diketahui.

**Kapan dipilih:** ketika anggaran tidak memungkinkan penggantian core dan tersedia waktu untuk penelitian driver tingkat rendah.

### Opsi C — Ganti core ke ESP32-S3 dan pertahankan RAK18032

ESP32-S3 mendukung PDM RX dalam format mentah pada clock beberapa MHz dan mempunyai native USB Full-Speed. Alurnya:

```text
RAK18032
→ raw PDM sekitar 4–4,8 MHz
→ ESP32-S3 + DMA
→ USB ke komputer
→ filter/desimasi di komputer
→ PCM 192/200 kS/s
→ WAV
```

Dalam ekosistem WisBlock, kandidat yang perlu diperiksa adalah core RAK berbasis ESP32-S3 seperti RAK3112/RAK3312. Dukungan audio untuk core tersebut sudah mulai tersedia dalam RAKwireless Audio Library terbaru, tetapi mode khusus 200 kS/s tetap memerlukan firmware raw PDM sendiri.

**Kelebihan:** raw PDM dan USB didukung lebih alami, kemampuan transfer cukup, RAK18032 dapat tetap digunakan, dan pengembangan lebih masuk akal daripada memaksa converter RAK4631.

**Kekurangan:** perlu membeli core baru, memastikan pin RAK18032 dan native USB terhubung dengan benar pada base board, serta menulis firmware ESP-IDF/Arduino yang lebih khusus.

**Risiko:** bukan plug-and-play. Keberhasilan tetap harus diverifikasi menggunakan sinyal 20, 40, 60, dan 80 kHz.

**Kapan dipilih:** pilihan utama jika target penelitian wajib mencakup seluruh wilayah hingga 80 kHz tetapi tetap ingin mempertahankan mikrofon RAK18032.

### Opsi D — Ganti core ke RP2040 dan gunakan PIO serta DMA

Core berbasis RP2040 dapat memakai PIO untuk menghasilkan clock dan menangkap bit PDM dengan timing yang fleksibel. Data disimpan melalui DMA, kemudian dikirim lewat USB atau SD.

**Kelebihan:** PIO cocok untuk protokol bitstream khusus dan kontrol timing sangat fleksibel.

**Kekurangan:** membutuhkan driver PIO, manajemen DMA, konversi PDM-ke-PCM, dan validasi yang sama ketatnya.

**Kapan dipilih:** bila pengembang lebih menguasai RP2040/PIO daripada ESP-IDF.

### Opsi E — RAK11200 atau ESP32 lama dengan penyimpanan SD/Wi-Fi

Core ESP32 lama dapat dipakai untuk eksperimen raw PDM, tetapi jalur USB-nya tidak sepraktis ESP32-S3. Data berkecepatan tinggi lebih aman disimpan ke SD atau dikirim melalui Wi-Fi.

Konfigurasi WisBlock dapat memerlukan:

- RAK11200;
- RAK18032;
- modul SD RAK15002;
- firmware raw PDM;
- konversi offline di komputer.

**Kelebihan:** masih berada dalam ekosistem WisBlock dan RAK menyediakan contoh perekaman berbasis SD untuk RAK11200.

**Kekurangan:** lebih banyak modul, penyimpanan harus mampu menulis kontinu, raw PDM tetap membutuhkan kode khusus, dan tidak sesederhana ESP32-S3 dengan native USB.

**Kapan dipilih:** jika RAK11200 dan modul SD sudah tersedia sehingga biaya tambahan rendah.

### Opsi F — Gunakan ultrasonic microphone/recorder komersial

Gunakan perangkat yang dari awal menyediakan:

- sample rate minimal 192 kS/s, lebih baik 250/384 kS/s;
- respons mikrofon yang dikalibrasi sampai minimal 80 kHz;
- driver USB atau penyimpanan internal;
- dokumentasi noise floor dan sensitivitas.

**Kelebihan:** jalur paling cepat dan paling mudah dipertanggungjawabkan secara ilmiah.

**Kekurangan:** harga dapat jauh lebih tinggi dan integrasi dengan WisBlock berkurang.

**Kapan dipilih:** jika prioritas utama adalah kualitas dataset dan waktu penelitian lebih berharga daripada pengembangan elektronik.

### Opsi G — Gunakan contact acoustic-emission sensor dan high-speed ADC

Sensor piezoelectric ditempelkan langsung ke batang untuk menangkap emisi akustik yang merambat melalui jaringan tanaman. Sistem ini berbeda dari mikrofon udara RAK18032.

Perangkat yang dibutuhkan umumnya mencakup:

- sensor AE/piezo broadband;
- couplant dan clamp yang konsisten;
- preamplifier;
- high-speed ADC;
- sistem trigger dan akuisisi.

**Kelebihan:** lebih sensitif terhadap emisi yang merambat di batang dan banyak dipakai untuk penelitian kavitasi xilem.

**Kekurangan:** metodologinya berbeda, pemasangan lebih invasif, harga lebih tinggi, dan hasil tidak dapat langsung dibandingkan dengan mikrofon udara.

**Kapan dipilih:** ketika fokus utama adalah kavitasi/xilem, bukan airborne ultrasonic clicks.

### Opsi H — Batasi klaim penelitian pada 20–28 kHz

Tetap gunakan hardware saat ini dan ubah ruang lingkup penelitian menjadi deteksi sinyal pada pita 20–28 kHz.

**Kelebihan:** paling murah, sistem sudah tersedia, dan dataset dapat segera dibuat setelah pilot lolos.

**Kekurangan:** tidak boleh mengklaim pengukuran penuh 20–80 kHz dan mungkin melewatkan emisi utama tanaman.

**Kapan dipilih:** ketika pilot menunjukkan perbedaan kuat dan konsisten pada pita tersebut.

## 7. Matriks keputusan

| Opsi | Hardware baru | Kesulitan kode | Dapat menargetkan 80 kHz | RAK18032 tetap dipakai | Tingkat keyakinan sebelum validasi |
|---|---:|---:|---:|---:|---|
| A. Pilot RAK4631 saat ini | Tidak | Rendah | Tidak | Ya | Tinggi untuk 20–28 kHz |
| B. Raw PDM RAK4631 | Tidak | Sangat tinggi | Secara teori ya | Ya | Eksperimental |
| C. ESP32-S3 raw PDM | Core baru | Tinggi | Ya | Ya | Paling menjanjikan untuk DIY |
| D. RP2040 PIO raw PDM | Core baru | Sangat tinggi | Ya | Ya | Eksperimental tetapi fleksibel |
| E. RAK11200 + SD/Wi-Fi | Core + mungkin SD | Tinggi | Secara teori ya | Ya | Menengah |
| F. Recorder ultrasonik komersial | Ya | Rendah | Ya | Tidak harus | Tertinggi |
| G. Contact AE + high-speed ADC | Ya | Tinggi | Ya | Tidak | Tinggi untuk contact AE |
| H. Batasi studi 20–28 kHz | Tidak | Rendah | Tidak | Ya | Tinggi bila pilot positif |

## 8. Rekomendasi utama

Urutan yang paling masuk akal adalah:

1. **Selesaikan pilot dengan firmware sekarang.** Jangan membeli atau mengganti hardware sebelum mengetahui noise floor, clipping, dan apakah ada perbedaan box kosong dengan sawit sehat.
2. **Uji dengan sumber ultrasonik yang diketahui pada 20–30 kHz.** Ini memastikan sample rate, frekuensi, dan respons alat tidak hanya terlihat benar di software.
3. **Jika pita 20–28 kHz sudah informatif**, lanjutkan pilot biologis lebih besar atau gunakan Opsi H dengan batas klaim yang jujur.
4. **Jika hasilnya tidak berbeda atau dugaan sinyal berada di atas 31 kHz**, pilih Opsi C: ESP32-S3 raw PDM dengan target WAV 192/200 kS/s.
5. **Jika tenggat penelitian pendek dan anggaran tersedia**, pertimbangkan Opsi F karena lebih cepat divalidasi daripada membuat driver baru.

Rekomendasi teknis untuk pengembangan DIY penuh adalah:

> Pertahankan RAK18032, ganti core ke ESP32-S3 yang mempunyai native USB, tangkap PDM mentah pada clock maksimal 4–4,8 MHz, lakukan filter/desimasi di komputer, dan hasilkan WAV PCM 192/200 kS/s.

## 9. Tahap validasi jika memakai sistem 192/200 kS/s

Sistem baru belum boleh digunakan untuk dataset tanaman sebelum melewati pengujian berikut:

1. rekam sumber 20 kHz dan pastikan puncaknya muncul di 20 kHz;
2. ulangi pada 40, 60, dan 80 kHz;
3. periksa apakah muncul alias atau frekuensi bayangan;
4. ukur noise floor pada acoustic box kosong;
5. periksa clipping pada beberapa gain;
6. pastikan tidak ada blok hilang;
7. rekam minimal 10 menit untuk menguji stabilitas;
8. simpan sample rate, clock, gain, firmware version, dan checksum;
9. bandingkan hasil dengan alat referensi bila tersedia;
10. kunci firmware sebelum pengambilan dataset utama.

## 10. Kriteria keputusan setelah pilot saat ini

### Lanjut memakai RAK4631 bila

- `drop alat = 0` dan `gap = 0`;
- clipping mendekati 0%;
- uji sumber ultrasonik 20–30 kHz terbaca pada frekuensi yang benar;
- perbedaan sawit dan box kosong konsisten pada beberapa pengulangan;
- penelitian bersedia membatasi klaim pada pita sekitar 20–28 kHz.

### Beralih ke sistem full-band bila

- tidak ada sinyal informatif pada 20–28 kHz;
- literatur atau pengujian referensi menunjukkan sinyal utama berada sekitar 40–80 kHz;
- tujuan penelitian secara eksplisit membutuhkan keseluruhan respons RAK18032;
- hasil akan digunakan untuk klaim ilmiah yang membutuhkan frekuensi di atas 31 kHz.

### Jangan melanjutkan dataset utama bila

- sample rate belum terverifikasi;
- sumber ultrasonik yang diketahui muncul pada frekuensi yang salah;
- terdapat drop/gap;
- clipping tinggi;
- noise box berubah tanpa kontrol;
- metadata dan identitas tanaman belum konsisten.

## 11. Rujukan teknis

- RAKwireless Audio Library: <https://github.com/RAKWireless/RAKwireless-Audio-library>
- RAK nRF52 Arduino BSP: <https://github.com/RAKWireless/RAK-nRF52-Arduino>
- ESP32-S3 PDM RX: <https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/peripherals/i2s.html>
- ESP32-S3 USB Device: <https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_device.html>
- RAK18032 documentation: <https://docs.rakwireless.com/product-categories/wisblock/rak18032/quickstart/>

## 12. Kesimpulan

RAK18032 bukan bagian yang paling bermasalah. Mikrofon tersebut memang dibuat untuk ultrasonik. Hambatan saat ini berada pada jalur konversi PDM bawaan RAK4631 yang hanya menghasilkan PCM aman 62,5 kS/s atau bandwidth sekitar 31,25 kHz.

Firmware saat ini tetap berguna dan harus diuji terlebih dahulu. Untuk merekam penuh sampai 80 kHz, solusi yang paling masuk akal adalah menangkap PDM mentah dengan core yang lebih cocok—terutama ESP32-S3—kemudian melakukan konversi menjadi PCM 192/200 kS/s di komputer. Menaikkan mode PDM RAK4631 ke 100/200 kS/s tanpa mengganti metode akuisisi bukan solusi yang dapat dipercaya.
