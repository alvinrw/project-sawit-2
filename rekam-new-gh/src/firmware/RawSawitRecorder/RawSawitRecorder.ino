/**
 * RawSawitRecorder.ino
 *
 * Hardware:
 *   - WisBlock Core RAK4631 (nRF52840)
 *   - WisBlock Base RAK19007
 *   - Ultrasonic PDM microphone RAK18032
 *
 * Streams unprocessed, signed 16-bit mono PCM over native USB serial.
 * There is no FFT, DC removal, filtering, normalization, or compression.
 * A small packet header lets the PC detect dropped blocks and recover sync.
 */

#include "audio.h"
#include <hal/nrf_pdm.h>

// The microphone is specified for a clock up to 4.8 MHz. The nRF52840 PDM
// peripheral/library can generate 4 MHz here. Ratio 64 gives exactly
// 4,000,000 / 64 = 62,500 PCM samples/second (Nyquist: 31.25 kHz).
static const uint32_t SAMPLE_RATE_HZ = 62500;
static const uint16_t SAMPLES_PER_BLOCK = BUFFER_SIZE; // 256 on RAK4631
static const uint8_t CHANNELS = 1;

// RAK's nRF52 PDM driver accepts 0..80. 80 is its maximum hardware gain.
// Lower this (for example to 60 or 40) if recorder.py reports clipping.
static const uint8_t PDM_GAIN = 80;

// 64 blocks = about 262 ms of buffering at 62.5 kS/s. This absorbs short
// Windows/USB scheduling stalls without changing or filtering PCM samples.
static const uint8_t RING_BLOCKS = 64;

struct AudioBlock {
  uint32_t sequence;
  int16_t samples[SAMPLES_PER_BLOCK];
};

AudioBlock ringBuffer[RING_BLOCKS];
volatile uint8_t ringHead = 0;
volatile uint8_t ringTail = 0;
volatile uint32_t nextSequence = 0;
volatile uint32_t droppedBlocks = 0;
volatile bool recording = false;

void onPDMdata();
bool startCapture();
void stopCapture();
bool writeAll(const uint8_t *data, size_t length);
void sendBlock(const AudioBlock &block, uint32_t droppedSnapshot);

static void setLed(bool active) {
  // LEDs on the RAK19007/RAK4631 combination are active-low.
  digitalWrite(LED_GREEN, active ? LOW : HIGH);
}

void setup() {
  pinMode(WB_IO2, OUTPUT);
  digitalWrite(WB_IO2, HIGH); // Enable the WisBlock IO slot / microphone.

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_BLUE, HIGH);

  Serial.begin(1000000); // USB CDC ignores baud, but documents required rate.

  // Let the microphone supply and USB interface settle. No text is printed:
  // every byte sent after capture starts belongs to the binary protocol.
  delay(500);
}

void loop() {
  // 'R' starts a clean recording; 'S' stops it. recorder.py sends these.
  while (Serial.available() > 0) {
    const char command = (char)Serial.read();
    if (command == 'R' && !recording) {
      startCapture();
    } else if (command == 'S' && recording) {
      stopCapture();
    }
  }

  if (!recording || ringTail == ringHead) {
    yield();
    return;
  }

  const uint8_t tail = ringTail;
  const uint32_t droppedSnapshot = droppedBlocks;
  sendBlock(ringBuffer[tail], droppedSnapshot);

  noInterrupts();
  ringTail = (uint8_t)((tail + 1) % RING_BLOCKS);
  interrupts();
}

