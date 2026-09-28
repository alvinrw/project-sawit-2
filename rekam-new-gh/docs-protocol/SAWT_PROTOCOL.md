# SAWT_PROTOCOL (draf — dikunci sebelum kode v2 ditulis)

Baseline v1 dari referensi (`RawSawitRecorder.ino:193-215`, `recorder.py:24-85`):
magic `SAWT`, version 1, flags 0, header 24, seq u32, rate u32 = 62500,
count u16 = 256, gain u16, dropped u32, lalu PCM int16[256] little-endian.

v2 (rencana, belum frozen): tambah version/flags/header-len eksplisit,
sample-rate/count/gain per frame, device dropped total, cumulative samples u64,
device tick u32 (wrapping), CRC32 header+payload, terminal frame zero-sample
setelah drain. Byte layout final + CRC coverage + flag + endian + urutan
terminal dikunci di sini dulu sebelum firmware/host ditulis.
