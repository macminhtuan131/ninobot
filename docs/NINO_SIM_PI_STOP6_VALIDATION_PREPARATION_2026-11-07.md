> **Cập nhật định hướng07/11:** protocol dưới đây giữ nguyên cho quyết định promote Ki0,15. Đây là nhánh riêng, không là điều kiện bắt buộc để thiết kế pilot TD3 dùng Ki0,10 frozen. [Đính chính phạm vi kết luận training](NINO_TD3_TRAINING_SCOPE_CORRECTION_2026-11-07.md).

# Validation PI ở lịch dừng 6 giây — chuẩn bị offline

**Ngày 07/11/2026. Trạng thái: chưa release physics, chưa cấp slot.**

## Vì sao làm bước này?

Screen dừng8s đã đóng4/4,560native ticks. Ki0,15 giảm native velocity
RMSE21,7%/19,5% so với Ki0,10; hai GT grids cùng chiều. Path RMSE tăng,
tối đa0,455mm. Đây là kết quả mô tả trong một điều kiện, chưa đủ để promote
baseline hay mở TD3. [Bằng chứng screen8s](NINO_SIM_PI_SCREEN_RESULT_2026-11-07.md).

Câu hỏi tiếp theo duy nhất: **lợi ích của đúng candidate Ki0,15 có giữ được
khi nguồn lệnh được rút ở6s, với baseline Ki0,10 cùng lịch dừng không?**

Stop6 đã tồn tại trong dự án nhưng không được dùng chọn candidate Ki.
Đây là validation tách khỏi phép chọn Ki, **không phải unseen test bank**,
generalization trên nhà máy, lặp độc lập seed huấn luyện hay exact-state branching.

## Protocol đề xuất, chưa là ngân sách được cấp

| Thành phần | Chốt cho phép so sánh |
|---|---|
| Thứ tự4cell | Ki0,10 →0,15 →0,15 →0,10; hai block đảo thứ tự |
| Yếu tố đổi so với screen8s | Thời điểm rút nguồn lệnh8→6s |
| Điều kiện giữ | Clear-box/E1, gain1, Kp0,3; nominal0,2m/s; B0zero; reset seed701 |
| Tốc độ/giới hạn | Physics1ms; PI500Hz; native100ms; ramp/slew/limit và driver frozen giữ nguyên |
| Mỗi cell | Fresh launch; reset ACK+quiet;140decision/14s; nguồn0 trước0,5s và từ6s |
| Tối đa đề xuất | 4launches/560eval ticks; wall1800s; reset/settle inherited ngoài eval ticks |
| Không cấp trong bước chuẩn bị | Actor/training/optimizer/probes/retry/extra smoke/hardware:0 |

Cùng thứ tự như screen8s giúp chỉ đổi lịch dừng; đảo thứ tự trong block giảm
một phần confound theo lượt, không loại trừ contact/solver/initial-state variation.
Hai lặp mỗi Ki chỉ phục vụ một phép kiểm nhỏ có điểm dừng. Không tăng mẫu
sau khi thấy kết quả.

### Primary, constraints và quyết định

- Primary: whole14s native nominal body velocity RMSE, candidate so baseline
  **trong từng block stop6**. Không gộp hay dùng khác biệt RMSE giữa stop6/8
  làm hiệu quả Ki vì tỷ trọng pha chuyển động/dừng khác nhau.
- Giữ GT-header20ms và grid dịch10ms riêng; không chọn grid thuận lợi.
- Proposed pass: native giảm ít nhất5% ở **cả hai block** và hai GT grids
  đều giảm ở cả hai; mọi task/measurement/closure gate đạt.
- Giữ marker0,95m, physical path RMSE≤0,04m, quiet2s trước horizon14s.
  Đây là gate nghiên cứu đề xuất; chưa phải mức chấp nhận ứng dụng nhà máy.
  Luôn báo path/tracking/time trade-off, kể cả khi nằm dưới gate.
- Candidate nhất quán kém: giữ Ki0,10. Hiệu ứng nhỏ, khác block, grid đổi
  chiều hoặc mẫu số không hợp lệ: UNKNOWN, giữ baseline frozen.
- Pass chỉ dẫn tới **review một baseline Sim có kiểu/ABI mới**, không tự
  promote, sửa baseline cũ, chấp nhận checkpoint cũ hoặc mở learner/hardware.
- Measurement/task/closure failure đầu tiên hoặc hủy đóng mọi slot còn lại.
  Không retry, thay candidate/objective hoặc mở rộng số lần lặp.