bool startCapture() {
  noInterrupts();
  ringHead = 0;
  ringTail = 0;
  nextSequence = 0;
  droppedBlocks = 0;
  interrupts();

  PDM.onReceive(onPDMdata);
  PDM.setPins(PDM_DATA_PIN, PDM_CLK_PIN, PDM_PWR_PIN);

  // PCM_48000 selects a 4 MHz PDM clock in the RAK nRF52 BSP. Its default
  // decimation ratio is 80 (50 kS/s); switch safely to ratio 64 (62.5 kS/s).
  if (!PDM.begin(CHANNELS, PCM_48000)) {
    return false;
  }

  NVIC_DisableIRQ(PDM_IRQn);
  nrf_pdm_task_trigger(NRF_PDM, NRF_PDM_TASK_STOP);
  while (!nrf_pdm_event_check(NRF_PDM, NRF_PDM_EVENT_STOPPED)) {
    // IRQ is disabled, so this event cannot be cleared by the ISR.
  }
  nrf_pdm_event_clear(NRF_PDM, NRF_PDM_EVENT_STOPPED);
  nrf_pdm_disable(NRF_PDM);
  NRF_PDM->RATIO =
      (PDM_RATIO_RATIO_Ratio64 << PDM_RATIO_RATIO_Pos) & PDM_RATIO_RATIO_Msk;
  nrf_pdm_enable(NRF_PDM);
  nrf_pdm_event_clear(NRF_PDM, NRF_PDM_EVENT_STARTED);
  nrf_pdm_event_clear(NRF_PDM, NRF_PDM_EVENT_END);
  NVIC_ClearPendingIRQ(PDM_IRQn);
  NVIC_EnableIRQ(PDM_IRQn);

  PDM.setGain(PDM_GAIN);
  recording = true;
  setLed(true);
  nrf_pdm_task_trigger(NRF_PDM, NRF_PDM_TASK_START);
  return true;
}

void stopCapture() {
  recording = false;
  PDM.end();
  setLed(false);

  noInterrupts();
  ringHead = 0;
  ringTail = 0;
  interrupts();
}

void onPDMdata() {
  if (!recording) {
    return;
  }

  const uint32_t sequence = nextSequence++;
  const uint8_t head = ringHead;
  const uint8_t nextHead = (uint8_t)((head + 1) % RING_BLOCKS);

  if (nextHead == ringTail) {
    // Still consume/copy the driver block into a scratch slot is unnecessary;
    // the next PDM interrupt will expose the next completed DMA buffer.
    droppedBlocks++;
    return;
  }

  ringBuffer[head].sequence = sequence;
  PDM.read(ringBuffer[head].samples,
           SAMPLES_PER_BLOCK * sizeof(int16_t));
  ringHead = nextHead;
}

bool writeAll(const uint8_t *data, size_t length) {
  while (length > 0 && recording) {
    const size_t written = Serial.write(data, length);
    if (written == 0) {
      yield();
      continue;
    }
    data += written;
    length -= written;
  }
  return length == 0;
}

static void put16le(uint8_t *dst, uint16_t value) {
  dst[0] = (uint8_t)(value);
  dst[1] = (uint8_t)(value >> 8);
}

static void put32le(uint8_t *dst, uint32_t value) {
  dst[0] = (uint8_t)(value);
  dst[1] = (uint8_t)(value >> 8);
  dst[2] = (uint8_t)(value >> 16);
  dst[3] = (uint8_t)(value >> 24);
}

void sendBlock(const AudioBlock &block, uint32_t droppedSnapshot) {
  // 24-byte little-endian header:
  // magic, version, flags, header size, sequence, sample rate,
  // sample count, gain setting, cumulative dropped blocks.
  uint8_t header[24];
  header[0] = 'S';
  header[1] = 'A';
  header[2] = 'W';
  header[3] = 'T';
  header[4] = 1; // Protocol version.
  header[5] = 0; // Reserved flags.
  put16le(header + 6, sizeof(header));
  put32le(header + 8, block.sequence);
  put32le(header + 12, SAMPLE_RATE_HZ);
  put16le(header + 16, SAMPLES_PER_BLOCK);
  put16le(header + 18, PDM_GAIN);
  put32le(header + 20, droppedSnapshot);

  if (!writeAll(header, sizeof(header))) {
    return;
  }
  writeAll((const uint8_t *)block.samples,
           SAMPLES_PER_BLOCK * sizeof(int16_t));
}
