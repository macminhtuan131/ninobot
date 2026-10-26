# Cadence v4: kết quả integration và correction v5 — 23/10/2026

> **Mới hơn:** [batch v5 và correction v6](GOVERNOR_ISOLATED_CADENCE_V5_RESULT_2026-10-23.md).
> V5 đã đóng ở 1/12 do thiếu auxiliary world metadata trong view; v6 được
> kiểm tra phần mềm/full collector fixture, chưa release/chạy. Phần dưới là lịch sử v4/v5.

## 1. Kết luận hiện tại

**Đã chạy batch v4 mới, dừng ở attempt 1/12 và đóng 11 slot còn lại.**
Lỗi ACK của v3 đã được vượt qua trong lượt này: end ACK đúng, hai logger
đóng sạch. Tuy nhiên, measurement view không được tạo vì code giả định sai
schema control trace. Chưa có governor run hoặc cadence comparison mới;
H2 vẫn chưa được đánh giá.

Đã sửa ràng buộc identity, thêm fixture đúng schema thực, fault-test và
kiểm tra đường xử lý offline bằng artifact vừa thu. **151 test đạt**;
contract **v5** đã freeze, chưa có release hoặc attempt simulation.

Nút thắt hiện tại vẫn là **live integration của pipeline đo**, không phải
thiếu dữ liệu thật để làm bước này. Chưa có bằng chứng mới để tuning governor,
đổi cơ khí, mở predictor/PPO hoặc Optuna. Robot thật tiếp tục giữ lại.

## 2. Budget và kết quả v4 nguyên trạng

Yêu cầu tiếp tục của người dùng được hiểu là thực hiện bước integration
v4 vừa khuyến nghị, trong **một batch mới tối đa 12 attempts**. Release được
ghi trước launch, gắn protocol SHA
`36845e6aa41c1b984b325ebe891b05c2a9d9059be24d15f751a0b7d7ed586ac9`.
Không dùng slot v3. Lịch PI/20ms/100ms và hai block/repeat giữ nguyên;
attempt 1 là PI seed 77600 repeat 1, cold start domain 132.

| Gate / outcome | Kết quả đã lưu |
|---|---|
| Native arrival | **Success**, khoảng 16,600 s |
| Reset, setup, provenance | Đạt |
| Native replay | Khớp, 166 bước; native slip RMS 0,012897653951115253 |
| Initial readiness | Hai role/process đúng session |
| End ACK | Cả hai ACK được runner xác nhận |
| Closure | Joint/GT exit 0, hai status closed/error=null |
| Stop-window acquisition | Runner đã chờ, ghi `stop_window_start_s=22.303...` |
| Measurement-view finalization | **Không đạt**: `KeyError: 'governor_run_id'` |
| Stopping được admit trong ledger | **Chưa xác nhận (`null`)** |
| Measurement integrity | **Không đạt** |
| Cleanup | Xác nhận; không launch attempt 2 |

Executor summary: `hard_stop_measurement_integrity_pass`; chi tiết còn ghi
`first_integration_stopping_not_confirmed_no_retry`. Chưa có manifest view,
nên không lấy primary làm nguồn thay thế joint/GT riêng dù collector có
sinh một số metric phụ. Analyzer chính thức xuất
`measurement_invalid_no_performance_comparison`, giữ đủ 12 slot.

- [Release](governor_isolated_cadence_v4_run_2026-10-23/execution_release.json).
- [Kế hoạch phân tích trước kết quả](governor_isolated_cadence_v4_run_2026-10-23/analysis_plan.json).
- [Ledger nguyên trạng](../rl_runs/governor_isolated_cadence_v4_2026-10-23/ledger.json).
- [Summary nguyên trạng](../rl_runs/governor_isolated_cadence_v4_2026-10-23/summary.json).
- [Analysis không admit](governor_isolated_cadence_v4_run_2026-10-23/analysis/report.json).

## 3. Nguyên nhân và correction duy nhất của v5

`finalize_view` lấy `controls[0]['governor_run_id']`. Nhưng control trace
thật chỉ có seed, timestamps, governor state và telemetry; **run ID nằm
trong `episodes.csv` và các lifecycle marker**, không có cột đó trong trace.
Fixture cũ tự tạo cột run ID, vì vậy không phát hiện lỗi nối schema này.

Đã thay fixture dùng schema đúng và tái hiện lỗi trước sửa. Correction:

1. Đòi đúng một control trace không rỗng và đúng một native outcome.
2. Lấy run ID không rỗng từ native `episodes.csv`; seed phải đúng slot và
   native attempt phải là 1 như lifecycle của mỗi cold start một episode.
3. Run ID phải khớp terminal marker/terminal metrics, reset/end của cả hai
   logger và CDR/primary markers. Nếu trace có cột ID ở phiên bản khác,
   **mọi dòng** phải khớp; không chọn dòng thuận lợi.
