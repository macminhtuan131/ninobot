# Frozen governor repeatability screen

See the [Vietnamese report](../GOVERNOR_FROZEN_REPEATS_2026-10-16.md).

Exactly four sequential cold starts ran under the prepared protocol. All
arrival/stop and reporting gates passed. The earlier instrumentation pair
remains separate; no historical trial scores were imported or rewritten.

- `episodes.json` / `episode_metrics.csv`: all four attempted outcomes.
- `decision.json`: automatic crossing RMS/peak comparison, without promotion.
- `quality_review.json`: review also considers whole-route RMS direction and
  historical severe peaks. It does not rewrite the automatic flag or scores.
- `caster_sequence_context.json`: privileged offline caster/contact evidence.
- `precontact_caster_floor_forces.json`: sampled load variation before intervention;
  zero median is not zero load throughout the window.
- `bracket_first_contact_geometry.json`: separate zero-force manifold and sampled
  loaded-contact timestamps; conservative geometry bounds do not certify fidelity.
- `verification.json`: configuration, provenance, preservation and cleanup.
- `source_manifest_sha256.json`: raw input and source hashes.

Large raw `.jsonl` logs remain at `rl_runs/governor_frozen_repeats_2026-10-16/`.
Original native/crossing metrics retain their original windows. The additional
force reference is diagnostic, not a replacement score or a governor input.
