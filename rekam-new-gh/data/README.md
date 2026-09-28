# Data — kontrak rekaman (aturannya di ../DOKUMEN-rekam.md)

- `raw_audio/<jenis>/hari-<N>/<jenis>_P<plant>_hari<N>_sesi<M>_<dur>s_<stamp>.wav`
  — data per jenis: kosong, air-kelebihan, air-normal, air-kekeringan,
  ph-normal, ph-asam. Immutable: tidak ditimpa/dinormalisasi/dihapus diam-diam.
- `controls/<jenis>/hari-<N>/kontrol-sesi<M>_hari<N>_<dur>s_<stamp>.wav`
  — SELALU box kosong tanpa tanaman/pot, patokan sesi (sesi 1=awal,
  2=tengah, 3=akhir). Bukan data latih.
- `pilot_test/` — latihan config semalam. DIBUANG, jangan masuk training.
- Tiap WAV tertelusur di `../metadata/captures/keseluruhan.csv`.
