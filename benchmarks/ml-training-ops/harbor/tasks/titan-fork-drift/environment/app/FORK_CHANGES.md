# Our torchtitan fork (based on v0.2.2): intentional changes

Each of these was reviewed and is wanted. They must stay.

1. `training.max_norm` default 0.5 (was 1.0): tighter clipping after the March loss spikes (INC-2291).
2. New LR decay type `cosine_floor`: cosine that never drops below 10% (for long runs).
3. `c4_test` is shuffled once with a fixed seed (1234). The raw shard is sorted by crawl date.
4. Output layer init std halved (`0.5 * dim**-0.5`).
5. Chunked cross-entropy (`CE_CHUNK`): numerically the same loss as plain cross-entropy, but the
   fp32 logits never exist for the whole batch at once (memory at long sequence lengths).
6. `TITAN_RUN_TAG` banner at startup; `TITAN_ROPE_THETA` env override for RoPE theta.
7. Attention keeps an explicit softmax temperature attribute `attn_scale` (set to the SDPA
   default) so attention-temperature sweeps can override it per layer.
8. Small map-style datasets are sharded contiguously across data-parallel ranks (keeps each
   document's neighbours on one rank).
