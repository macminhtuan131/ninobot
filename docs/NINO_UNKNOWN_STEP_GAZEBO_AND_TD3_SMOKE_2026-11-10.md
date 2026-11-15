# Goal100: Gazebo integration và smoke TD3 đã hoàn tất

Ngày 10/11/2026. Theo yêu cầu làm tiếp tới trước lượt train dài.

## 1. Kết luận

Đã nối task **gờ không biết trước → bám đường → goal → dừng** với Gazebo
Harmonic, robot Nino/caster thật trong URDF và velocity PI mô phỏng. Đã chạy
baseline, optimizer smoke và một lượt deterministic. **Chưa train research
dài, chưa chứng minh TD3 tốt hơn classical và chưa triển khai hardware.**

| Kết quả thực tế | Giá trị |
|---|---:|
| Gazebo fresh launches | 7 / cap 8 |
| Native task transitions | 970 |
| B0 task success | 2/3; một path failure được giữ |
| TD3 smoke transitions | 384 |
| Critic / actor updates | 368 / 184 |
| Complete train episodes | 2/2 thành công; đoạn cuối 51 bước censored |
| Replay audit | 384/384: obs, next obs, requested action, reward, done/timeout |
| Deterministic development evaluation | 1 lượt thành công, 154 bước / 15,4 s |
| Manifest files đối chiếu | 238/238 khớp |
| Observer closures / PI readbacks | 7/7 / 7/7 |
| Hardware / long-training jobs mới | 0 / 0 |

Root: `~/nino_research/unknown_step_short_20261110_v1/`.

## 2. Task và dữ liệu đã khóa

- Route thẳng `(0,0) → (2,0)`, cruise 0,20 m/s; source warmup0,5s; deadline25s.
- Một cylinder cứng nằm ngang, Ø6mm, góc0; sàn box, friction cấu hình1.
  Không phải rãnh/hõm/dây mềm hoặc mọi layout factory.
- Development: sàn sạch, gờ x0,65m và1,05m. Validation x1,25m và test x1,50m
  được tạo/khóa offline, **chưa chạy hoặc dùng train/chọn checkpoint**.
- Actor chỉ nhận100D =20feature×5frame ở10Hz, common residual1D ±0,02m/s.
  Không có ba feature planned-stop; không nhận vị trí/chiều cao/metadata gờ.
  Follower dùng causal wheel/IMU estimator và đường/goal đã biết.
- GT/contact/geometry ở nhánh chấm/audit riêng. Metadata layout chỉ để lưu
  provenance và vẽ scene cho người vận hành, không vào observation.
- PI đọc lại Kp0,3/Ki0,1,500Hz, torque cap4Nm; torque residual bằng0 trong
  toàn bộ970transition. Không chỉnh gain/current hoặc copy sang hardware.

Conservative full collision envelope được trích từ expanded URDF/mesh và
bound toàn bộ góc quay của các joint continuous, gồm caster sweep. Frame
`base_footprint`, nominal bounds khoảng `[-0,190;-0,1935;-0,02589]` tới
`[0,310;0,1935;0,2525]`m. Đây là bound bảo thủ của **model sim**, không phải
geometry đo robot thật. Mỗi loaded URDF được đối chiếu với bank trước task.

## 3. B0 và một correction ở gate mở smoke

| Layout | Kết quả | Path max | Thời gian tới outcome |
|---|---|---:|---:|
| Clear | Tới goal, dừng2s | 0,117mm | 17,1s |
| Gờ x0,65 | Tới goal, toàn robot qua gờ, dừng2s | 7,679mm | 17,1s |
| Gờ x1,05 | Đã qua gờ, **path violation** | 40,564mm >40mm | 9,0s |

Cả ba lượt có QC hợp lệ. Stage baseline nguyên gốc vẫn **failed**, không
đổi thành3/3pass, không hạ gate4cm hoặc xóa trajectory lỗi.

Gate ban đầu yêu cầu B0 thành công ở mọi layout trước optimizer smoke đã
gộp chất lượng controller với validity của environment. Sau review, amendment
riêng chỉ cho phép **software smoke** khi cả ba dữ liệu hợp lệ, clear và ít
nhất một gờ đạt physical goal/stop, và giữ failure còn lại. Điều này không
promote controller hoặc đổi success definition. Không chạy lại B0. Reward,
history, action bound, physics và PI không đổi; một gate correction được ghi
trong ledger, không mở vòng retry/tuning.

Protocol gốc và amendment:
`src/nino_rl/config/unknown_step_short_integration_v1.json`,
`unknown_step_short_gate_amendment_v1.json`.

## 4. Smoke TD3 và giới hạn kết luận

