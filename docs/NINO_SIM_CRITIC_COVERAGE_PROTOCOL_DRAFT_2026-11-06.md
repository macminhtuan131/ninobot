# Study critic/coverage — bản thiết kế để review

> Cập nhật implementation 06/11: sampler/runner và profile GUI đã được xây
> theo draft; xem [báo cáo implementation](NINO_SIM_COVERAGE_IMPLEMENTATION_2026-11-06.md).
> Release Gazebo vẫn khóa. Các câu “chưa có runner” bên dưới ghi trạng thái
> lúc soạn draft; không phải kết luận hiện tại. Chưa có kết quả study mới.

06/11/2026 · `nino_critic_coverage_draft_v1_2026_11_06`

**Trạng thái: chuẩn bị xong protocol, chưa có runner hoặc release training.**
Các con số dưới đây là ngân sách đề xuất, chưa tiêu thụ. Không mở lại batch
cũ, không resume checkpoint/replay, không chạy hardware. Ngưỡng lợi ích 5%
là quy tắc nghiên cứu đề xuất; `minimum_effect_accepted` vẫn `null`.

## 1. Bằng chứng và câu hỏi duy nhất

**[N]** [Evaluation đã đóng](NINO_SIM_RELIABLE_EVAL_ONLY_RESULT_2026-11-06.md)
có 10/10 lượt hợp lệ; classical có vRMSE thấp hơn cả sáu lượt TD3 trên
native và hai grids. Audit 20 state open-window mỗi seed thấy Q1 seed
11/33 cùng ưu tiên −1, phù hợp với actor gần −1. Replay mỗi seed có 289
mẫu open-window, tập trung ở action âm với hai seed này. Đây là audit hậu
nghiệm trên trajectory riêng, chưa phải outcome counterfactual.

**[S]** Coverage hẹp trong lúc học có thể duy trì critic ranking bất lợi.
Actor có thể thực hiện đúng objective Q1 nhưng không cải thiện tracking.
Giả thuyết này có thể sai vì reward nhiều thành phần, critic chưa học đủ,
hoặc bài toán không cần learned residual.

**[Đ] Câu hỏi:** giữ cùng lịch học và tổng số cập nhật, việc duy trì các
probe action trải đều trong vùng residual được phép có giảm phụ thuộc seed
và cải thiện tracking của final actor so với Gaussian exploration không?

Không tăng `learning_starts`: đổi 64→280 với cùng 1.024 transition sẽ giảm
960→744 critic updates. Vì vậy study này **không phải warmup ablation**.
Can thiệp là chính sách thu action khi train, bao gồm biên độ khám phá và
state occupancy phát sinh; không tách riêng được coverage khỏi hai yếu tố
này. Không kết luận critic sai nhân quả chỉ từ Q-grid thuận lợi hơn.

## 2. Hai arm mới và biến giữ cố định

| Thành phần | A — Gaussian control | C — probe phân tầng |
|---|---|---|
| Khởi tạo | Fresh seed 11/22/33 | Cùng seed/initial network với A; kiểm hash trước học |
| Transition 1..64 | Uniform warmup theo parent | Giống A |
| Sau warmup, ngoài probe | Actor + Gaussian σ=0,1, clip [−1,1] | Giống A |
| Mỗi quyết định open thứ 4 sau warmup | Giữ Gaussian request | Thay request bằng một probe phân tầng |
| Cửa sổ đóng | Giữ request/zero projection như parent | Giống A; không probe |
| Evaluation | Final actor deterministic | Final actor deterministic, **tắt probe** |

Eligibility chỉ đọc `common_window_open` tại observation index 101 đã có
**trước action**. Không dùng GT/contact, reward tương lai hoặc kết quả step
để chọn probe. Counter chỉ tăng ở open decisions sau warmup, giữ qua reset
của cùng learner; probe tại counter 4,8,12,... Counter không tăng ở window
đóng, không tự mở window/permission khi thiếu dữ liệu.

