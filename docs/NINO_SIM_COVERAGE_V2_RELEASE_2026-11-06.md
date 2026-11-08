# Release Coverage V2 — một đợt Sim có giới hạn

> **Đã tiêu thụ và đóng release.**15launches/1.865control attempts,
> 1.864replay/0eval;49slot còn lại đóng. [Kết quả](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md).
> File này giữ record release trước thực thi, không cho phép chạy lại.

06/11/2026 · Theo yêu cầu tiếp tục nhánh Sim sau preflight V2.

Đã review source/runtime, manifest preflight, ma trận và release overlay.
Chỉ mở một attempt tại root `~/nino_research/sim_coverage_study_v2`:
6 learner A/C × seed11/22/33 ×1.024, rồi16 eval ×140.
Tối đa6.144train +2.240eval,5.760critic/2.880actor updates,64launches,
10.800giây;0retry/extra smoke/hardware. V1 giữ đóng toàn bộ slot còn lại.

- Fingerprint: `57dc776c83cf8ef3de6830423f27577b80299b089a628a3c9404d54d9f7894fe`.
- Preflight manifest: `0c8f324a5c60e5c23489279975941212cb4e2a4ce13cd206771e76b01a7b4280`.
- Preflight80software tests, GUI54tests và build2package đã đạt.
- Release JSON được chụp trước/sau vào workspace artifact
  `artifacts/sim_coverage_v2_release_2026-11-06/`.

Không sửa reward/physics/gain/QoS/action bounds/history; giữ native và hai GT
grids riêng. Rule5% là rule nghiên cứu, không là yêu cầu ứng dụng đã chấp nhận.
First episode là integration check trong budget; không có smoke physics ngoài.
Một failure đóng phần còn lại, giữ raw/partial và không chạy bù.

[Protocol](NINO_SIM_COVERAGE_V2_PROTOCOL_2026-11-06.md) và
[preflight](NINO_SIM_COVERAGE_V2_IMPLEMENTATION_2026-11-06.md) là cơ sở release.
Release không chứng minh measurement/learning benefit hoặc cho phép hardware.