- SIGINT/wall timeout có cleanup+seal. Hard kill/power loss không bảo đảm
  graceful closure; ledger tồn tại vẫn chặn chạy lại. Phải review artifact.

## Phần mềm đã tách riêng

- Context: `pi_stop_validation_context.py`;103D/1D, history5,10Hz; ABI mới,
  chỉ B0zero. Không thêm Ki/cell/block vào observation. Feature thời gian còn
  lại tới lịch dừng đã có trong contract kế thừa: đây là bài **biết lịch dừng**,
  không phải phát hiện vật cản chưa biết bằng proprioception.
- Motor/backend/launch: tái sử dụng nguyên PI screen family, cached Ki
  readback0,10/0,15, gain1 và watchdog/limiter/reset cũ.
  Telemetry vẫn mang đúng ID **driver** cũ; context evaluation có ID riêng.
- Runner: `pi_stop_validation_runner.py`; ledger/root/protocol/release riêng.
  Pin manifest screen chọn Ki, fingerprint phần mềm, source/install và protocol.
- Root physics dự kiến: `~/nino_research/sim_pi_stop_validation_v1`.
  **Chưa tạo root hoặc ledger physics** trong bước chuẩn bị.
- Release record: `src/nino_rl/config/pi_stop_validation_release_v1.json`:
  `released=false`, `allocated_physics_slots=0`.
- GUI chỉ đọc proof, mở protocol và hướng dẫn bước sau; không có nút tự cấp
  budget hay chạy validation trong trang benchmark.

### Kiểm offline và giới hạn

Báo cáo/hash chi tiết nằm trong artifact preflight liên kết từ GUI.
Có68software tests: schedule/config/ABI, B0-only, actual inherited guidance
view ở biên6s với IO mocked, comparator, ledger/cancel/cleanup/lock/release;
cùng4cell/560decisions coordinator synthetic và560transitions wrapper parity.

**Correction có căn cứ:** fixture screen cũ ghi cứng8s. Tạo fixture riêng
tham số6s thay vì dùng lại rồi gắn nhãn6s. Không sửa fixture/artifact frozen.
Fixture mới kiểm source schedule và source packet; **không mô hình hóa tác
động Ki lên plant**. Test ban đầu4fail (3cleanup fixture chưa reset và1đọc sai
schema sample) được giữ cùng báo cáo pass sau sửa. Các test phát hiện đúng
lịch dừng của actual guided backend gọi không ROS, nhưng không chứng minh
toàn pipeline Gazebo đã chạy.

Summary, timing và closure trong full-coordinator fixture là mocked; không
tính chúng thành measurement coverage hay closure physics. Không có outcome
mới để khẳng định Ki0,15 hữu ích ở stop6.

## Gate tiếp theo

1. Review protocol/proof, fingerprint, release=false và root mới chưa tồn tại.
2. Nếu release riêng: cấp **đúng4slot/560ticks**, chạy một batch, đóng budget
   sau kết thúc/lỗi. Không chạy lại screen8s đã đóng.
3. Kiểm manifest/hash, reset/ACK/lifecycle, source support và conflicting
   payload theo **đúng query dùng cho metric** trước khi so sánh.
   Giữ raw conflict; không chọn biến thể first/last. Query chạm ambiguity
   thì UNKNOWN/fail closed.
4. Báo whole14native + hai GT grids, path và task/stop; ra pass/no-go/unknown
   theo rule trên. Không tự train TD3 dù pass.

**Việc ngay tiếp theo:** review/release riêng phép validation stop6, thay vì
thêm candidate hoặc train dài. Nếu stop6 không giữ được benefit/quality,
giữ Ki0,10 và đóng hướng promote candidate này trong envelope đang xét.

## Artifact đã kiểm

- Proof: `/home/tuanmac/nino_research/sim_pi_stop_validation_preflight_v1/offline_2026_11_07`.
- Manifest SHA256: `d30937e2d7e4ac01922e9e66c71521f1c50cf09ae8d25744fca901e8a7f52e91`.
- Runner fingerprint: `2d9f70ec52e81a102ee5f6b3e7cb56ec3d2e3a2912e3045cd55284e8de90b14c`.
- Context ABI: `56dc039dedae4542dccc711b242d4a9cfa22ab80184dc238ad1998e105aae3bd`.
- QA/tests: `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_pi_stop_validation_2026-11-07`;68tests context/runner,18tests GUI đạt.
- Build `nino_rl`/`nino_pi` đạt; chưa có slot/runtime outcome mới.