Bốn bin request: [−1;−0,5), [−0,5;0), [0;0,5), [0,5;1]. Mỗi block bốn
probe dùng một permutation ngẫu nhiên của bốn bin; jitter uniform trong
bin bằng RNG riêng. Ghi endpoint/clipping chính xác; không bỏ block cuối
chưa đủ bốn. Dùng stream riêng cho initialization, warmup, Gaussian,
probe-order, probe-jitter, replay. Gaussian được lấy mẫu ở mọi decision sau
warmup, kể cả khi C thay bằng probe, để probe không làm lệch stream noise.
Không reseed global Torch/NumPy từ probe sampler.

**Replay bắt buộc lưu request sau khi chọn Gaussian/probe, trước shared
window/projection.** Log actor mean, noise, probe flag/bin/counter,
requested, windowed, mapped, accepted và issued riêng. Không lưu actor
output làm replay action khi environment thực nhận probe. Reward và cost
thay đổi action dùng request thực này theo contract cũ.

Giữ ABI 103D/1D, history 5, common ±0,005 m/s, cruise 0,2 m/s, stop 6/8 s,
14 s/140 tick, control 100 ms, physics 1 ms/chunk 50 ms, follower/PI,
projection/window, estimator, reward, geometry, source/termination và
acquisition như parent. Không đổi gain, current, QoS, history, reward,
Optuna, PPO hoặc domain randomization trong study.

Các checkpoint cũ chỉ là bối cảnh. Không dùng chúng thay A mới, không gộp
các seed cũ/mới thành sáu lặp. Cùng seed giúp so theo block, **không** là
exact-state branching hay bảo đảm trajectory tiếp xúc/trạng thái giống nhau.

## 3. Ngân sách và thứ tự cố định trước release

| Hạng mục | Mỗi learner | Toàn study tối đa |
|---|---:|---:|
| Fresh learners | — | 2 arm × 3 seed = 6 |
| Training transition | 1.024 | 6.144 |
| Critic updates | 960 | 5.760 |
| Actor updates | 480 | 2.880 |
| Training launches | 8 | 48 |
| Evaluation | — | 16 lượt × 140 = 2.240 tick |
| Tổng control transition | — | 8.384 |
| Tổng Gazebo launches | — | 64 |

Learning starts 64, gradient_steps 1, train_freq 1, policy_delay 2; các
hyperparameter còn lại giữ [YAML learner](../src/nino_rl/config/residual_reliable_td3_v1.yaml).
Đếm optimizer thực tế phải khớp, không suy ra chỉ từ timesteps. Mỗi learner
có 7 episode đủ 140 tick và segment cuối 44 tick bị censor bởi budget;
segment cuối không tự gắn terminal/timeout giả. Stop luân phiên 6/8 s,
bắt đầu 6 s, backend/context/observer/partition mới mỗi episode.

Train order: **A11, C11, C22, A22, A33, C33**. Không chọn checkpoint giữa
chừng theo reward; chỉ final checkpoint từng learner. Nếu training chưa đủ
sáu learner thì không chạy một evaluation chọn lọc cho kết luận thắng/thua.

Eval order khóa trong [config](../src/nino_rl/config/residual_coverage_study_v1.json):
12 condition arm×seed×stop và 4 baseline B0/classical×stop, tất cả chạy mới
cùng evaluator. Mỗi condition một lượt; không gọi 16 lượt là 16 learner
độc lập. Không dùng eval cũ thay baseline mới.

Wall deadline đề xuất **10.800 s** cho toàn job, không phải thời gian chạy
đã đo hoặc deadline realtime. Cơ sở: eval trước 451,31 s/1.400 tick; nhân
8.384/1.400 xấp xỉ 2.703 s, thêm margin khoảng bốn lần cho learner/startup.
Startup/cleanup/optimizer có thể khác; chạm deadline thì đóng, không gia hạn.

## 4. Đo và phân tích khóa trước kết quả

