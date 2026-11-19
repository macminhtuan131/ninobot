# Training TD3 sàn sạch và gờ ngày 18/11/2026

## Cập nhật chạy song song

Theo yêu cầu mới, clean tiếp tục từ tiến độ hiện có và gờ chạy trong scope
độc lập. [Cấu hình isolation và kiểm chứng song song](RECOVERY_PARALLEL_TRAINING_2026-11-18.md)
là hiện trạng mới. Các mô tả queue tuần tự bên dưới là lịch sử; queue đó đã
handoff task gờ để tránh chạy trùng.

## Phạm vi

Hai campaign độc lập, mỗi campaign có ngân sách 50.000 transitions. `clean`
dùng sàn sạch; `short_obstacle` dùng gờ capsule cứng trong factory floor.
Model, replay, RNG và checkpoint tách riêng. Cả hai chạy tuần tự qua khóa
Gazebo chung để tránh tranh ROS domain và simulator.

Đây là research stage 0, mỗi task dùng một layout development đã khóa và
một seed training. Cruise 0,2 m/s, tuyến thẳng 4 m, physics 1 ms, policy
100 ms. Gờ thuộc khoảng đường kính danh nghĩa 4–6 mm và góc ±0,35 rad.
Không coi kết quả trên layout này là bằng chứng tổng quát hóa.

Observation có 100 chiều, bằng 20 features × history 5. Actor xuất một
residual vận tốc chung, biên độ ±0,02 m/s. Causal follower điều khiển yaw.
Reference qua projection và shaping trước PI vận tốc bánh xuất torque
trong Gazebo. Truth phục vụ reset và đánh giá, không làm observation actor.

Pothole, mixed và dốc vẫn có trong project. Sửa startup và kiểm replay dùng
chung cho năm family. Contact của ba family còn lại chưa được qualification
bởi hai campaign này. Không có lệnh lên robot thật.

## Các lỗi có bằng chứng đã sửa

### Request bắt buộc trộn cả năm family

Parser hiện cho phép subset không rỗng, không trùng và chỉ chứa family đã
biết. Default vẫn gồm năm family. Readiness, assignment và identity theo
đúng subset đã chọn.

### Bootstrap phụ thuộc lịch sử startup bị thiếu

Hai raw logs có gap wheel 68 ms trước drive publication. Reliable subscriber
đã được dùng. Đổi QoS không thể tạo lại source chưa quan sát.

Sau khi drive ACK zero và robot đạt quiet, backend thực hiện một challenge
dịch model 20 mm rồi trả về declared pose. Mỗi leg chỉ gửi một SetEntityPose.
Fresh truth phải chứng minh pose thực sự đổi. No-op ACK bị từ chối.
Ngưỡng source 40 ms, sai số pose 1 mm và yaw 1 mrad được giữ.

### Twist của khoảng reset bị dùng để kiểm đứng yên

Queue đầu ngày 18/11 dừng sau 272 transitions hợp lệ, tại lần reset thứ hai.
First post-SetPose truth báo speed norm 2,062355 m/s khi bánh gần zero.
Backend nhận giá trị twist từ simulator; không tự tính đạo hàm ở callback.
Khoảng pose thay đổi do reset không là bằng chứng vận tốc vật lý đứng yên.

Bản sửa xác nhận application trong 20 ms đầu. Nó giữ raw twist nhưng đánh
dấu không dùng twist đó để kết luận quiet. Một bước 20 ms tiếp theo bắt buộc
truth, wheel và drive ACK mới hơn ranh giới application, pose vẫn đúng và
đầy đủ điều kiện quiet. Mỗi leg có hai phase cố định, không retry SetPose,
không chọn một suffix yên thuận lợi và không nới gate.

Epoch vẫn là stamp truth đầu tiên chứng minh final return pose. Mẫu quiet
đến sau không được dời epoch. Thu thêm prefix thật trước khi task bắt đầu.

### Bootstrap bỏ gyro trước wheel mới đầu tiên

Estimator hiện khởi tạo tại imposed epoch, dùng wheel sample thật tại hoặc
trước epoch với support age tối đa 40 ms. Gyro sau epoch nhưng trước wheel
mới vẫn được tích phân với wheel support nhân quả đó. Thiếu support bị từ
chối. Không tạo wheel sample giả từ command hoặc truth.

Default legacy spawn epoch còn khai báo unsupported prefix riêng. Luồng
physical reset hiện hành bắt buộc causal support tại epoch và báo integration
stamp, wheel support stamp để audit.

### Trạng thái queue lỗi còn hiển thị progress cũ

Queue mới đọc progress cuối sau khi child kết thúc. Task sau chỉ bắt đầu nếu
task trước đủ 50.000 verified replay rows, có actor và critic updates, source
QC đạt, checkpoint qualified và lifecycle đóng sạch.

## Rà soát ngữ nghĩa học

Giữ observation, reward, history, learning rate và action scale trong lần sửa
startup này. Không có bằng chứng từ audit yêu cầu retune đồng thời chúng.

Replay giữ requested scalar action của TD3. Sau mỗi store, kiểm actual SB3
observation, next observation, action, reward, done và timeout. Reference sau
projection và drive telemetry được ghi riêng.

Physical task timeout là terminal. Cutoff hành chính có right censoring và
bootstrap tương ứng. Fault source hoặc ownership không được tính là physical
success. Residual không làm trôi baseline state hoặc thay yaw bằng common
wheel delta. Resume yêu cầu identity phù hợp và khôi phục optimizer, replay,
RNG cùng lịch episode.

