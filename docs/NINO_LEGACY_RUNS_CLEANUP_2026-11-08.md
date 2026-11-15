# Dọn các run lịch sử trong `rl_runs` — 08/11/2026

## Kết quả

Theo yêu cầu chỉ giữ dữ liệu phục vụ định hướng hiện tại, đã xóa **23.850 file/symlink**, tổng kích thước file thường **10.136.685.157 byte ≈ 9,44 GiB**, và dọn **138 thư mục cấp đầu**, bao gồm thư mục trống còn lại từ các course đã bỏ.

Đây là lượt dọn riêng trong `/home/tuanmac/ninorobot/rl_runs`, không cộng lại các lượt dọn episode, cache hoặc rough trước đó.

Các run bị loại thuộc các workflow PPO, flat tuning/Optuna, contact governor, cadence/logger audit và smoke cũ tháng 9–10. Chúng không còn là đầu vào runtime của nhánh Sim/TD3 tháng 11 hiện tại. Không chọn xóa theo kết quả tốt/xấu; toàn bộ run thuộc phạm vi nghỉ dùng được xử lý như nhau.

## Cơ sở giữ/xóa

| Nhóm | Xử lý và lý do |
|---|---|
| Run cũ trong `rl_runs` | Xóa raw episode, model/replay cũ, snapshot, trace và log; không còn dùng cho định hướng đang làm |
| Dữ liệu Sim tháng 11 trong `~/nino_research` | Giữ nguyên; đây là nơi lưu các nhánh hiện tại, gồm PI validation và prestop authority |
| Checkpoint TD3 20k/25k/30k | Giữ nguyên bundle và replay; hash/runtime và preflight resume đạt |
| Bag thật, firmware, source/config đang dùng | Giữ nguyên; không thuộc phạm vi xóa |
| `rl_runs/COLCON_IGNORE` | Giữ để colcon không quét dữ liệu như source package |
| Ba thư mục `.governor_*_budget_claims` | Giữ các tombstone ngân sách nhỏ; ngăn vô tình mở lại budget đã tiêu, không phải run hoặc checkpoint được giữ để tiếp tục |
| Báo cáo lịch sử nhỏ | Sao chép 141 aggregate report, tổng 4.222.083 byte, vào hồ sơ audit trước khi xóa |

Rà soát các file JSON/YAML/Python/Markdown và symlink trong `~/nino_research` không tìm thấy tham chiếu tới `rl_runs/`. Đây là kiểm tra phạm vi phụ thuộc của dữ liệu hiện tại, không phải bằng chứng mọi CLI lịch sử còn có thể chạy khi không có archive cũ.

## Gỡ phụ thuộc kiểm thử

Ba test trước đây đọc dữ liệu trực tiếp từ run cũ. Đã chuyển bốn đầu vào nhỏ sang `src/nino_rl/test/fixtures/legacy_flat/` và ghi đường dẫn gốc/hash trong biên bản:

- Pilot config và contract cũ để kiểm việc từ chối resume optimizer khi đổi contract.
- Văn bản `ros_env` cũ để kiểm phép chèn trace không đổi phần còn lại.
- World 22 mm cũ để kiểm geometry generator.

Đây chỉ là fixture kiểm thử, không phải bản sao để khởi chạy lại experiment. Không thay thuật toán, gain, reward, observation hoặc action contract của nhánh đang dùng.

## Kiểm chứng sau xóa

- **383 file được bảo vệ giữ nguyên SHA256**, bao gồm ba checkpoint, các source/config của nhánh hiện tại, báo cáo gần đây và bag thật đã có trong inventory.
- **51 test được chọn đạt**, gồm các test fixture vừa chuyển và các nhóm storage/training panel/dashboard/tích hợp Studio. Không gọi đây là chạy toàn bộ test suite.
- Checkpoint **20.000/25.000/30.000 bước** đều đạt kiểm bundle/hash/runtime và preflight resume; không thực sự resume, load để train hoặc cập nhật optimizer.
- Không còn dữ liệu run thuộc phạm vi xóa trong `rl_runs`; giữ marker và tombstone nói trên.
- Không chạy training, Gazebo, SSH hoặc điều khiển phần cứng trong lượt cleanup.

## Giới hạn lưu trữ

Các báo cáo kết quả và tài liệu lịch sử còn được giữ không đồng nghĩa raw archive vẫn nguyên vẹn. Những link lịch sử tới run đã xóa sẽ không còn mở được. Không thể tái kiểm toàn bộ metric/raw manifest của các run này từ các summary còn lại; checkpoint mới không khôi phục được raw cũ. Không sửa manifest hoặc kết quả lịch sử để che việc thiếu dữ liệu.

Quyết định này thay thế phần **giữ `rl_runs` lịch sử** trong [báo cáo dọn project trước đó](NINO_PROJECT_CLEANUP_2026-11-08.md). Không tự áp dụng chính sách xóa này cho các job tương lai hoặc cho `~/nino_research`.

## Biên bản

[Hồ sơ cleanup](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/rl_runs_cleanup_2026-11-08/) chứa inventory/hash trước xóa, biên bản xóa, báo cáo nhỏ giữ lại, provenance fixture, kiểm bảo toàn, kiểm checkpoint và XML/log test. Không lưu thêm bản sao raw lớn.