Smoke dùng profile `nino_td3_smoke_h5_v1`: MLP32×32, warmup16, replay2048,
LR0,0003, batch32. **Không phải** research h5 MLP256×256/warmup10k.

- Episode train gờ sớm:172steps, success; gờ muộn:161steps, success.
- Đoạn sàn sạch cuối51steps chưa terminal: giữ censored, không tính success.
- Checkpoint384 được load lại cùng replay; counter, networks finite và toàn
  bộ384 replay rows khớp. Requested action khác accepted correction và
  wheel target; chúng không bị đồng nhất khi ghi/đánh giá.
- Deterministic dev_late:154steps, goal error18,47mm, path RMS4,293mm,
  path max8,321mm, toàn robot clear và quiet2s. Không optimizer lúc eval.

Một baseline late thất bại và một TD3 late thành công **chưa chứng minh
causal benefit**: fresh launch không phải cùng trạng thái vật lý; chỉ một
learner seed, ít lượt và evaluation là development. Không so RMS của9s
trajectory thất bại với15,4s trajectory thành công như một effect estimate.
Không suy slip/rung tốt hơn từ reward/arrival.

## 5. GUI và trainer đã chuẩn bị cho bước dài

Trong Studio, tab **Train TD3 · Sim** có engine mới:
**Gờ không biết · Goal100D/1D · tới goal, không lịch stop**.

- Nút **Điền cấu hình Goal100 · research20k · chưa chạy** chỉ điền form.
- Smoke của engine mới là384steps, không phải64steps của engine lịch sử.
- Form hỗ trợ timesteps, seed, checkpoint interval, TensorBoard, kết quả và
  resume đúng identity. Common103 hoặc smoke MLP32 không đổi thành research
  MLP256 khi resume; lượt research đầu phải **fresh**, resume bỏ chọn.
- Dispatcherv3 giữ các dispatcherv1/v2 nguyên trạng. Worker Goal100 chỉ bắt
  đầu khi có request bấm Train/CLI và qualification/bank/source/disk hợp lệ.
- Live observer nhận worker mới. Map dùng đúng world của episode đang đọc;
  khi chuyển evaluation, scene và vệt xe cùng đổi. Trường metric task cũ
  không có ở task goal được giữ unknown, không bịa velocity ISE.

Long worker đã kiểm software, request/GUI và save-load TD3 synthetic; chưa
chạy end-to-end research job dài. Gazebo smoke ở trên kiểm backend/goal task
và optimizer qua short runner; không đánh đồng hai mức bằng chứng.

**117 software tests đạt**, gồm goal/clock/geometry/leakage, Gym interface,
backend adapter, TD3 save-load synthetic, GUI/dispatcher/live/map và evidence
badges. Chúng không phải117rollout hoặc117episode train.

## 6. Điểm dừng hiện tại: cần lượt research dài có request riêng

Cấu hình đề xuất đã chuẩn bị, **chưa chạy**:

| Mục | Đề xuất |
|---|---|
| Engine / task | unknown_goal100_v1 / unknown_step_dev_bank_v1 |
| Bắt đầu | Fresh; không resume384 hoặc common10350k |
| Profile | nino_td3_research_h5_v1, MLP256×256, replay100k |
| Steps / warmup | 20.000 / 10.000 |
| Seed | 11, một pilot nghiên cứu; chưa là multiseed confirmation |
| Checkpoint | Mỗi5.000bước và cuối / khi dừng ở boundary hợp lệ |
| Wall cap | 240phút, giới hạn đề xuất, không là dự báo thời gian chạy |
| Eval sau train | B0/TD3 trên3development layouts; val/test giữ riêng |

Preflight request này đạt: ước tính cần10,64GiB trống gồm reserve, quan sát
còn15,47GiB lúc kiểm. Đây là ước tính, không là upper bound; runtime vẫn
dừng nếu chạm reserve. File request/preflight ở artifact bên dưới, không có
job research được tạo từ thao tác chuẩn bị này.

Lượt này giữ LR/history/action/reward đã khóa để xem việc tối ưu thật có
tạo policy hữu ích. Sau20k đọc success/failure, path/time, action/projection,
source QC và critic trước khi quyết định thêm budget/seed/ablation. Không tự
tăng sample size, đổi reward hoặc chạy validation/test để tìm winner.

Nếu đo lường hỏng: dừng job/giữ checkpoint, không hạ coverage. Nếu policy
không cải thiện: phân tích rollout/action authority và baseline; cân nhắc
tuning follower cổ điển, không mặc định tăng steps hoặc thêm thuật toán.

**Không có thao tác robot thật cần làm ở mốc này.** Đã dừng trước research20k.

Artifact:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/unknown_step_gazebo_integration_2026-11-10/`.