## Kiểm chứng đã hoàn tất

- 199 source tests đạt, gồm 28 reset tests và 25 startup tests.
- 3 queue tests đạt, task kế bị chặn khi child lỗi, partial hoặc đóng không sạch.
- Sáu lần khởi tạo Gazebo độc lập đạt, ba clean và ba short_obstacle.
- Readiness mới `_04` cho cả hai task đều task_success, measurement và source
  QC đạt, lifecycle đóng sạch.
- Kiểm 68/68 manifest hashes và 1.656 boundary checks.
- Tái tính startup từ raw khớp counts và pose đã lưu. Prefix unsupported bằng
  zero trong hai probe mới.
- Raw startup cũ thiếu wheel vẫn bị từ chối, không bị sửa thành dữ liệu hợp lệ.
- Review độc lập bằng gpt-6.1-terra không còn tìm thấy blocker trong reset,
  bootstrap và queue sau các correction. Review không thay thế runtime evidence.
- `git diff --check` đạt và knowledge graph đã cập nhật.

Các probe dùng residual zero, không cập nhật optimizer. Chúng không chứng minh
TD3 học tốt hơn baseline.

## Campaign mới đang chạy

Service `nino-td3-clean-obstacle-50k-20261118-02.service` đã được khởi động.
Clean chạy trước; short_obstacle xếp sau. Bộ đếm thực được ghi liên tục trong
`progress.json` và `queue.json`. Ngân sách 50k không phải số steps đã đạt.

Đã mở lại checkpoint boundary 1.083 bước và load model cùng replay thật.
Đối chiếu đủ 1.083 rows với trace episode khớp observation, next observation,
requested action, reward và done. Checkpoint có 83 critic updates, 41 actor
updates, qualified và resumable; source identity khớp, inference 100D → 1D
hữu hạn. Receipt ở `training_checkpoint_verification.json`.

Đã đối chiếu thêm chuỗi requested → projection → final reference, reward và
history trên 272 hàng episode đầu; 244 hàng có accepted residual khác zero.
Đây là bằng chứng action đi qua pipeline, chưa là lợi ích so baseline.

Các checkpoint boundary này có thể được xoay vòng theo retention. Receipt
giữ kết quả kiểm đã thực hiện; để resume dùng bundle qualified hiện còn.

TD3 dùng learning rate 0,0003, warmup 1.000, batch 256, replay 50.000,
mạng 256 × 256, policy delay 2. Clean seed 1511, obstacle seed 2511.

Checkpoint ghi tại boundary episode, giữ các milestone đi qua mỗi 5k và
hai boundary mới nhất, cap 12 bundle. Mốc boundary có thể vượt nhẹ 5k.
Episode cuối bị cutoff tại đúng tổng ngân sách 50.000.
Mỗi task có cap 24 giờ, tối đa 1.000 launches, disk reserve 2 GiB và raw
retention cap 4 GiB. Summary và hash được giữ khi successful raw được prune.
Failures giữ riêng. Không tự retry một campaign đã lỗi.

Queue đầu `recovery100_clean50k_20261118_01` đã đóng failed tại 272 bước.
Checkpoint warmup của nó được giữ, actor và critic có zero updates.
Không resume checkpoint khác source identity vào campaign mới.

## Đường dẫn theo dõi

Workspace artifacts hiện hành:

`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/clean_obstacle_50k_20261118_reset3`

- `run_pair.py` quản lý hai campaign.
- `clean_request.json` và `short_obstacle_request.json` khóa ngân sách.
- `queue.json` ghi process, progress cuối và lỗi.
- `readiness_verification.json` là kiểm chứng hash, source và startup replay.
- `verify_reset_restarts.py` và `verify_readiness.py` tái chạy phép kiểm.
- `decisions.tsv` ghi quyết định và bằng chứng.

Root dữ liệu hiện hành:

- `~/nino_research/recovery100_pair_inputs_20261118_04`.
- `~/nino_research/recovery100_reset_restarts_20261118_04`.
- `~/nino_research/recovery100_pair_readiness_20261118_04`.
- `~/nino_research/recovery100_clean50k_20261118_02`.
- `~/nino_research/recovery100_obstacle50k_20261118_02`.

Output gờ được tạo khi task bắt đầu. Khi output chưa có, đọc queue để phân biệt
queued với lỗi recorder.

```bash
systemctl --user status nino-td3-clean-obstacle-50k-20261118-02.service
cat ~/nino_research/recovery100_clean50k_20261118_02/progress.json
cat ~/nino_research/recovery100_obstacle50k_20261118_02/progress.json
```

File `STOP` trong output task yêu cầu pause ở boundary có checkpoint. File
`STOP` trong thư mục workspace artifact ngăn mở task kế.

Sau training, cần đánh giá checkpoint với classical trên cùng điều kiện và
giữ test layout riêng. Đủ steps hoặc reward tăng chưa chứng minh giảm rung,
giảm slip, bám đường tốt hơn hay sim-to-real thành công.

## Nguyên tắc đã dùng

Fix Root Causes sửa việc dùng twist ở khoảng teleport và thời điểm bootstrap.
Attack the Premise loại giả định lịch sử wheel từ spawn luôn đầy đủ.
Model the Domain tách application evidence khỏi quiet evidence và khóa family
trong request. Prove It Works yêu cầu live restarts, full probes và actual
training counters. Build the Lever tạo các script tái kiểm raw, manifest và
startup thay cho chỉ đọc summary.
