# Cadence v5: quality-analysis integration và correction v6 — 23/10/2026

> **Cập nhật sau báo cáo này:** [v6 đã chạy, coverage fail; correction queue v7](GOVERNOR_ISOLATED_CADENCE_V6_RESULT_2026-10-23.md).
> V6 đóng ở 1/12, không có governor contrast mới. Các mô tả v6 chưa chạy
> bên dưới là trạng thái lịch sử khi chuẩn bị.

## 1. Kết luận

**Batch v5 mới dừng ở 1/12 vì lỗi tích hợp quality analyzer.** PI đến đích,
dừng đạt, hai logger đóng sạch, native replay và provenance đạt. Measurement
view được tạo, nhưng thiếu `world_metadata.json` mà analyzer yêu cầu. Lượt
20 ms chưa chạy; 11 slot còn lại đóng, không retry hoặc dùng bù.

Đã bổ sung file phụ trợ đúng nguồn và kiểm tra **toàn bộ đường collector →
quality analyzer → metric extraction → timing reader/classification** bằng
artifact thật trong fixture offline riêng. **155 test đạt**; v6 đã freeze,
chưa release/chạy simulation. Các fixture không thay kết quả batch cũ.

**H2 vẫn chưa xác định.** Tiến bộ lần này là hoàn thiện measurement pipeline,
chưa phải bằng chứng governor cải thiện crossing. Chưa cần dữ liệu robot
thật để kiểm chứng integration này; phần hardware, PPO/predictor/Optuna
tiếp tục giữ lại.

## 2. Thực thi và kết quả v5 nguyên trạng

Yêu cầu tiếp tục hiện tại được hiểu là một batch v5 mới tối đa 12 attempts
theo lịch đã chuẩn bị. Release ghi trước launch, không dùng slot v3/v4,
không chấp nhận thêm ngưỡng ứng dụng. Protocol SHA v5:
`5c0a619e8ef8741b8708e008ece50fc5929c8805776699cf03a54d4bd9eff747`.

Attempt 1: PI, seed 77600, repeat 1, cold start domain 132. First PI và
20 ms được đặt làm integration checks trong ngân sách; batch dừng trước
lượt 20 ms theo gate hiện có.

| Outcome / gate | Kết quả |
|---|---|
| Arrival | **Success**, 16,600 s |
| Stopping | **Đạt**, cửa sổ gốc 2 s |
| Setup, provenance | Đạt |
| Lifecycle / end ACK / hai closure | Đạt |
| Native replay | Khớp, 166 bước; RMS native 0,012752385219229766 |
| Native timestamp/feedback-age checks | Đạt |
| GT whole-route coverage từ isolated view | **99,9157%** |
| PI cadence check | Đạt, 166 scoring rows, không micro trace |
| Quality availability | **Không đạt**, thiếu `world_metadata.json` trong view |
| Measurement integrity toàn bộ | **Không đạt** |
| Cleanup | Xác nhận; không launch attempt 2 |

Runner đã ghi `passed=True`; collector sau đó báo `quality_available=false`
và đóng batch. Whole-route coverage đạt không thay thế yêu cầu chất lượng
từng window hoặc xử lý lỗi analyzer. Không chọn subset metric để so
controller. Analyzer chính thức giữ đủ 12 slot và xuất
`measurement_invalid_no_performance_comparison`.

- [Release trước launch](governor_isolated_cadence_v5_run_2026-10-23/execution_release.json).
- [Kế hoạch phân tích](governor_isolated_cadence_v5_run_2026-10-23/analysis_plan.json).
- [Ledger nguyên trạng](../rl_runs/governor_isolated_cadence_v5_2026-10-23/ledger.json).
- [Summary nguyên trạng](../rl_runs/governor_isolated_cadence_v5_2026-10-23/summary.json).
- [Analysis không admit comparison](governor_isolated_cadence_v5_run_2026-10-23/analysis/report.json).

## 3. Lỗi cụ thể và correction v6

Primary có `world_metadata.json`. `finalize_view` đã copy contact events,
config, URDF và health, nhưng bỏ sót file này. `audit_single_cable_screen`
đọc metadata hình học trong quality analysis nên phát sinh
`FileNotFoundError` trước khi báo đầy đủ crossing/post-contact.

Correction duy nhất về xử lý dữ liệu của v6:

- Copy **verbatim** `world_metadata.json` từ primary vào measurement view,
  cùng các auxiliary bắt buộc khác.
