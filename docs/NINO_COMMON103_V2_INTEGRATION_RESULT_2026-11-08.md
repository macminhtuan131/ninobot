# E1 common103_v2 — full-episode integration đã đóng

Ngày 08/11/2026. Tiếp tục đúng bước E1 từ review; **1 job, không retry,
không campaign đa seed, không hardware**.

## 1. Kết quả

| Đại lượng | Thực tế |
|---|---:|
| Scenario train | `box_c1_6mm_dr`, seed11, smoke h5 profile |
| Train transitions | **280/280** |
| Critic / actor updates | **264 / 132** |
| Replay size | **280** |
| Episode train hoàn chỉnh/task/stop đạt | **2/2** — source stops6/8 s |
| Training launches | **3/3 cap**, gồm một auto-reset cuối không có transition |
| Evaluation | **6/6**, B0/classical/TD3 × stops6/8 s |
| Evaluation transitions | **840/840** |
| Tổng native task transitions | **1.120**, không phải tổng solver steps gồm reset |
| Gated request penalty sai | **0/200 tick đóng cửa sổ** |
| Action coverage mở | **80 tick**, 58 request dương /22 âm |
| Wall time job | **443,26 s**, quan sát của riêng job này |

Đã kiểm hash **263 file gốc** trước retention, source pins, world/DR metadata
ba reset và lifecycle đóng sạch. Final checkpoint280 có model/replay/identity,
qua hash/runtime và preflight resume; chưa thực sự chạy resume.

**Verdict: integration đạt sau một correction ở GUI reader.** Điều này
không xác nhận TD3 hơn classical, DR robustness hoặc khả năng triển khai real.
Đây là smoke profile với warmup16/replay2048, không phải research profile
warmup10k/replay100k; không đánh đồng 280 bước này với campaign nghiên cứu.

## 2. Development evaluation — chỉ mô tả

Các lượt eval dùng **gờ danh nghĩa Ø6 mm**, không lấy mẫu DR; mỗi arm/stop
chỉ một fresh launch. Tất cả đạt task/stop và timestamp diagnostic. Không
có independent test bank hoặc exact-state branching.

| Source stop | Arm | Native vRMSE, mm/s | Path RMSE, mm |
|---:|---|---:|---:|
| 6 s | B0 | 21,859 | 4,555 |
| 6 s | Classical scheduled, Ki0.10 | 19,021 | 0,903 |
| 6 s | TD3 | 18,338 | 2,898 |
| 8 s | B0 | 36,101 | 12,004 |
| 8 s | Classical scheduled, Ki0.10 | 16,473 | 2,974 |
| 8 s | TD3 | 24,818 | 4,302 |

TD3 có vRMSE thấp hơn classical **3,59%** ở stop6 nhưng cao hơn **50,66%**
ở stop8; path RMSE cao hơn ở cả hai lượt. Đây không là gate xác nhận thất
bại của thuật toán TD3 hoặc chiến thắng ở stop6. Không promote checkpoint,
không tự tăng budget để tìm winner.

Đã đọc offline bốn phase bằng **measurement clock cho body metric**, giữ
**decision clock cho action**, không gán hai clock thành một:

| Stop/arm | Tăng tốc & warmup | Cửa sổ reference mở | Withdrawal | Source-stop |
|---|---:|---:|---:|---:|
| 6/classical | 6,336 | 40,175 | 2,390 | 3,908 |
| 6/TD3 | 6,624 | 38,431 | 2,043 | 4,574 |
| 8/classical | 6,606 | 26,672 | 2,254 | 4,704 |
| 8/TD3 | 6,516 | 40,861 | 2,592 | 5,274 |

Bảng là native velocity RMSE mm/s theo bin đã ghi trong `phase_readout.json`.
Sự khác biệt stop8 chủ yếu xuất hiện trong cửa sổ reference mở; **không tự
là bằng chứng control authority hữu ích hoặc nhãn first loaded contact**.
E1 chưa thu contact-force labels để xác định đầy đủ pha contact. Không đổi
reward/history/LR/action scale từ hai trajectory này.

## 3. Correction duy nhất: map và vệt xe phải cùng episode

Lỗi quan sát được trên chính E1: sau auto-reset cuối, `current_world.json`
đã chỉ episode2 chưa có transition; dashboard vẫn vẽ path episode1 lên map
episode2. Điều tương tự có thể xảy ra khi reader đang đọc backlog.

Sửa `DashboardReader` chọn `episode_world` từ **last consumed trace row**;
chỉ dùng reset metadata khi chưa có transition. Thêm `map_episode` và nhãn
last-recorded-transition, giữ kiểm hash geometry. Regression test kiểm cả
backlog và auto-reset cuối. Đối chiếu lại 280 row thực xác nhận map là world
episode1, khớp path. **0 lượt Gazebo bổ sung** cho correction, không thay
controller/reward hoặc checkpoint fingerprint.

GUI tiến độ, Train TD3 và project dashboard đã cập nhật E1 hoàn tất. Số đếm
mới chỉ hiển thị là đã xác minh khi hash integration report và counter khớp.
**116 test phần mềm được chọn đạt** sau correction và cập nhật GUI; không
phải 116 rollout hoặc kiểm toàn bộ test suite.
Job này gọi public engine từ harness; live discovery của launcher CLI chuẩn
được kiểm bằng fixture. Không gọi đây là một lượt bấm toàn bộ GUI end-to-end.

## 4. Retention

Sau audit đầy đủ, dùng public retention API xóa **66 file raw train** trong
ba thư mục episode, **71.524.067 byte ≈68,2 MiB**. Giữ checkpoint280/replay,
traces, TensorBoard, reset/world metadata, lifecycle, cả sáu raw evaluation
và kết quả. **197 file gốc giữ lại khớp hash**.

Manifest gốc không sửa. Nó không còn kiểm đủ toàn bộ raw train sau retention;
receipt ghi rõ dữ liệu đã xóa. Không coi checkpoint có thể khôi phục raw này.

## 5. Bước tiếp theo

1. **Đã làm offline:** đọc phase và action coverage từ E1 để tránh tiếp tục
   phỏng đoán chỉ từ return hoặc ảnh Laya.
2. **Tiếp theo, chuẩn bị offline:** chốt protocol baseline/control-authority
   cho gờ cố định. Giữ một yếu tố thay đổi; Ki0.15 mới là candidate từ sàn
   sạch, cần context/version riêng, không sửa baseline v1. Định nghĩa contact
   labels, contrast command→wheel→body, primary/constraint, block và stop rule
   trước release. Chưa chạy thêm physics trong lượt này.
3. Sau benchmark/authority và validation/test bank hợp lệ mới xét pilot
   research12k. Chưa mở 3×50k, chưa DR generalization hoặc hardware transfer.

Artifact:
`~/nino_research/common_v2_integration_20261108_v1/20261108T153835484317Z_common_v2_seed11_train`.

[Audit và correction receipt](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/common_v2_integration_2026-11-08/).
Draft gốc vẫn nguyên trạng chưa release; release riêng của E1 đã đóng sau
một job. Không tái sử dụng cùng root/slot hoặc lấy draft gốc làm budget mới.
