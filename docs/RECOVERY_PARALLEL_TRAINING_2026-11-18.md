# Sàn sạch và gờ train song song

## Quyết định

Theo yêu cầu người dùng, campaign gờ 50.000 transitions chạy đồng thời với
campaign sàn sạch 50.000 transitions. Sàn sạch giữ model, replay, source pins
và tiến độ hiện có. Gờ bắt đầu với model và replay độc lập.

Không chỉnh source điều khiển đang được campaign sàn sạch pin. Backend và
independent observer đều dùng ROS domain 129. Chỉ đổi biến môi trường domain
không đủ vì có explicit `rclpy.init(domain_id=129)`.

## Isolation thực sự dùng

Launcher Bubblewrap tạo network, IPC và PID namespace riêng cho toàn bộ
campaign gờ. Worker chỉ có loopback. ROS domain 129 trong worker không cùng
mạng với domain 129 của sàn sạch. `/proc` chứa PID của worker; `/dev/shm`
riêng chặn DDS shared-memory discovery giữa hai campaign.

Lock gờ có inode riêng, bind lên đường dẫn lock mà code hiện hành sử dụng
chỉ trong mount namespace của gờ. Lock sàn sạch trên host không thay đổi.
Gazebo vẫn có UUID partition riêng cho mỗi episode.

Device interface của host được giữ cho NVIDIA, GLX và CUDA. Sau đó launcher
overlay `/dev/shm` riêng. Đây là môi trường cô lập giao tiếp simulation,
không phải sandbox bảo mật để chạy code không tin cậy.

## Kiểm chứng và correction

- 7 tests kiểm namespace, shared memory và lock đạt. Mọi trường hợp dùng lại
  namespace, shared memory hoặc sai lock đều bị từ chối.
- Runtime facts xác nhận network, IPC, PID, shared-memory mount và lock inode
  khác host. Loopback phải UP và là interface duy nhất.
- V1 dừng ở shell setup trước simulation vì root bind có nodev tại `/dev/null`.
- V2 đã khởi động ROS/controller nhưng Gazebo dừng ở GLX khi device interface
  NVIDIA bị che. Không có training transition từ hai attempt này.
- V3 giữ device interface rồi overlay shared memory. Full readiness gờ trong
  namespace, chạy đồng thời với clean, đạt task_success và source QC.
- Kiểm 34/34 hash, 828 boundary checks, startup replay từ raw khớp pose và count.
  Primary graph chỉ thấy một RELIABLE joint publisher. Thư viện controller
  manager đã pin được xác nhận trong process của đúng partition.
- Service trực tiếp từ user manager bị chặn tạo loopback. Thử nghiệm systemd
  scope từ context caller đã đạt. Campaign gờ hiện dùng scope đó.

Không nới source gate 40 ms hoặc PI timing gate 4 ms. Readiness dùng residual
zero, không có optimizer update và không chứng minh TD3 tốt hơn classical.

## Hai campaign

| Task | Ngân sách | Output | Đơn vị chạy nền |
|---|---:|---|---|
| Clean | 50.000 | `~/nino_research/recovery100_clean50k_20261118_02` | `nino-td3-clean-obstacle-50k-20261118-02.service` |
| Short obstacle | 50.000 | `~/nino_research/recovery100_obstacle50k_20261118_02` | `nino-td3-obstacle-50k-parallel-20261118-02.scope` |

Giữ task, world, observation 100D, residual chung 1D, reward, hyperparameters
và retention đã khóa. Sàn sạch và gờ có seed training riêng. Phạm vi vẫn là
research stage 0, không phải kết quả cho mọi obstacle hoặc robot thật.

Artifacts hiện hành nằm trong:

`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/obstacle_parallel_50k_20261118_v3`

- `launch_isolated.py` tạo namespace và kiểm invariants trước khi gọi campaign.
- `request.json` khóa task gờ và ngân sách 50k.
- `isolation_run.json` ghi identity namespace và inode thực tế.
- `readiness_verification.json` lưu kiểm chứng full probe.
- `parallel_status.json` đọc progress của cả hai task mỗi 5 giây.
- `scope_launch.json` ghi command và PID host của scope client.
- `run.log` giữ stdout/stderr của gờ. Không tự retry lỗi.

Đọc `progress.json` của từng output để lấy số bước thực, replay rows, actor
và critic updates. Ngân sách 50k không phải số bước đã hoàn thành.

## Handoff hàng đợi cũ

File STOP trong thư mục artifact của queue tuần tự chỉ được kiểm trước khi
queue mở task kế. Nó không dừng campaign clean đang chạy. File
`PARALLEL_HANDOFF.json` chỉ tới scope và status mới của gờ.

Khi clean kết thúc, queue cũ có thể ghi lỗi orchestration do STOP handoff.
Đọc result của từng campaign và `parallel_status.json` để phân biệt handoff
với lỗi training. Không dùng trạng thái queued của queue cũ cho campaign gờ.
Queue cũ không ghi vào status mới; hai launcher không cùng sửa một JSON.

PID trong metadata simulator là PID bên trong namespace. PID của scope client
và wrapper được ghi rõ là PID host. Chỉ dùng unit tương ứng để quản lý lifecycle.

## Các nguyên tắc áp dụng

Separate Before Serializing Shared State dẫn đến tách namespace, shared memory,
lock và status. Prove It Works yêu cầu full probe dưới tải song song trước khi
train. Build the Lever tạo launcher và script kiểm lại readiness từ raw.
