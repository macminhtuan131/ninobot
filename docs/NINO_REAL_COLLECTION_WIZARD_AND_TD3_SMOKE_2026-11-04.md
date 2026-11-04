# GUI thu từng bước và smoke TD3 residual — 04/11/2026

## 1. Kết quả bàn giao

**[N — phần mềm]** GUI v6 đã chuyển luồng thu thật thành sáu trang. Đã chạy
TD3 mới **128 transition** trên backend giảm bậc, lưu/nạp checkpoint, replay
và actor. Kiểm sâu đạt; không phát hiện lỗi learner/replay trong phạm vi này.
Không sửa gain/current/controller để tạo một kết quả tốt hơn.

**[Giới hạn]** Không có phiên robot thật mới, SSH, flash hoặc lệnh motor trong
lần làm này. Hardware cutoff vẫn 02/11. Kết quả smoke không là bằng chứng
TD3 cải thiện Nino, contact fidelity, sim-to-real hoặc khả năng deploy.

## 2. GUI hiện hành

Mở **Nino · Thu dữ liệu & Xây project → Thu dữ liệu thật**. Nếu đang mở bản
cũ, đóng rồi mở lại. [Hướng dẫn thao tác](../src/nino_pi/GUIDED_COLLECTION.md).

| Trang | Hành động tiếp theo | Gate / artifact |
|---|---|---|
| 1. Chọn phiên | Chọn tiến–dừng có video hoặc đứng yên; Tiếp tục | Chưa có tác vụ robot |
| 2. Chuẩn bị Pi | Deploy → Agent/cảm biến → inventory; có lựa chọn kiểm driver đang chạy | Trạng thái process và báo cáo thiết bị, không suy chỉ từ topic name |
| 3. Điều kiện/video | Điền pose/caster, sàn/tải, video/mốc đồng bộ; xác nhận điều kiện | Hiển thị trường còn thiếu; stack ZERO chưa yêu cầu tiến |
| 4. Thu/thử | Bắt đầu ghi → đợi mẫu → xác nhận lại vùng thử/RC → bấm tiến riêng | Progress, count và session path; chỉ một yêu cầu thử, đợi recorder đóng |
| 5. QC/quan sát | Kiểm gói đã đóng → lưu quan sát thật | Raw integrity tách khỏi quan sát thân xe; giữ no-motion/failure/unknown |
| 6. Nhận dữ liệu | Tải về → mở thư mục | Local path thật từ helper; video camera copy riêng |

Mỗi trang có **một nút hành động chính**. Điều hướng chỉ xem trang, không chạy
job. Log chi tiết thu gọn và tự mở khi lỗi. Nội dung dài cuộn riêng; nút chính
được kiểm là nhìn thấy ở cả **900×740** và **1280×960**.

Các thay đổi/correction cụ thể:

- Tách view `collection_wizard.py` khỏi state/process controller. Sửa callback
  chọn trang chạy quá sớm khi constructor chưa gán xong `wizard`.
- Bắt đầu recorder không phát tiến; thêm checkbox xác nhận ngay trước nút tiến.
  GUI còn yêu cầu receipt cập nhật recorder trong 2 s, còn ≥33 s ghi. Đây
  không phải đo source freshness hoặc actuator latency; trial vẫn kiểm ở Pi.
- Khóa profile/metadata điều kiện khi đã bắt đầu thu, tránh đổi mô tả giữa phiên.
- Sửa helper fetch để trả đường dẫn local có cấu trúc, giữ qua process closure;
  nút mở thư mục dùng đường dẫn đó. Demo không bịa một thư mục dữ liệu thật.
- Giữ việc chờ process đóng thật trước QC, zero/disable finalizers, kiểm STOP,
  command ownership và ledger. Không mở lại pilot đã đóng hoặc đổi runtime bundle.

Profile còn **0,05 m/s, ramp 0,10 m/s², source 2 s, zero/disable, bag 60 s**.
Runtime diagnostic hiện có là một lượt có ledger. Nếu đã dùng, GUI báo chặn;
phải review và có protocol riêng cho đợt sau. Thiết kế giao diện không cấp thêm lượt.

## 3. TD3 smoke thực sự đã chạy

**[N — fixture phần mềm]** Validation và train mới nằm trong
`~/nino_research/td3_smoke_20261104_v2_initial/`:

- Validation: `20261104T012934446879Z_validate`.
- Train: `20261104T013418821991Z_train-td3`.
- Audit hiện hành của checkpoint mới: `20261104T014242429731Z_td3_audit`.

