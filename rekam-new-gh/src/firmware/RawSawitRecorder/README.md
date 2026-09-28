# Firmware lokal — RawSawitRecorder (baseline)

Baseline: salinan audit dari
`.reference-project-sawit-2/alat/kodingan_hardware/RawSawitRecorder/RawSawitRecorder.ino`
(PCM 16-bit mono 62.500 Hz, paket `SAWT` v1 24-byte, perintah `R`/`S`).
Clone referensi tidak diubah; penyempurnaan dilakukan di sini.

## File

- `RawSawitRecorder.ino` — capture PDM → USB CDC (akan refactor pakai `sawt_protocol.h`).
- `sawt_protocol.h` — konstanta paket + writer little-endian, tanpa heap di ISR.

## Build (compile-only)

```powershell
.\rekam-new\scripts\build_firmware.ps1
```

Upload tetap via Arduino IDE manual (Tools > Board RAK4631, Port COM15 `239A:8029`,
tutup Serial Monitor/Plotter, Verify lalu Upload). LED hijau menyala saat merekam.

## Aturan ubah

- Gain (`PDM_GAIN`) hanya antar-capture, catat di manifest, kunci sebelum koleksi formal.
- Jangan kirim teks serial saat capture aktif — semua byte adalah paket biner.
- Jangan naikkan clock di atas 4,8 MHz mic / klaim 80 kHz tanpa kalibrasi 20/24/28 kHz.