- Giữ hash cả file source lẫn derived; thiếu hoặc tamper vẫn fail closed.
- Không tạo lại metadata từ trí nhớ/config khác, không vá view của run cũ,
  không đổi geometry, scoring, sampling, native score hay coverage 98%.

Đã tái hiện lỗi bằng regression test trước sửa. Bốn case mới kiểm tra copy
đúng bytes/hash, tamper source, tamper derived và thiếu file bắt buộc.
Suite sau correction: **155 test đạt**, gồm các nhóm lifecycle/identity,
CRC/epoch, native replay, coverage, cadence, executor và stopping cũ.

## 4. Kiểm tra toàn bộ collector trên recorded-artifact fixture

Các fixture trước chỉ đi qua một phần đường phân tích, nên chưa đủ phát
hiện việc thiếu auxiliary này. Lần này dùng
[harness full collector](governor_isolated_cadence_v5_run_2026-10-23/replay_full_collector.py)
đọc raw v5 vào thư mục tạm riêng:

1. Giữ native CSV, timestamps, samples/CDR, nguồn logger và source provenance
   nguyên bytes. Symlink chỉ để đọc; case/summary/path binding của fixture
   tách riêng. Không ghi vào case hoặc ledger đã đóng.
2. Tạo candidate view bằng finalizer mới và kiểm tra metadata copy/hash.
3. Gọi **collector thật** của isolated cadence, gồm quality analyzer,
   enrichment, sequence, original coverage/native/timestamp gates và
   cadence check.
4. Gọi metric extractor, timing reader và classifier; không patch validator,
   không tự đặt quality/integrity thành True. Runner/cleanup flags dùng
   đúng outcome đã lưu của lượt gốc.
5. Quarantine view sau kiểm tra: `admitted_for_new_contract=false`,
   `diagnostic_only=true`; validator từ chối sử dụng view đó cho experiment.

Kết quả fixture:

| Kiểm tra | Kết quả |
|---|---|
| Collector flags | Setup, provenance, measurement integrity, quality, stopping đều True trong fixture |
| Collection/acquisition errors | Không có |
| Executor classifier | Không có hard-stop reason trong fixture |
| Original metric extraction | **17/17 khả dụng** |
| Native replay | Khớp |
| PI cadence | Đạt, 166 scoring rows |
| Timing reader | Đọc thành công |
| Closed run artifacts | **72 file không đổi hash** |

[Fixture result](governor_isolated_cadence_v5_run_2026-10-23/full_collector_fixture.json)
ghi đầy đủ flags và metric availability. Đây là **software diagnostic
post-hoc trên một PI run**, không phải run v6, không chứng minh DDS loss-free
hoặc governor 20 ms đã integration-test. Không sửa measurement-invalid của
v5 hoặc biến các metric fixture thành một comparison mới.

## 5. Hiện trạng contract và bước tiếp theo

- Contract mới: **`isolated_joint_gt_cadence_v6_2026_10_23`**.
- [Protocol](governor_isolated_cadence_contract_v6_2026-10-23/protocol.json).
- SHA-256: `567228933edaece4fd4e615986316d150f18be40754e320eb26d3709828be153`.
- Software prepared; chưa release ngân sách, chưa chạy simulation v6.
- Robot/controller/world inputs, schedule, physics, PI/torque limits,
  native scoring 100 ms, sampling, coverage và stop window giữ nguyên v5.

**Bước tiếp theo có giá trị là live integration v6 trong một batch mới có
giới hạn.** Phần sửa đã có full collector fixture để review. Không audit
lại slip của PI run này và không coi số test tăng là bằng chứng governor.
Không tiếp tục slot của v3/v4/v5; không tự tạo release v6 từ batch đã đóng.

Sau phép đo hợp lệ mới trả lời: command có sớm hơn → actual wheel/body
đổi trước contact sau → crossing/tracking/time đổi thế nào. Hiện chưa có
governor run mới; 10%/+0,5s vẫn chỉ là đề xuất.

## 6. Kiểm tra offline

```bash
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
export PYTHONPATH="$PWD/src/nino_rl:$PWD/src/nino_control:$PWD/src/nino_rl/scripts${PYTHONPATH:+:$PYTHONPATH}"
python -m pytest -q src/nino_rl/test/test_acquisition_contract.py
python src/nino_rl/scripts/prepare_isolated_cadence_contract.py --validate docs/governor_isolated_cadence_contract_v6_2026-10-23
```

Source validation v5 tại lúc đóng đã lưu trước correction. Source hiện tại
khớp v6; frozen protocol/snapshot/result v5 giữ nguyên, không diễn giải lại.
