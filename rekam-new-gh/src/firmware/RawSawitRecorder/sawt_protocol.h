#pragma once
// sawt_protocol.h — definisi paket SAWT v1 (baseline audit) untuk firmware lokal.
// Baseline dari `.reference-project-sawit-2/alat/kodingan_hardware/RawSawitRecorder/RawSawitRecorder.ino:193-215`.
// File ini akan disempurnakan ke SAWT v2 (CRC, seq wrap, terminal frame) setelah
// `docs/protocol/SAWT_PROTOCOL.md` dikunci. Jangan ubah konstanta di sini
// tanpa update doc + test parser host.

#include <stdint.h>
#include <stddef.h>

static const uint32_t SAWT_SAMPLE_RATE_HZ = 62500;
static const uint16_t SAWT_SAMPLES_PER_BLOCK = 256; // = BUFFER_SIZE RAK4631
static const uint8_t SAWT_CHANNELS = 1;
static const uint8_t SAWT_PDM_GAIN_DEFAULT = 80; // turunkan ke 60/40 bila clipping, antar-capture saja
static const uint8_t SAWT_RING_BLOCKS = 64;      // ~262 ms @ 62,5 kS/s
static const uint8_t SAWT_PROTOCOL_VERSION = 1;
static const size_t SAWT_HEADER_SIZE = 24;

static inline void sawt_put16le(uint8_t *dst, uint16_t v) {
  dst[0] = (uint8_t)(v);
  dst[1] = (uint8_t)(v >> 8);
}

static inline void sawt_put32le(uint8_t *dst, uint32_t v) {
  dst[0] = (uint8_t)(v);
  dst[1] = (uint8_t)(v >> 8);
  dst[2] = (uint8_t)(v >> 16);
  dst[3] = (uint8_t)(v >> 24);
}
