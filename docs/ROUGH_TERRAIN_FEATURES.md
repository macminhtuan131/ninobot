# Extended rough terrain: feature catalogue

Coordinates are in metres. Signed relief is added carving/rise relative to the rolling background, not absolute ground elevation.
The extension uses the original terrain generator for continuous hills, valleys and asymmetric relief between the annotated features.
Blue depressions and brown mounds are sculpted into the shared collision/visual mesh.

| ID | Type | x | y | Length × width (m) | Relief (cm) | Angle (°) |
|---|---|---:|---:|---|---:|---:|
| D1 | round bowl | 7.45 | -1.05 | 0.96 × 0.86 | -2.5 | 0 |
| M1 | rounded mound | 7.5 | 0 | 0.84 × 0.8 | +3.5 | 0 |
| D2 | flat bottom bowl | 7.45 | 1.05 | 0.96 × 0.9 | -4 | 0 |
| D3 | angled trough | 8.3 | -1.12 | 0.96 × 0.64 | -4.5 | 25 |
| D5 | broad bowl | 8.38 | 0 | 1 × 0.9 | -10 | 0 |
| M4 | angled ridge | 8.28 | 1.05 | 0.96 × 0.72 | +7 | -25 |
| M3 | low plateau | 9.13 | -0.98 | 1 × 0.9 | +8 | 0 |
| S1+ | saddle mound | 9.15 | 0.3 | 0.72 × 0.76 | +6 | 0 |
| S1- | saddle bowl | 9.55 | -0.24 | 0.5 × 0.64 | -4 | 0 |
| M6 | rounded mound | 9.15 | 1.08 | 1.04 × 0.96 | +14 | 0 |
| W1 | drive bowl | 7.98 | 0.171 | 0.32 × 0.26 | -1.2 | 0 |
| W2 | drive bowl | 8.98 | -0.171 | 0.34 × 0.28 | -2 | 0 |
| C1 | caster bowl | 8 | -0.088 | 0.15 × 0.13 | -0.6 | 0 |
| D9 | broad bowl | 6.2 | 1.25 | 1 × 1.1 | -5 | 0 |
| M7 | rounded mound | 6.2 | -1.25 | 1 × 1.1 | +6 | 0 |
| D4 | broad bowl | 1.75 | 2.9 | 1.04 × 0.96 | -7 | 0 |
| M2 | rounded mound | 3.15 | 3.03 | 1.3 × 1.04 | +6 | 0 |
| D6 | broad bowl | 4.8 | 2.95 | 1.56 × 1.16 | -12 | 0 |
| M5 | rounded mound | 6.3 | 3.05 | 1.32 × 1.08 | +10 | 0 |
| D7 | flat bottom bowl | 7.8 | 2.85 | 1.14 × 1.04 | -8 | 0 |
| D8 | angled trough | 9.05 | 3 | 1.16 × 0.72 | -6 | -25 |
| M8 | banked mound | 1.65 | -2.95 | 1.04 × 0.96 | +4.5 | 15 |
| D10 | round bowl | 3 | -3.05 | 1.1 × 0.96 | -4.5 | 0 |
| M9 | rounded mound | 4.6 | -2.9 | 1.36 × 1.12 | +12 | 0 |
| D11 | broad bowl | 6.1 | -3.05 | 1.44 × 1.1 | -9 | 0 |
| M10 | low plateau | 7.6 | -2.95 | 1.2 × 1.1 | +9 | 0 |
| D12 | angled trough | 9.1 | -3 | 1.12 × 0.96 | -5.5 | 20 |
| W3 | drive bowl | 2.5 | 2.471 | 0.36 × 0.29 | -3 | 0 |
| W4 | drive bowl | 3.93 | -3.6 | 0.48 × 0.4 | -4 | 0 |
| C2 | caster bowl | 6.9 | 2.488 | 0.17 × 0.15 | -1 | 0 |
| W5 | drive bowl | 5.5 | 3.35 | 0.34 × 0.28 | -1.8 | 0 |
| C3 | caster bowl | 8.55 | -3.388 | 0.15 × 0.13 | -0.8 | 0 |

The original centre strip remains unchanged at x=0.8..5.7 m, y=-2..2 m; its bowl IDs are L1..L9.
The rough patch is 8 m wide (y=-4..4 m). Additional carving fills the old taper corners and both new sides.
The flat landing is x=10..12 m and the default goal is (10.5, 0).
Flat, connected goal halls surround it: world x=-2..12 m, y=-7.2..7.2 m.
Side ramps occupy y=4..5.2 m and y=-5.2..-4 m. The side goal halls are 2 m wide.
Five profile lines in the preview are drawing guides, not automatically loaded paths.
The rough training config now samples eight user-drawn routes with ordered route gates.
See ROUGH_DRAWN_ROUTES.md and rough_routes_preview.png for the configured trajectories.

## Optional goal stations

Station markers are visual only. The rough trainer selects a configured route and its goal each episode.

| Goal ID | Hall | x (m) | y (m) | Exit heading (degrees) |
|---|---|---:|---:|---:|
| W1 | west | -0.75 | 0 | 180 |
| E1 | east | 10.5 | 0 | 0 |
| N1 | north | 2.5 | 6.2 | 90 |
| N2 | north | 5.4 | 6.2 | 90 |
| N3 | north | 8.4 | 6.2 | 90 |
| S1 | south | 2.5 | -6.2 | -90 |
| S2 | south | 5.4 | -6.2 | -90 |
| S3 | south | 8.4 | -6.2 | -90 |