4. Đưa **native CSV và control trace** vào hash provenance của view; không
   sửa CSV, không chèn cột, không suy ID chỉ từ timestamp hoặc logger tùy ý.

Không đổi controller, acquisition authority, native score, sampling,
coverage 98% từng window, stopping 2 s, physics, geometry, PI hoặc torque.
ACK/heartbeat correction của v4 vẫn giữ nguyên. Không tăng timeout hay retry.

## 4. Kiểm tra software và recorded-artifact fixture

**151 test đạt** sau correction, gồm 11 case mới so với v4:
schema trace thực, thiếu/empty/duplicate native outcome, ID rỗng/foreign,
seed/attempt sai, trace ID xung đột và tamper native/trace sau composition.
Các test cũ về lifecycle, CRC/epoch, source authority, replay, coverage,
cadence, executor và stopping vẫn đạt.

Để tránh chỉ kiểm tra fixture tổng hợp, đã chạy thêm
[recorded-artifact replay](governor_isolated_cadence_v4_run_2026-10-23/replay_schema_fixture.py)
trên raw CDR, primary và native CSV của lượt v4 vừa lưu. Output chỉ nằm
trong thư mục tạm, không ghi vào case đã đóng. Cùng các hàm hiện có xử lý
view → stability → stopping → native replay → các grid/window cũ:

| Kiểm tra offline trên candidate fixture | Kết quả |
|---|---|
| Composition / native identity | Khớp run ID native với hai nguồn; 9.625 joint và 950 GT trong view |
| Missing-value fill / resampling | Không / không |
| Native replay | Khớp native CSV |
| GT-header whole-route coverage | **99,6566%** |
| Grid 20 ms / grid dịch 10 ms whole-route coverage | **99,6386% / 99,5181%** |
| Crossing / fixed post-contact coverage, cả ba grid | **100%** |
| Sequence / sequence + recovery slip và vertical coverage | **100%** |
| Stopping fixture | Có đủ 100 GT + 100 drive samples trong cửa sổ 2 s; settled theo diagnostic gốc |
| Run artifacts nguyên trạng | 60 file không đổi hashes |

**Các kết quả fixture không sửa kết luận batch.** Đây là post-hoc software
integration diagnostic dùng code mới trên dữ liệu cũ, không phải một run v5
hoặc bằng chứng governor hữu ích. View thử được đặt
`admitted_for_new_contract=false`, `diagnostic_only=true` sau kiểm tra;
validator xác nhận nó không thể được dùng như view đã admit. Stopping trong
ledger v4 vẫn `null`, measurement invalid và không có performance comparison.

[Fixture result đầy đủ](governor_isolated_cadence_v4_run_2026-10-23/recorded_schema_fixture.json)
giữ định nghĩa coverage, cửa sổ, source paths và giới hạn suy luận. Không
suy từ một PI fixture rằng governor 20 ms đã được integration-test hoặc
mọi lần Gazebo sau sẽ không mất dữ liệu.

## 5. Contract hiện tại và điểm dừng

- **`isolated_joint_gt_cadence_v5_2026_10_23`**.
- [Protocol](governor_isolated_cadence_contract_v5_2026-10-23/protocol.json).
- SHA-256: `5c0a619e8ef8741b8708e008ece50fc5929c8805776699cf03a54d4bd9eff747`.
- Software prepared; `execution_authorized=false`, `budget_released=false`,
  `simulation_attempts=0`, live integration chưa được xác nhận.
- Input robot/world/controller và schedule byte-identical với v4; khác
  source freeze và contract identity/provenance nêu trên.

**Bước có giá trị tiếp theo là live integration v5 trong một ngân sách mới
có giới hạn**, sau khi review correction đã có test schema thực và replay
artifact. Không audit lại slip của cùng attempt PI hoặc tự tăng độ phức tạp
controller. V3/v4 đóng; không tiếp tục 11 slot của bất kỳ batch nào.

Khi có phép đo hợp lệ mới trả lời: command sớm hơn → actual wheel/body
thay đổi trước contact sau → crossing/tracking/time. Không đổi primary sang
rung, chấp nhận ngưỡng 10%/+0,5s hoặc promote dựa trên các fixture ở đây.

## 6. Tái tạo kiểm tra offline

```bash
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
export PYTHONPATH="$PWD/src/nino_rl:$PWD/src/nino_control:$PWD/src/nino_rl/scripts${PYTHONPATH:+:$PYTHONPATH}"
python -m pytest -q src/nino_rl/test/test_acquisition_contract.py
python src/nino_rl/scripts/prepare_isolated_cadence_contract.py --validate docs/governor_isolated_cadence_contract_v5_2026-10-23
```

Các snapshot/batch cũ được giữ nguyên; source hiện tại không được dùng để
tuyên bố vẫn byte-identical với frozen v4. Validation tại lúc đóng v4 được
lưu riêng trước correction.