| Kiểm tra | Kết quả |
|---|---|
| Budget / seed train | 128 transition, một seed 7, CPU |
| Cập nhật TD3 | `_n_updates=112`; actor L1 weight change ≈32,564884 |
| Checkpoint reload | Tham số finite; actor/critic optimizer state nạp lại được |
| Replay so JSONL và tái thực hiện environment | **128/128** observation, proposal, next observation, reward và done/timeout đạt |
| Episode time limit | Hai terminal observation được giữ đúng trước reset; bootstrap timeout đúng |
| Sai số actor NumPy so SB3 đã nạp | Tối đa **8,94×10⁻⁸** trên 128 observation của trace |
| Sai số observation replay | Tối đa ≈1,49×10⁻⁸ |
| Sai số reward replay | Tối đa ≈7,39×10⁻⁹ |
| Rollout giới hạn | 60 bước/arm: alpha=0, TD3 alpha=1, TD3 + Governor |
| Projection | Per-wheel residual, wheel/body speed, reference acceleration đều trong contract fixture |
| Alpha=0 / baseline=0 | Policy contribution bằng zero / residual không tự tạo lệnh khởi hành |
| Fault cases | Mất permission, fault, emergency-stop flag, sensors-stale flag và command-age quá hạn: terminal failure, zero reference |

Trained actor tạo chênh target/feedback fixture lớn nhất khoảng **0,44919 rad/s**
so alpha=0. Đây là **control-flow effect**, không phải motion-quality benefit.
Fixture chưa có caster/contact/plant Nino đã hiệu chuẩn. Các seeds không tạo
ra điều kiện vật lý độc lập khi fixture deterministic.

Đường actor vẫn **20 features × 5 history frames = 100 phần tử**. GT/pose
fixture chỉ là nhãn/evaluator, không vào actor. Bản source/ABI đang kiểm:

```text
source: eed70c3f51dd8ade8f111e3432fe8afc084d740cdb090cb24559658a3ae471e2
ABI:    e5329fa80772a876fb8bb810c5b13312dcfc992d213db8fe52dd1909f7497f93
```

Không sửa source controller/learner gốc trong smoke này. Auditor mới có hash
riêng trong manifest để tránh gán kết quả cũ cho một mã audit đã đổi.

## 4. Chạy lại kiểm TD3 trong GUI

Vào **Xây project / sơ đồ → Công cụ kiểm phần mềm**:

1. Kiểm History/giới hạn/environment.
2. TD3 · kiểm optimizer 128 bước.
3. **Kiểm replay/checkpoint/actor TD3** — dùng checkpoint mới nhất hợp lệ.

Auditor lưu `audit.json`, ba rollout JSONL, manifest và hash. Source đổi,
checkpoint mới hơn hoặc lần train mới nhất lỗi/hủy thì kết quả audit cũ không
được hiện như kiểm đạt của bản hiện hành. Không tự train/retry khi audit lỗi.
SB3 dùng pickle: chỉ kiểm checkpoint/replay tự sinh tại local, không nạp tệp
không tin cậy từ attachment/internet.

Đã kiểm nút này bằng **QProcess thật** trên thư mục GUI mặc định
`~/nino_research/residual_build_v1/`; audit ở
`20261104T014640757157Z_td3_audit`. Các artifact PPO/ROS/Gazebo cũ trong thư mục
này giữ nguyên; không tính chúng là các lần thử mới hôm nay.

## 5. Kiểm chứng và phần còn thiếu

**[N — software QA]** Kết quả test, screenshot, build và hashes hiện hành được
ghi trong `NINO_GUI_TD3_SMOKE_VERIFICATION_2026-11-04.json` cạnh báo cáo này.
**41 tests đạt**: 25 GUI/process/artifact và 16 reference/History/environment.
Đợt TD3 128 transition và các rollout audit là phép kiểm chạy riêng, không
được cộng thành số lượt thử robot thật.
Artifact QA chi tiết tại:

```text
/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/gui_wizard_td3_smoke_2026-11-04/
```

Đã kiểm flow demo sáu trang, nút record/trial riêng, stationary không mở motor,
metadata bị khóa sau thu, receipt stale/cửa sổ muộn chặn trial, true closure,
fetch path, không promote Q0, và audit hết hiệu lực khi đổi checkpoint/mã kiểm.

Build isolated đầu chỉ chọn pi/rl thiếu hai dependency chưa build; giữ log lỗi.
Sau khi build đủ control/description/pi/rl, **4/4 package đạt**. Không phải lỗi
TD3 hoặc một phép thử hardware thất bại.

**[Chưa kiểm live]** Wizard mới chưa được dùng với Pi thật trong phiên này.
Chưa kiểm body reference, wheel response lặp lại, stopping vật lý hoặc residual
trên Nino. Không nâng dataset cũ lên Q3/Q4 từ kết quả software smoke.

**Bước tiếp theo:** mở lại GUI v6, chọn phiên cần thu và đi qua inventory.
Chỉ thu khi protocol hiện hành còn lượt và readiness thực đạt; nếu diagnostic
đã dùng/đóng thì review ledger/kết quả trước khi chuẩn bị đợt mới có giới hạn.
