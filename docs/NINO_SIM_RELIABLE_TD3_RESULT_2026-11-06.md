# Kết quả pilot TD3 RELIABLE với lifecycle từng episode

06/11/2026 · [N] Dữ liệu Sim local mới. Không thu thêm dữ liệu thật hoặc điều khiển phần cứng.

## Quyết định

Pilot đóng do lỗi: `'GuidedBackend' object has no attribute 'namespace'`. Giữ 3072 replay rows / 2880 critic updates; mọi slot còn lại đóng. Không retry batch hoặc tự thêm correction acquisition.

## Lỗi evaluator và correction chuẩn bị

Ba learner seed 11/22/33 đều hoàn tất đúng budget. Eval B0 đầu tiên tạo nhầm `baseline.GuidedBackend` thay vì `EpisodeLifecycle`; sau một interval100ms, code đọc `backend.namespace` và lỗi trước khi append trace. Vì vậy **0 evaluation transitions hợp lệ/được lưu**, không có TD3-vs-baseline contrast; mọi9slot còn lại đóng. Raw B0 cho thấy settling0,5s rồi2×50physicssteps, không gọi đây là một evaluation đạt.
Đã chuẩn bị `residual_reliable_evaluation.py` riêng: tạo đúng lifecycle; xác minh namespace ngay sau reset và trước control. 4 regression tests offline đạt cho B0/classical/TD3 và backend sai. Source/job V1 giữ nguyên để pin provenance. Module correction chưa có CLI/job release và chưa chạy thêm Gazebo. Bước kế là eval-only protocol với3final checkpoints đã có, **không train lại**.

## Thay đổi đã triển khai

- Learner mới giữ ABI103D/1D, history5, common±0,005m/s; source stop6/8s xen kẽ. Giữ PI/physics/reward/window/projection và gate40ms.
- Mỗi episode có backend, ROS context/executor, primary log, independent process, GZ partition và namespace mới. Đóng và kiểm instance cũ trước khi tạo mới; timestamp có thể lặp qua launch, không dùng nó làm epoch identity duy nhất.
- RELIABLE chỉ ở primary joint/depth100. Independent BEST_EFFORT chỉ audit; không vá primary. Không sửa scientific module/artifact cha; partial700 cũ vẫn đóng.
- GUI có profile riêng, nút chạy một budget, xem lỗi/kết quả, khóa retry và bảng train/eval/native/header/path/task. TRAIN Studio100D/2D vẫn là ABI khác.

## Budget và bằng chứng

| Đại lượng | Kết quả |
|---|---|
| Job | `failed` |
| Root artifact | `/home/tuanmac/nino_research/sim_reliable_td3_v1/20261106T022633802858Z_sim-reliable-td3` |
| Fingerprint | `659254596ac139709828d9f8fb64fba51c191fafbae857bb25996bbfe887ff46` |
| Manifest SHA256 | `bb6293d9d5e62b1f63646e805e6b67dc9f712fc570ecbe2fa29b75de629ff053` |
| Wall time | 1197.751s / deadline5.400s |
| Artifact hashes | 648 files |
| Source pins trước chạy | 167 files, không đổi |
| Launches | 25 / tối đa34 (24 train; 1 B0 evaluator lỗi) |
| Feedback boundary checks | 9360 (không là số trial độc lập) |
| Canonical payload lệch giữa readers trên stamp chung | 0 |
| Physics requests / retries | 6396 / 0 |
| Physics ACK/completion toàn bộ | True |
| Parameter readbacks | 50, complete=True |
| Estimator causal updates đã kiểm | 15360 |
| Hardware actions | 0 |

### Learner/replay

| Seed | Replay rows | Critic / actor updates | Hoàn tất learner |
|---|---:|---:|---|
| 11 | 1024 | 960 / 480 | True |
| 22 | 1024 | 960 / 480 | True |
| 33 | 1024 | 960 / 480 | True |

