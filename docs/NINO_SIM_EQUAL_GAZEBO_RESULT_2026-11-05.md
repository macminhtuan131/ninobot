# Kết quả qualification wrapper103D/1D trong Gazebo

05/11/2026 · **4/4fresh launches,560evaluation ticks,560diagnostic replay rows.**
Actor inference/optimizer/training/hardware0. Chạy qua nút GUI, worker exit0.
[Protocol chốt trước chạy](NINO_SIM_EQUAL_GAZEBO_PROTOCOL_2026-11-05.md).

## 1. Quyết định

**[N — Gazebo]** Wrapper103D/1D giữ preview/history, source/decision clock,
shared window, nominal scoring và request→mapped→accepted semantics ở
clear development stop6/8s.4/4 đạt marker0,95m+quiet stop2s và engineering
bounds cũ. Không có source/guidance/physics failure hoặc retry.

**[S]** Gate tích hợp để thiết kế learner103D/1D đã có bằng chứng trong
envelope hẹp này. Batch không dùng actor đã học, không đánh giá thuật toán,
không chứng minh useful first-contact authority hoặc sim-to-real.

**[Đ]** Chuyển sang thiết kế [bounded learner pilot common-only](NINO_SIM_COMMON_TD3_PILOT_NEXT_2026-11-05.md),
fresh model/task/checkpoint identity mới. Dự thảo3seeds×1.024transitions và
10evaluation launches chưa triển khai/chạy hoặc mở budget. Không tiếp tục
các batch qualification gần giống chỉ để lặp lại integration đã đạt.

## 2. Đã chạy gì và kết quả diagnostic

Clear box/yaw0/cruise0,2m/s/warmup0,5s, horizon14s, native100ms/physics1ms.
Giữ estimator wheel+IMU, follower, projection/ramp/wheel PI và frozen
103D/1D wrapper; không sửa frozen parent để batch mới đạt.

| Arm / stop | Ticks | Window decision(s) | Request khác0 bị gate chặn | Native v RMSE(m/s) | Path RMSE(mm) | Integration/stop |
|---|---:|---|---:|---:|---:|---|
|B0 /6s |140 |2,5–5,4(30ticks) |0 |0,004884 |0,032 |Đạt |
|Classical /6s |140 |2,5–5,4(30ticks) |0 |0,003926 |0,037 |Đạt |
|Probe /6s |140 |2,5–5,4(30ticks) |73 |0,004903 |0,229 |Đạt |
|Probe /8s |140 |2,5–7,4(50ticks) |60 |0,005353 |0,450 |Đạt |

Probe deterministic−1/0/+1 có bound common±0,005m/s và differential0; không
là learned TD3. B0/classical có cùng thông tin theo schema, nhưng feedback
trajectories khác; fresh launches/seed reset701 không exact-state branching.
Số window ticks của B0 là **eligible window**, không B0 phát residual.

Những RMSE trên chỉ diagnostic của integration, không quality gate hoặc
lý do chọn checkpoint/tuyên bố superiority. Một launch/condition không là
benefit test; stop6/8 đã xem không đổi tên thành unseen bank. Max path toàn
batch0,692mm, maxestimate4,27mm, dưới engineering bounds đề xuất40/50mm;
chưa là thông số chính xác hoặc acceptance của robot thật.

| Arm / stop | GT-header20ms v RMSE(m/s) | Grid dịch10ms(m/s) |
|---|---:|---:|
|B0 /6s |0,006456 |0,006461 |
|Classical /6s |0,006037 |0,006041 |
|Probe /6s |0,006500 |0,006505 |
|Probe /8s |0,006799 |0,006804 |

Method được chốt trước: latest GT tại/trước grid, nominal held theo native
interval tại GT header; không nội suy body.696/695grid points mỗi run,
support≤20ms. Đây là reference alignment/aggregation khác native endpoint,
không thay native bằng grid thuận lợi hoặc gọi GT50Hz có resolution10ms.

## 3. Các kiểm semantics đã đạt

-103D=100history+2plan+previous requested scalar, ABI mới đúng mỗi tick;
  inherited100D/2D identity/proposal giữ riêng. Không privileged controller
  input. Source/guidance/task/scorer đều dùng cùng stop6/8s.
- Preview/source decision clock đúng epoch, countdown và request trước đó
  causal; nominal adapter/scorer và legacy shadow cùng source khớp từng tick.
