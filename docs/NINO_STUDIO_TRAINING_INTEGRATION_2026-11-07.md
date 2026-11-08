> **Cập nhật mới07/11:** Studio mặc định common103D/1D; smoke64 đạt48critic/24actor updates. Pilot20k chưa chạy do dung lượng. [Chi tiết](NINO_COMMON_STUDIO_PILOT_2026-11-07.md). Các đoạn100D/2D dưới đây là legacy.

# Nino Studio — training trong cùng ứng dụng và cách chọn tham số TD3

07/11/2026. Thay đổi GUI; không chạy training/Gazebo hoặc robot thật trong bước này.

## Một cửa sổ Studio

Studio có tab cấp cao **Train TD3 · Sim**, dùng lại đúng một training panel
và một runner. Không phải mở ứng dụng training riêng. Shortcut
`td3_training_gui` cũ cũng mở Studio tại tab training, giữ tương thích
`--output`. Có thể mở Studio trực tiếp bằng `mode_gui --train`.

Trong tab này:

1. Chọn map fixture, parameter profile, timesteps học thêm, seed và wall cap.
   Form mặc định research h5 và20.000bước như đề xuất khởi đầu có thể sửa;
   không tự chạy hoặc coi20.000bước là đủ hội tụ.
2. Bấm Smoke để kiểm pipeline bằng model mới64bước, hoặc Train với ngân sách
   nhập trong form. Không có job tự chạy khi mở tab/chọn profile.
3. Theo dõi quá trình/lỗi, kết quả và checkpoint trong cùng tab; mở TensorBoard.
4. Chọn checkpoint bundle đầy đủ để resume cùng contract/profile; số bước
   nhập là số học thêm. Resume không khôi phục exact-state của Gazebo.
5. Nút xem tham số điều hướng tới editor hiện có trong Studio và chọn cùng
   profile. Editor lưu draft để review, không áp âm thầm vào job đang chạy.

Recorder và training vẫn có vòng đời riêng. Training chia sẻ busy/close
coordination với Studio; đóng cửa sổ khi training/TensorBoard còn hoạt động
phải chờ cleanup. Chế độ demo không khởi chạy smoke/train; local training
không yêu cầu Pi/agent kết nối.

### Giới hạn contract phải nhìn thấy

Trainer tự nhập timesteps hiện là **V3/history5/100D/2D**, common+differential
residual, trên controlled factory clear-box hoặc gờ6mm. Đây không phải toàn
factory mixed map, và không phải runner common103D/1D đã dùng cho checkpoint A.
GUI ghi rõ khác biệt này. Không chuyển A sang resume bằng cách bỏ qua ABI.
Việc tích hợp GUI không đổi engine, reward, action scale hoặc release của các
experiment đã đóng. Pilot103D/1D tiếp theo vẫn cần protocol/version riêng.

Studio chỉ quét hồ sơ benchmark lịch sử khi mở trang benchmark; trang này
giữ trạng thái chưa xác minh trước khi kiểm. Refresh training dùng catalog
tham số đã đọc, không parse YAML theo nhịp GUI. Khi yêu cầu chạy, catalog
được đối chiếu lại để chặn cấu hình đã đổi so với preview. Timer được dừng
khi cửa sổ hoàn tất đóng.

## Có cần tune tham số không?

Cần chọn cấu hình phù hợp và có thể phải tune sau pilot. **Không cần tìm bộ
hyperparameter tối ưu trước khi được train lượt đầu.** Tách ba nhóm:

| Nhóm | Việc cần làm |
|---|---|
| Contract/control | Chốt observation/history/normalization, residual scale, projection, rate, baseline và reward trước phép so sánh; thay ABI cần checkpoint mới |
| Ngân sách học | Chọn warmup, timesteps, replay, checkpoint/eval cadence và wall cap; kiểm số update thật thay vì chỉ đếm interactions |
| Hyperparameter | Bắt đầu từ profile cố định; sau pilot mới khảo sát nhỏ LR, exploration noise, batch/update ratio hoặc mạng nếu có triệu chứng cụ thể |

Profile hiện có trong `src/nino_rl/config/td3_parameter_profiles.yaml`:

| Tham số | Smoke h5 | Research h5 — cấu hình khởi đầu, chưa tối ưu cho Nino |
|---|---:|---:|
| LR actor/critic dùng chung | 0,0003 | 0,0003 |
| gamma / tau | 0,99 / 0,005 | 0,99 / 0,005 |
| batch / replay | 32 / 2.048 | 256 / 1.000.000 |
| learning_starts | 16 | 10.000 |
| network | [32,32] | [256,256] |
| exploration sigma | 0,1 | 0,1 |
| policy_delay / target noise / clip | 2 / 0,2 / 0,5 | 2 / 0,2 / 0,5 |

Đây là cấu hình project, không là bộ thông số được chứng minh tốt nhất.
Adapter hiện dùng chung LR actor/critic; editor từ chối hai giá trị khác
nhau thay vì giả vờ áp độc lập.

**Warmup quan trọng:** với fresh research profile,10.000timesteps và
learning_starts10.000 chỉ thu dữ liệu trước khi bắt đầu học. GUI cảnh báo
và chặn nút Train cho ngân sách không còn bước sau warmup. Ví dụ20.000bước
để lại tối đa10.000bước sau warmup có thể cập nhật; không bảo đảm hội tụ.
Smoke vẫn dùng profile smoke riêng. Khi resume, kiểm global steps đã có để
không tính lại warmup từ zero. Worker vẫn xác minh toàn bundle trước load.

### Thứ tự đề nghị cho Nino

1. Giữ baseline/controller và contract ổn định cho một pilot TD3 có ngân sách.
2. Dùng một cấu hình khởi đầu; kiểm actual optimizer updates, exploration/
   action coverage, saturation, reward components và deterministic evaluation.
3. Tune một nhóm nhỏ dựa trên triệu chứng, giữ seed/condition đối chứng và
   tập đánh giá tách biệt; không dùng training return đơn lẻ chọn controller.
4. Kết luận hội tụ/hiệu quả cần bằng chứng từ curves và evaluation phù hợp.
   Ki0,15 validation không là điều kiện bắt buộc để train với baseline Ki0,10.

Nguồn đối chiếu ngày07/11/2026: [SB3 TD3](https://stable-baselines3.readthedocs.io/en/master/modules/td3.html)
mô tả ý nghĩa warmup, noise và LR dùng chung;
[SB3 RL tips](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)
khuyến nghị thử nghiệm định lượng, nhiều lần chạy và đánh giá riêng. Những
nguồn này không xác nhận bộ tham số trên tối ưu cho robot Nino.

## Kiểm chứng thay đổi GUI

- 42 tests đạt: tích hợp tab/alias, một panel/runner, khóa recorder/training,
  close/cancel, tham số/warmup/resume, phát hiện catalog đổi, benchmark và
  luồng authority bằng demo subprocess. Đây không là kiểm chứng hardware.
- Build `nino_pi` đạt, source/install khớp. Mở alias thực trong chế độ demo
  cho đúng một Studio window tại tab training, không tạo thư mục job.
- Đã xem ảnh offscreen1280×1100; smoke/train/dừng nằm trong viewport.
- Checkpoint A và fingerprint Sim frozen giữ nguyên. 0 training/Gazebo/hardware
  actions mới. QA tại workspace `artifacts/studio_training_integration_2026-11-07/`.