### Outcome chính và estimand

Primary giữ **velocity RMSE toàn 14 s, native 100 ms**, body trừ independent
nominal reference như evaluator cũ. GT-header 20 ms và dịch +10 ms báo riêng;
không nội suy body để tạo timing/GT giả hoặc chọn grid thuận lợi.

Với seed s, stop t, grid g: `d_s,t,g = (RMSE_C − RMSE_A) / RMSE_A`.
Ước lượng so arm là mean bằng trọng số qua hai stop của từng seed, sau đó
mean ba seed; báo cả 6 paired deltas và range giữa seed, không pooled ratio.
Tương tự so C với classical và B0 riêng. Nếu denominator 0 thì relative
delta undefined, giữ absolute delta, không chèn epsilon hậu nghiệm.

Ba seed là pilot chẩn đoán, không đủ power claim hoặc generalization. Không
bootstrap frame như mẫu độc lập, không dùng reward tăng làm thay primary.

Secondary: path RMSE, return và từng reward term, stop/task, saturation,
action change và tỷ lệ projection/intervention. Constraints giữ: đủ 140
tick, marker 0,95 m, quiet stop 2 s, max cross-track 40 mm, estimator position
50 mm/yaw 0,05 rad, không guidance fault/intervention. Giữ native/source
support ≤40 ms và toàn bộ integrity/READY/epoch/closure của evaluator cũ.

### Manipulation check và critic diagnostic

- Mỗi learner: histogram requested **và windowed/accepted** chỉ ở open
  decisions; counts, bin fraction, probe/nonprobe, clipping/saturation;
  chia warmup và post-warmup. Không dùng samples ở closed window để làm
  coverage trông tốt hơn. Đề xuất coverage tối thiểu C: mỗi bin ≥10 mẫu
  và ≥5% open requests, mọi seed; nếu không đạt, intervention chưa tạo
  coverage theo thiết kế, kết luận cơ chế unknown, không kéo dài train.
- Nếu A cũng đủ coverage hoặc accepted profiles gần như không khác thì
  báo contrast yếu; không kết luận coverage vô ích.
- Critic: 20 observation steady-open cố định từ **B0 đã ghi trước study**,
  chọn đều theo decision index qua stop6/8 (10 mỗi stop); chốt indices/hash
  trong preflight trước học. Cả sáu critic dùng cùng 20 packet trên grid
  [−1;−0,5;0;0,5;1]. Báo Q1/Q2/min-Q, argmax, disagreement, actor-Q gap.
  Thêm 20 packet own-policy mỗi learner chọn cùng rule để so distribution.
- Q-grid không thêm physics/updates; snapshot model/targets/optimizer/
  counters trước/sau. Q không là đo outcome của action chưa thực hiện.
  Đổi Q ranking mà tracking không tốt hơn không phải system benefit.

## 5. Go / no-go / unknown — đề xuất để review

**Study hợp lệ trước:** đủ artifacts/conditions, integrity và constraints;
mọi learner đúng update budget, replay-action parity, finite/save-load.
Failure giữ raw và reasons; không xóa seed rồi chỉ tính seed còn tốt.

**Ứng viên để nghiên cứu holdout riêng**, chưa promote: C đạt coverage và
tracking tốt hơn A; mean benefit so classical **ít nhất 5% trên cả ba
grids**; ít nhất 2/3 seed tốt hơn classical ở cả hai stop trên cả ba grids;
không seed/stop nào tệ hơn classical quá 5%; tất cả constraints đạt.
Các mức 5% chưa được ứng dụng chấp nhận; trước release phải review và khóa
quy tắc này hoặc một thay thế có lý do. Không đổi sau khi nhìn kết quả.

**No-go cho mở rộng TD3 clear known-stop:** measurement hợp lệ, có coverage
contrast nhưng C vẫn không hơn classical, hoặc vẫn bão hòa âm và tracking
bất lợi. Nếu C tốt hơn A nhưng chưa hơn classical: có giá trị diagnostic,
giữ classical cho ứng dụng; không tự cấp train dài.

