# SLED (Self-Logits Evolution Decoding)

SLED nudges final logits using evidence from mid-layer projections and clamps to the final top-k union to remain stable.
Configure via `decoding.sled` in `config/accuracy.yml`.
