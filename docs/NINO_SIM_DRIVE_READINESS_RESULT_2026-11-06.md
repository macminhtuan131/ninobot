# Drive readiness — qualification đã đạt 2/2

06/11/2026 · **Đạt tích hợp reset/zero; chưa chứng minh motion hoặc learned benefit.**

Sau [failure V2](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md), đã triển khai
`DriveReadinessBackend` riêng: physical quiet **và** drive ACK feedback/zero,
diagnostics fresh≤40ms liên tục0,5s trong cùng cap5sim seconds.
Frozen backend/V1/V2 không bị sửa hoặc mở lại.

| Điều kiện | Zero ticks | Settling có điều khiển | Drive ACK trước tick đầu | Max joint age |
|---|---:|---:|---|---:|
| Stop plan6s, command thực zero | 10 | 0,5sim s | Có | 1ms |
| Stop plan8s, command thực zero | 10 | 0,5sim s | Có | 1ms |

- **2fresh launches,20zero ticks;0actor loads/optimizer/hardware/retry.**
- **68file** khớp SHA;**72boundary checks**, hai reader supported.
- **60physics requests** đúng ACK/completion/iterations, retries0.
- Primary6.209/independent6.209 records, common6.208source stamps,
  payload mismatch0. Counts không thay cho mọi window coverage/loss claim.
- Hai observer exit0/shutdownACK, hai lifecycle đóng; reference/target zero.
- **82software/GUI tests đạt** trước release:25candidate/coordinator/readiness
  và57GUI. Build `nino_rl`/`nino_pi`; release đã đóng sau attempt.

## Giới hạn phải giữ

Drive đã ready sớm trong cả2Gazebo runs; initially-blocked setup rows đều0.
**Chưa tái hiện ACK muộn trong Gazebo.** Fixture phần mềm kiểm ACK muộn và
không ACK, quiet riêng không đủ qua gate; cap50rounds/5s không bị tăng.
Hai lượt pass không chứng minh xác suất lỗi hiếm hoặc general reliability.

Qualification gọi backend trực tiếp bằngzero, không dùng actor/reference
controller để phát tiến; không kiểm task arrival, vRMSE motion, contact,
history benefit hoặc policy ranking. Không dùng pass để deploy TD3/hardware.

V2 vẫn failed, A seed11 hoàn tất/C partial giữ nguyên; không chạy lại49slots.
Bước sau là [eval-only có giới hạn](NINO_SIM_READY_EVAL_ONLY_NEXT_2026-11-06.md)
dùng checkpoint A đã có, không train thêm hoặc tiếp partial C.

## Provenance

- Root `~/nino_research/sim_drive_readiness_v1`.
- Artifact `20261106T125008475990Z_sim-drive-readiness`.
- Fingerprint `f98acf799df1a2833530056828e06f77a0d65a481358dd39f24dc42bba39de2a`.
- Manifest SHA256 `0c569728eb935dd2d6f6bd3ac1b1a0ca92fbfda313fff553e894473e57564aeb`.
- QA tại workspace `artifacts/sim_drive_readiness_2026-11-06/`.
- [Protocol/release scope](NINO_SIM_DRIVE_READINESS_PROTOCOL_2026-11-06.md).
- GUI profile **Reset drive readiness · ACK + quiet · zero-only** có kết quả,
  QC và nút stage đã tiêu thụ bị khóa. Real data cutoff02/11 không đổi.
