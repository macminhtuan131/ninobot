# Train TD3 recovery trong Gazebo

## Phạm vi hiện hành

Nhánh recovery dùng observation 100 chiều, gồm 20 feature trong 5 mẫu lịch sử. Actor TD3 xuất một residual vận tốc chung cho hai bánh. Follower dùng encoder và gyro để tạo lệnh bám tuyến. Wheel PI xuất torque trong mô phỏng. Ground truth chỉ phục vụ đánh giá.

Campaign nghiên cứu đầu có ngân sách 20.000 transition. Mỗi episode chạy hết nhiệm vụ hoặc kết thúc bằng một failure có phân loại, tối đa 400 bước. Campaign luân phiên sàn sạch, gờ cứng, hõm, mixed và dốc ở stage 0. Nó chưa tăng độ khó và chưa chứng minh tổng quát hóa sang vị trí vật cản mới.

## Các điều kiện để khởi chạy

Readiness kiểm manifest, phiên bản source, world, mẫu nguồn, clock, startup và đóng simulator. Classical baseline không bắt buộc phải thắng bài. Một failure vật lý có dữ liệu hợp lệ vẫn là kết quả nghiên cứu. Thiếu dữ liệu, sai clock hoặc sai source không được đổi thành transition thất bại để đưa vào replay.

Truncation từ backend chỉ hợp lệ khi task ghi `external_cutoff` và backend ghi `time_limit`. Campaign từ chối các truncation do fault, owner intervention hoặc không có chứng cứ timeout trước khi ghi trace và replay. Giới hạn bước do campaign tự tạo vẫn là administrative censor. Timeout hợp lệ giữ bootstrap của TD3.

Hai đường chạy có mục đích khác nhau.

- `recovery_training` giữ các smoke 384 hoặc 640 bước và contract cũ.
- `recovery_campaign` thực hiện training nghiên cứu, readiness và tiếp tục từ checkpoint tương thích.

## Thực hiện campaign

Từ root repository, dùng request JSON có đường dẫn tới một bank mới được chuẩn bị bằng source hiện tại.

```bash
bash src/nino_rl/scripts/recovery_campaign.sh probe --request REQUEST.json --output READINESS_ROOT
bash src/nino_rl/scripts/recovery_campaign.sh check-ready --request REQUEST.json --readiness READINESS_ROOT
bash src/nino_rl/scripts/recovery_campaign.sh run --request REQUEST.json --readiness READINESS_ROOT --output NEW_CAMPAIGN_ROOT
```

Mỗi output phải là thư mục mới. Giữ nguyên phiên cũ khi có lỗi. Không sửa source hoặc config trong lúc campaign đang dùng source đã đóng băng.

Profile nghiên cứu dùng learning rate 0,0003, batch 256, mạng `[256, 256]`, warmup 1.000 transition và replay đủ chứa ngân sách campaign. Đây là cấu hình khởi đầu chưa tune, không phải bộ tham số tối ưu.

## Checkpoint và dung lượng

Checkpoint phải gồm model, optimizer, replay, RNG, scheduler, identity, QC và hashes. Chỉ tiếp tục tại ranh giới episode có dữ liệu hợp lệ. Không dùng checkpoint Goal100 hoặc smoke khác ABI để tiếp tục campaign này.

Để dừng có lưu checkpoint, tạo file `STOP` trong thư mục campaign. Runner hoàn tất episode hiện tại rồi dừng. SIGINT và SIGTERM cũng yêu cầu dừng tại ranh giới đó. Nút dừng tiến trình không phải thao tác điều khiển robot thật.

Để tiếp tục, giữ nguyên các trường request và thêm `resume` là đường dẫn bundle checkpoint. Chạy lại `run` với output mới và cùng readiness. Ngân sách 20.000 bước là tổng của campaign, không cộng thêm 20.000 sau mỗi lần tiếp tục. Identity khác source, task hoặc profile phải bị từ chối.

Campaign phải giữ tối thiểu 2 GiB trống. Việc giảm dữ liệu chỉ áp dụng với artifact do campaign mới tạo, sau QC và ghi summary/hash. Không xóa dataset lịch sử qua thao tác khởi chạy training.

`progress.json` ghi số bước đã xác minh, episode, nhóm địa hình và số cập nhật actor/critic. Thư mục `tensorboard` chứa event training. `latest.json` trỏ tới checkpoint đã đóng bundle. Đọc `result.json` và `job.json` để phân biệt hoàn tất, dừng theo ngân sách và lỗi.

## Đọc kết quả

Số bước và reward cho biết optimizer đang hoạt động. Đánh giá controller cần thêm tỷ lệ hoàn thành, physical goal error, path và heading RMSE, speed RMSE, crossing/recovery, source QC và các can thiệp. Không suy ra TD3 tốt hơn classical từ việc training chạy hết ngân sách.
