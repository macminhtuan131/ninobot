# Pilot TD3 mới với joint RELIABLE và lifecycle từng episode

06/11/2026. Release riêng cho Sim local; không mở lại batch partial 700 bước.

## Căn cứ và phạm vi

Candidate `e2e0748afe1b560e1b00ee847029e5481d8654a84f7187d711750fe173bc10a8`
đã qua fixture và hai lượt B0. Manifest qualification:
`629f0c636309b18bcbe391f3550424bfbb0fb28d6adff1967ce5de94479d056a`.
Đó là functional qualification, chưa chứng minh nguyên nhân lỗi 50 ms cũ
hoặc vận hành dưới optimizer load. Pilot này kiểm learner/load thực trong
ngân sách; không thêm một Gazebo smoke riêng.

## Budget và điều kiện khóa trước chạy

- Seed 11 → 22 → 33, fresh model/critics/targets/optimizers/replay.
- 1.024 transition/seed, tối đa 3.072; clear box trong factory lab, cruise
  danh nghĩa 0,2 m/s. Đây không phải mixed factory/contact generalization.
- Stop nguồn 6/8 s xen kẽ, bắt đầu 6; 140 tick/episode, 7 episode đầy đủ
  +44 tick bị cắt phải. Không thêm bước để hoàn tất episode thứ tám.
- ABI103D/1D, history5, common residual ±0,005 m/s qua window/projection
  và follower/PI cũ. Reward, limiter, 1 ms physics/50 ms chunk không đổi.
- CPU32²; lr3e-4, gamma0,99, tau0,005, batch32, buffer8192, warmup64,
  train_freq1/gradient_steps1, policy_delay2, noise0,2/clip0,5,
  exploration0,1. Zero-init actor head/target; warmup/exploration vẫn có action.
- Mỗi seed đúng 960 critic updates, 480 actor updates; lưu finite losses,
  actor change, targets/optimizers/replay và kiểm save-load parity.
- Sau khi cả ba seed đạt mới chạy 10 lượt fresh eval: B0 stop6; TD3/11
  stop6; classical stop8; TD3/22 stop8; TD3/33 stop6; classical stop6;
  TD3/11 stop8; B0 stop8; TD3/22 stop6; TD3/33 stop8. Mỗi lượt140tick.
- Tổng tối đa4.472 control tick,34 launches; mọi final checkpoint đều được
  đánh giá, không chọn checkpoint/seed theo kết quả. Đánh giá deterministic.
- Wall deadline5.400s: hai B0 qualification mất89,58s/280tick, suy rộng
  khoảng1.431s/4.472tick (đã gồm startup/closure); khoảng3,77× làm margin
  optimizer/lifecycle. Đây là giới hạn wall của job, không latency realtime.
- Một job/root `~/nino_research/sim_reliable_td3_v1`; state tồn tại là đã
  tiêu thụ, kể cả corrupt/failure. Một lỗi đóng mọi slot còn lại, không retry.

## Lifecycle và acquisition

Mỗi episode có directory/partition/primary ROS context và independent
observer process mới. Trước epoch mới phải đóng Gazebo/executor/log primary,
đóng và ACK observer cũ; xác minh thread/process không còn sống. Không mang
count/latest stamp/boundary/estimator/history từ episode trước qua reset.
Epoch là namespace artifact + partition + local estimator epoch; timestamp
sim có thể lặp lại qua launch nên không dùng timestamp đơn lẻ làm identity.
Observer READY trước launch; xác minh đúng một joint publisher RELIABLE.

Primary giữ RELIABLE/depth100; independent BEST_EFFORT là audit, không vá
primary. Gate40ms cho nguồn giữ nguyên; auxiliary failure cũng quarantine,
nhưng report phải phân biệt primary/independent/other channel/physics.
Source publish count chưa có trong Gazebo; số message nhận không là delivery ACK.

## Outcomes, thất bại và diễn giải

- Giữ native boundary/scoring100ms riêng; GT-header20ms và dịch+10ms là
  diagnostics, không nội suy body hoặc chọn grid thuận lợi.
- Mỗi full episode/eval phải140tick, đạt marker0,95m và quiet stop2s;
  maxcross-track40mm, estimatorposition50mm/yaw0,05rad, không guidancefault.
- Replay lưu requested1D, obs/nextobs103D, reward, done/timeout; mapped và
  accepted reference nằm riêng trong trace. Partial44tick cuối giữ done=false,
  không ép thành terminal/truncated chỉ vì hết budget.
- Giữ mọi invalid transition attempt, partial checkpoint/replay, log và hash.
  Không dùng full episode của partial job để gọi cả pilot thành công.
- So native vRMSE từng seed/stop với cả B0 và classical; báo path/task/stop
  và hai grids. Đơn vị là fresh run/learner seed, không từng frame. Ba seed
  vẫn là development pilot nhỏ, không bảo đảm generalization.
- Minimum worthwhile effect vẫn null; không tự chấp nhận ngưỡng ứng dụng.
  Không thắng classical hoặc đảo ranking theo grid → unknown/no promotion.
- Không hardware, PPO, DR, tăng budget, đổi queue/chunk/gain/reward sau lỗi.
  Nếu candidate vẫn fail: phân loại lỗi rồi quyết định dừng/chuyển baseline
  hoặc thiết kế acquisition khác bằng protocol riêng; không sửa và retry job này.

## Artifact

Source/config/script/lifecycle fingerprint và upstream manifest được pin
trước job; raw/protocol/job/manifest, per-episode epoch/READY/closure,
traces/physics/parameters, model/replay/identity, final evaluation và review.
Fixture reset/close/cancel/failure chạy offline trước release, không tiêu
thụ physics. Bản GUI hiển thị tiến độ, lỗi và kết quả; không mở lại batch cũ.
