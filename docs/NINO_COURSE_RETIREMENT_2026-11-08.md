# Bỏ nhánh rough course — 08/11/2026

## Quyết định và phạm vi

Theo yêu cầu người dùng, nhánh rough/rocky course đã bị loại bỏ, không còn là nhánh chờ tiếp tục. Factory floor và flat là các môi trường được giữ lại; pothole/groove của factory không bị xóa chỉ vì có hình học mặt sàn âm.

Đã xóa **23.071 file, tổng 4.932.445.576 byte (khoảng 4,59 GiB)**, gồm hai lượt xóa có biên bản. Không viết lại lịch sử Git.

Các nhóm đã xóa:

- Generator, world, mesh, config, launch, curriculum và test chuyên biệt rough/rocky.
- Mixed combined course phụ thuộc rough; giữ các workflow combined-flat độc lập.
- Run, checkpoint PPO cũ, snapshot, bản build/install và tài liệu dành riêng cho nhánh bị bỏ.
- Hai ZIP ngữ cảnh nghiên cứu cũ chứa rough và các dataset mô phỏng `foundations_20261011/hardware_sensors_v1/v2`. Hai thư mục này là dữ liệu sim với `rough_diverse_v5`, không phải bag robot thật.

## Gỡ phụ thuộc dùng chung

Trước khi xóa, các phần factory/flat còn dùng được tách thành:

| File | Vai trò |
|---|---|
| `src/nino_description/scripts/terrain_mesh.py` | Tạo mesh/carving dùng cho factory |
| `src/nino_description/worlds/factory_floor_template.sdf` | Template factory độc lập |
| `src/nino_rl/scripts/experiment_processes.py` | Quản lý process và evaluation dùng chung |
| `src/nino_rl/scripts/experiment_assets.py` | Asset, trace và metric helper cho flat |

Factory generator không còn nhập generator rough hoặc đọc world rough. Route loader, training, CLI tuning và monitor đã bỏ nhánh vận hành rough/rocky. Config course cũ bị từ chối rõ ràng trước khi thiết lập ROS/environment.

## Giữ tính tương thích của nhánh hiện tại

Checkpoint TD3 **20k/25k/30k** và các factory asset đã khóa được giữ nguyên. Kiểm tra hash, runtime contract và preflight resume của cả ba checkpoint đạt; chưa thực sự chạy resume hay training mới.

Một số chuỗi lịch sử còn trong file dùng chung được giữ có chủ ý:

- Metadata factory cũ ghi nguồn template rough: đây là provenance khi asset được sinh, không phải phụ thuộc runtime hiện tại. Không sửa JSON đã khóa chỉ để đổi tên nguồn lịch sử.
- Khóa `rough_progress_weight` và helper geometry cũ trong module chung: giữ byte của contract hiện tại; config rough đã bị chặn trước khi sử dụng. Không có course asset hoặc trainer rough được khôi phục.

Các manifest lịch sử từng dẫn đến snapshot rough đã xóa không còn đủ dữ liệu để tái dựng toàn bộ thí nghiệm đó. Không diễn giải chúng thành bộ lưu trữ còn nguyên hoặc sửa kết quả lịch sử. Sinh lại asset bằng generator đã tách cần review/version riêng; không coi là tái tạo byte-identical của asset cũ.

## Kiểm chứng

- **119 test regression + 40 test GUI = 159 test phần mềm được chọn đạt**; đây không phải toàn bộ suite hoặc số lượt chạy robot.
- Build thành công ba package: `nino_description`, `nino_rl`, `nino_pi`.
- Không còn file chuyên biệt rough/rocky trong các cây source/build/install/run/artifact được rà soát; import helper dùng chung còn lại đều phân giải được.
- Fingerprint engine hiện tại và factory sources đã khóa không đổi so baseline trước khi xóa.
- Không chạy Gazebo, training, SSH hoặc tác động phần cứng trong công việc này.

Quyết định controller không thay đổi: giữ classical cho envelope **clear floor / planned stop** hiện đã đánh giá; việc xóa course không tạo bằng chứng TD3 tốt hơn baseline.

## Biên bản

Inventory trước xóa có đường dẫn, kích thước và hash; kết quả xóa, kiểm contract/checkpoint, XML test và build log nằm trong [thư mục audit](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/rough_retirement_2026-11-08/).