**Unknown:** effect nhỏ hơn mức đề xuất, ranking đổi theo grid, coverage
contrast yếu, thiếu data/conditions hoặc task failure. Không tự tăng mẫu,
không hạ gate, bỏ spike hoặc sửa objective. Unknown không tự cho budget mới.

Sau no-go/unknown, ưu tiên baseline/operating envelope hoặc câu hỏi contact
H2 có cơ chế riêng. Tuning cổ điển/calibration không phải chờ PPO/TD3 thắng.
Hardware vẫn theo gate SysID/body reference/shadow/deployment riêng.

## 6. Artifact và các việc còn phải triển khai

1. Review draft/config và ngưỡng đề xuất. Planner hiện chỉ kiểm ngân sách,
   matrix và draft flag; **không phải runner hoặc xác minh simulator**.
2. Xây runner version mới, sampler với RNG tách biệt, actual-request replay
   parity, ledger một lần, deadline/cancel và evaluator dùng chung. Pin
   nguồn/runtime/artifact, fixed B0 critic packets; không sửa frozen learner.
3. Software tests: warmup/eligibility trước action, reset/counter/bin
   balance, RNG isolation, replay override/reward parity, no probe khi eval,
   budget/order, tamper/checkpoint ABI, failure trước reset và closure.
   Không thêm Gazebo smoke ngoài 64 launches. Một correction có căn cứ chỉ
   ở bước software **trước release**; sau launch không retry/correction.
4. GUI: hiển thị 6 learner slots, 16 eval slots, seed/arm, optimizer counts,
   progress/errors, matrix 3 grids, coverage/Q diagnostics và kết luận.
   Nút chạy chỉ mở sau runner/preflight và release mới; không tái dùng nút
   learner/eval đã đóng. Hiện chỉ có mục roadmap và nút **xem protocol**.
5. Khi đã release riêng: một root mới, một attempt; lỗi/cancel/deadline đóng
   toàn bộ slots chưa chạy. Seal raw/trace/config/checkpoint/replay/manifest;
   báo attempts partial, right-censoring, source gaps và failures.

### Dấu vết đầu vào

Learner fingerprint: `659254596ac139709828d9f8fb64fba51c191fafbae857bb25996bbfe887ff46`.
Eval manifest: `2e111a3de591c2b5c616d9264392dc4f9cae3dadd74ae5962500edd50b645144`.
Controller ABI: `b8c71ccb876cb6f2f5ab66d08d74d9b3d8cfdbfac22ccfc3b326da16b5a2e6e0`.
Những SHA trong draft là pin dự kiến; runner còn phải kiểm byte thật và
dependencies/runtime trước khi nhận budget. Source cũ/manifest không sửa.

**Việc kế tiếp:** triển khai sampler/runner và software preflight theo draft
này. Chưa cần real bag mới. Điều làm đổi khuyến nghị là coverage contrast
đủ và lợi ích tracking nhất quán so baseline, không phải chỉ Q/return đẹp.

## Kiểm tra bản thiết kế đã thực hiện

- 14 test planner và 42 test GUI đạt; kiểm release/resume, budget/update
  arithmetic, duplicate/order, warmup và replay semantic drift.
- Build `nino_rl`, `nino_pi` đạt; config/planner/GUI cài đặt khớp source,
  default config của planner tìm được trong cả source và colcon copy install.
- GUI roadmap đã xem trực quan; nút xem protocol chỉ mở tài liệu.
- Learner fingerprint, controller ABI và eval manifest cũ vẫn khớp pin.
  Training/Gazebo/hardware mới: **0**; real-data cutoff giữ 02/11.

Chi tiết: [verification JSON](NINO_SIM_CRITIC_COVERAGE_DRAFT_VERIFICATION_2026-11-06.json).
Software tests này chưa kiểm sampler hoặc runner, vì hai phần đó chưa xây.