- Classical mapped2D khớp rule cũ trên chính received source. Shadow chỉ
  đọc/check, không chọn hoặc sửa request của controller mới.
-133request khác0 ngoài window giữ nguyên trong trace/replay, mapped2D0.
  Differential residual0 nhưng yaw follower còn hoạt động.
-560replay rows giữ obs103/request1D/nextobs103/reward/terminal/timeout;
  numerical audit shared helper đạt. File replay chỉ chẩn đoán integration,
  không replay TD3 train hoặc offline-RL dataset.

### Correction diễn giải thời điểm mở window

Trace mới **và trace B0 stop-transfer cũ** đều có first forward source tại
decision0,5s. B0 mới tại2,4s có nominal v≈0,19999050m/s, yaw≈−5,54×10⁻⁵rad/s;
tại2,5s mới đạt0,2m/s. B0 cũ tại2,4s cũng chỉ≈0,19999633m/s. Tiny follower
yaw kết hợp wheel-ramp giữ nominal body dưới steady tolerance1e−8 một tick.

Test mới giữ source start0,5s, so yaw0 với yaw0,0001rad/s, tái hiện opening
2,4s/2,5s. Vì vậy diễn giải trước rằng source Gazebo muộn một tick là sai.
Đã sửa report/contract offline theo bằng chứng mới; raw/frozen source và
source snapshots cũ giữ nguyên. Không sửa detector/ramp/tolerance để ép count.

## 4. Measurement, physics và provenance

-73artifact files và108prelaunch source files khớp SHA256 trước cập nhật
  hồ sơ kết quả; parent offline fingerprint/ABI không đổi.
-1.160physics requests ACK/completion, iteration và clock delta đúng1ms/step;
  retry0.8parameter readbacks hoàn tất.2.800causal estimator updates có
  gyro/wheel support hợp lệ,700/run; no truth input.
-Native boundary source age tối đa17ms, dưới40ms measurement proposal;
  không là phần cứng latency. GT source gap20ms. Drive raw gaps tới107ms,
  boundary source vẫn mới; không suy full transient/continuous coverage,
  loss-free logging hoặc actuator-limit readback đầy đủ từ counts/hash.
-Job đóng exit0, ledger consumed; không còn worker/Sim do job sở hữu.
  Dữ liệu thật cutoff02/11, real data mới0, không SSH/flash/motor commands.

Root:
`/home/tuanmac/nino_research/sim_equal_gazebo_v1/20261105T120846465990Z_sim-equal-gazebo`.

Fingerprint module/config/script:
`f172f89ad897828aeda84776b66ed9584a8784d79bd5f0c8557c69beba6d0e6a`.
Manifest SHA256:
`10c2270e45430c0342717f0d6ace678fbd01ffddc6144dc45f826799605d5b36`.
Frozen ABI:
`b8c71ccb876cb6f2f5ab66d08d74d9b3d8cfdbfac22ccfc3b326da16b5a2e6e0`.

## 5. GUI, tests và bước tiếp

**Xây project → NHÁNH SIM → Qualification103D/1D · Gazebo ·4lượt**:
bảng4×10, native/header/path, window/counts, task/stop/integration; rerun
bị khóa. Nút Xem kết quả đọc đúng artifact. Các profile trước và TRAIN TD3
V3/100D/2D giữ riêng; chưa giả vờ nút train cũ huấn luyện ABI103D/1D.

12runner/control tests và21GUI tests đạt; build2packages và source/install
parity tại [verification](NINO_SIM_EQUAL_GAZEBO_VERIFICATION_2026-11-05.json).
Test thêm về yaw/ramp là kiểm software sau audit, không physics launch mới.
QA/screenshot/plot/XML/source snapshot tại
`artifacts/sim_equal_gazebo_2026-11-05/` trong workspace thread.

**Một việc tiếp:** chốt và triển khai bounded TD3 common-only learner pilot
theo draft mới, cùng103D/1D/reward/window/limits đã qualify. Đây là bước
kiểm khả thi học với cùng information budget, chưa hứa learned advantage.
Real data và factory requirement hoàn chỉnh không chặn pilot Sim; objective
tạm, budget, seeds và split cần ghi minh bạch trước outcomes. Effect nhỏ/
sampling-sensitive hoặc không vượt classical →unknown/giữ baseline, không
tự tăng timesteps, đổi reward hoặc mở PPO/history/DR/hardware cùng lúc.