Mỗi seed hoàn tất gồm7full episodes và44tick đoạn thứ tám, giữ done=false ở cuối budget. Requested1D/obs103/nextobs103/reward/done/timeout được kiểm với replay; model/targets/optimizers kiểm finite và save–load parity. Không claim restore physics/RNG hoặc cho phép resume.


## Đối chiếu observer

9.360 feedback checks của 24 training launches đều có support hai reader; joint endpoint age tối đa 3 ms ở mỗi reader. Canonical payload trên stamp chung không lệch. Có 33 stamp chỉ ở independent, đều trước task epoch; không gọi toàn luồng loss-free. 15.360 causal estimator updates ở bảng trên thuộc training epochs, không gồm B0 evaluator lỗi.

## Giới hạn kết luận

- [N] Đây là clear-box factory lab với lịch dừng đã biết, chưa mixed floor, contact/caster/gờ/rãnh/cáp mềm, payload hoặc route mới. Không có deploy governor/TD3 trên robot.
- [S] Hoàn tất dưới learner load và nhiều reset hỗ trợ tính tương thích của implementation mới trong pilot. Không tách riêng nguyên nhân QoS khỏi instrumentation/lifecycle/load; lỗi50ms cũ vẫn chưa nhận dạng nguyên nhân.
- [N] Không có upstream source publish counter trong Gazebo. Hai reader cùng dữ liệu không chứng minh không mất mọi message ở source hoặc đường chung; đủ support biên không chứng minh mọi transient đã được giữ.
- [N] Ba learner seeds đã train; thiết kế dự kiến một fresh launch/condition eval nhưng hiện chưa có eval hợp lệ. Không snapshot/exact-state branching hoặc kiểm được toàn bộ RNG vật lý. Frame/tick/boundary không là mẫu độc lập. Chưa có holdout scenario hoặc mức cải thiện ứng dụng được chấp nhận.
- [S] Reward/loss đẹp, nhiều updates hoặc arrival không tự là giảm contact risk. Ranking theo grids phải báo nguyên trạng; benefit vẫn chưa promote.

## Việc kế tiếp có giới hạn

1. Giữ job này đóng; hoàn thiện protocol eval-only riêng pin3final checkpoints và module correction đã test. Không retrain3seed hoặc resume partial700.
2. Chỉ sau protocol eval-only được release mới chạy10fresh launches cùng order đã khóa, optimizer0. Giữ40ms/native/header/task gates; lỗi đóng slot, không retry. Hiện chưa thể xếp hạng TD3/classical vì thiếu eval hợp lệ.
3. Chỉ đề xuất protocol mới khi audit chỉ ra câu hỏi có thể bác bỏ: ví dụ holdout known-stop cho baseline hoặc ablation information/action có kiểm soát. Contact cần H2 riêng; dữ liệu thật dùng SysID theo protocol độc lập, không là prerequisite để phân tích Sim đã có.

**Việc nên làm ngay:** chốt protocol eval-only cho3checkpoints đã hoàn tất, dùng evaluator correction đã qua fixture. Artifact dự kiến: dependency/model hashes,10điều kiện cố định, budget/stop rule; chưa chạy thêm trong turn này. Chỉ thay đổi khuyến nghị nghiên cứu khi có evaluation hợp lệ với cảB0/classical và sensitivity grids; chưa cần tăng timesteps.

## Truy xuất

- [Protocol](NINO_SIM_RELIABLE_TD3_PROTOCOL_2026-11-06.md)
- `src/nino_rl/nino_rl/residual_reliable_td3.py`, `reliable_episode.py`, config/script riêng.
- Audit dẫn xuất: `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_reliable_td3_2026-11-06/analysis.json`; bản GUI `/home/tuanmac/nino_research/sim_reliable_td3_v1/review.json`. Audit nằm ngoài raw sealed manifest, pin SHA manifest đầu vào.
- Software fixture21tests, GUI35tests và evaluator correction4tests đạt; đây không phải60trial robot. Build/GUI visual/source-install verification ghi trong file verification riêng.
