# Rà soát và dọn project Nino — 08/11/2026

## Kết quả

Đã xóa **13.086 file**, tổng kích thước **3.833.120.831 byte ≈ 3,57 GiB**.
Đây là lượt dọn project riêng, không cộng lại 6,76 GiB raw episode đã dọn
ở lượt trước. Ổ đĩa còn khoảng **19,7 GiB trống** sau lượt này; dung lượng
trống có thể thay đổi bởi các tác vụ khác trên máy.

| Nhóm đã xóa | File | Dung lượng file | Cơ sở |
|---|---:|---:|---|
| Log build/test colcon cũ trong repo | 1.938 | 2,184 GiB | Output sinh lại được; giữ các target `latest_build`, `latest_test`, `latest_test-result` |
| `logger_all.log` DEBUG trong artifact build cũ | 39 | 0,975 GiB | Không thuộc artifact có manifest đóng dấu; không có tham chiếu JSON tới tên file; giữ stdout/stderr/streams và báo cáo build |
| Bytecode Python có source tương ứng | 11.093 | 0,214 GiB | Chỉ xóa `.pyc` trong `__pycache__`, có `.py` tương ứng; giữ thư viện và môi trường ML |
| Cache pytest | 12 | 0,10 MB | Cache có thể tạo lại, không là kết quả nghiệm thu |
| `d.zip`, `src.zip`, `rl_training.log` ở root repo | 3 | 49,08 MiB | Gói nhập dự án/log lịch sử; không có tham chiếu chính xác từ source/docs; bản làm việc trùng blob trong Git |
| Gói tải compiler `arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi.tar.xz` | 1 | 152,45 MiB | Đã đối chiếu checksum; compiler giải nén vẫn hoạt động |

Không dùng thời gian sửa file hoặc việc thiếu một câu `import` làm bằng
chứng duy nhất để xóa source. Một module còn có thể là CLI, ROS launch,
plugin, baseline lịch sử hoặc đầu vào kiểm thử/contract.

## Phạm vi rà soát

- Repo `/home/tuanmac/ninorobot`: kiểm kê dung lượng và loại file, package,
  entrypoint, source/config/report, archive và output sinh tự động.
- Workspace `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi`:
  firmware, toolchain, raw bag, artifact build và các manifest.
- Ba bundle checkpoint hiện tại dưới `~/nino_research/td3_studio`.
- Đọc AST của **615 file Python**, không có lỗi parse; nhận diện **10 package
  ROS** và **26 entrypoint console**. Đây là rà soát phục vụ cleanup,
  không phải chứng minh đầy đủ mọi nhánh code đều được thực thi.

## Các nhóm giữ lại có lý do

| Nhóm | Vì sao còn cần |
|---|---|
| Checkpoint 20k/25k/30k và replay | Tiếp tục learner và đối chiếu offline đã chốt |
| Raw bag robot thật | Bằng chứng sensor/command; không thể tạo lại bằng chạy sim |
| Source, test, launch, config và các package linorobot2 | Có entrypoint/phụ thuộc hoặc còn trong danh sách package hiện tại; chưa có bằng chứng chắc để loại bỏ |
| `collection_runtime.zip` | Còn được setup, collection deploy, build helper và test sử dụng |
| `docs`, source snapshot, protocol, manifest và artifact nghiên cứu | Provenance, bằng chứng thất bại/unknown và các kết luận đã báo cáo |
| `rl_runs` lịch sử | Nhiều run được báo cáo và công cụ đánh giá tham chiếu; không coi toàn bộ run cũ là rác |
| `.venv`, overlay `build`/`install` hiện tại | Môi trường ML/ROS và GUI đang dùng; chỉ dọn cache sinh lại được |
| Firmware nguồn, binary và compiler giải nén | Giữ khả năng đọc/build và đối chiếu firmware; không flash hay thay firmware |

## Ngăn phát sinh file dư

1. Thêm `COLCON_IGNORE` tại `docs/`, `artifacts/`, `rl_runs/` để colcon
   không đi sâu vào dữ liệu/kết quả như thể đó là source ROS package.
   Danh sách **10 package trước/sau giống hệt nhau**.
2. Lượt `colcon list` kiểm tra sinh log DEBUG khoảng **29 KB**, so với
   khoảng **26,8 MB** trước thay đổi. Đây là kết quả kiểm discovery,
   chưa phải benchmark cho mọi lệnh build.
3. Bổ sung ignore cho `.pytest_cache`; giữ rule ignore dữ liệu `rl_runs`
   nhưng cho phép theo dõi marker `COLCON_IGNORE` trong Git.
4. `prepare_toolchain.sh` dùng compiler đã giải nén trước. Archive chỉ cần
   tải khi phải cài lại compiler; chạy lại helper sau khi xóa archive đạt,
   không tải lại gói. Bản script trước sửa được lưu trong artifact cleanup.

Chính sách dọn raw episode sau job TD3 thành công đã có từ lượt trước,
không thay bằng thao tác xóa hàng loạt các experiment lịch sử.

## Kiểm chứng sau dọn

- **6.811 file được bảo vệ** giữ nguyên SHA256, gồm source/report đang theo
  dõi trong Git, ba bundle checkpoint và raw bag ROS trong workspace.
- Cả ba checkpoint đạt kiểm hash/bundle/runtime; global steps lần lượt
  **20.000 / 25.000 / 30.000**. Không load model để train hay optimizer update.
- Scientific assessment hiện tại vẫn đọc hợp lệ và giữ kết luận cũ.
- **40 software tests đạt** cho training storage, training panel, dashboard
  và tích hợp Studio. Chạy với bytecode/cache pytest tắt để tránh tạo lại
  ngay các cache vừa dọn.
- Danh sách package ROS trước/sau khớp; compiler `12.3.Rel1` chạy được.
- Không chạy Gazebo, train, SSH, enable motor hay thao tác hardware.

## Biên bản và khả năng phục hồi

Artifact cleanup nằm tại workspace người dùng:
`artifacts/project_cleanup_2026-11-08/`.

- `cleanup_plan.json`: từng file xóa, kích thước, hash và nhóm lý do.
- `cleanup_result.json`: số file/byte thực xóa, trạng thái và dung lượng đĩa.
- `protected_before.json`: hash các file được bảo vệ.
- `project_review.json`: kiểm kê các root, entrypoint và tham chiếu archive.
- `runtime_verification.json`, `tests.xml`, `colcon_*.txt`: kết quả kiểm tra.

Ba file ở root repo còn bản trong Git; có thể khôi phục trước khi commit:

```bash
git restore -- d.zip src.zip rl_training.log
```

Log/cache đã xóa không được sao lưu thành một bản lớn khác. Báo cáo và
stdout/stderr build cần cho kết quả lịch sử được giữ theo phạm vi nêu trên.
Các file chưa đủ bằng chứng là thừa được giữ lại, không xóa theo tên “old”,
“legacy”, “rough” hay chỉ vì hiện tại ưu tiên TD3.
