> **Phân tích offline đã hoàn tất:** audit chuỗi lệnh/reward khớp; actor cải
> thiện mô tả trong phase mở nhưng classical vẫn tốt hơn; critic chưa đáng
> tin. Chốt giữ classical cho envelope hiện tại, không tự thêm training.
> [Báo cáo phase/checkpoint](NINO_TD3_OFFLINE_PHASE_REVIEW_2026-11-07.md).
> Phần đề xuất phân tích bên dưới được giữ làm lịch sử quyết định.

# Nino — đánh giá continuation 20k → 30k và bước tiếp theo

Ngày 07/11/2026. Dựa trên `job.json`, `training_result.json`, `result.json`
và sealed-artifact QC tại workspace client:
`artifacts/common_studio_continuation_2026-11-07/review.json`.

## Đã hoàn thành

- Continuation thêm 10.000 transition, global **30.000**, cùng learner seed 11;
  không phải một training seed độc lập mới. Không warmup lại.
- Tổng **20.000 critic / 10.000 actor updates**, replay 30.000/capacity 32.768.
- Continuation có 72 training launches, 71 terminal episode; đoạn cuối 60 bước
  right-censored được giữ riêng. Worker khoảng 71,35 phút.
- Sáu evaluation × 140 tick đều đạt task/stop/functional/timestamp gates.
- QC kiểm 1.844 file hash, source identity, lifecycle; audit 10.000 replay row
  mới và 20.000 row parent được giữ nguyên; model/targets/optimizers hữu hạn.
  Không suy ra toàn bộ raw acquisition loss-free từ những kiểm tra này.
- Final checkpoint: `~/nino_research/td3_studio/20261107T080414816378Z_common_train/checkpoints/step_000000030000_final`.
- Manifest SHA256: `9d0337d6c31a22a52c89faa0a8921d938c7a4cc99ca63b18cb57389947d392bd`.
- Budget đã đóng, không có job kế tiếp tự động hoặc hardware action.

GUI đã có tiến độ, log, TensorBoard, checkpoint, bản đồ scene/pose, bảng
episode/checkpoint và Laya advisory. Correction GUI gần nhất có 38 tests đạt.
Đây là năng lực phần mềm, không là bằng chứng controller tốt hơn baseline.

## Kết quả so sánh

Native velocity RMSE toàn 14 s, **mm/s, thấp hơn tốt hơn**:

| Source stop | B0 | Classical scheduled | TD3 30k | TD3 so classical |
|---|---:|---:|---:|---:|
| 6 s | 4,948 | **3,900** | 4,236 | +8,62% |
| 8 s | 5,118 | **4,140** | 4,351 | +5,08% |

Cả hai GT-header grids cũng có TD3 kém classical: khoảng +7,42% tại stop6
và +4,78% tại stop8. Vì vậy dấu của so sánh này nhất quán ở ba reporting grids.
Một run/cell, một seed và seen scenario vẫn không đủ cho CI/generalization.

So B0, native TD3 tốt hơn 14,40%/14,98%; nhưng GT grids ở stop8 tệ hơn
khoảng 1,27%. Không phát biểu ưu thế B0 trên mọi cách đo.

Path RMSE TD3 0,099/0,042 mm, classical 0,025/1,131 mm. Tracking không
đồng loạt tệ hơn hoặc tốt hơn; giữ metric này cùng velocity và task/stop.

So block 20k trước, native velocity RMSE TD3 30k cao hơn 2,58%/4,51%.
Đây là hai fresh evaluation blocks, không exact-state pairing: chưa kết luận
train thêm gây suy giảm, cũng chưa thấy bằng chứng lợi ích từ continuation.
30k không tự chứng minh hội tụ hoặc giới hạn cuối cùng của TD3.

**Quyết định:** giữ checkpoint và dữ liệu, chưa promote TD3 hơn classical.
Trước mắt classical vẫn là lựa chọn có bằng chứng velocity tốt hơn trong
screen này. Kết luận chỉ áp dụng clear-box, common103D/1D/history5/10Hz,
planned stop6/8 và baseline Ki0,10; không áp sang cáp, groove hoặc robot thật.

## Khuyến nghị, chưa thực hiện thêm

**Ưu tiên một phân tích offline có điểm dừng**, dùng dữ liệu đã có:

1. Trên cùng corpus observation hợp lệ, so actor checkpoint20k/25k/30k:
   requested action, window/projection và executed reference theo phase.
2. Tách reward tracking, action-size và action-change; đối chiếu diễn biến
   action và critic ranking. Corpus probe/Q-values chỉ là chẩn đoán, không
   tạo counterfactual outcome hoặc thay evaluation thật.
3. Kiểm một giả thuyết cụ thể về reward/gating/critic thay vì đổi đồng thời
   LR, history, action scale, baseline và domain randomization. Window mở
   2.865/10.000, positive 2.829, negative 36; đó là hành vi quan sát được,
   chưa phải lỗi coverage hoặc số optimizer updates hữu ích.

Artifact cần bàn giao: bảng checkpoint × phase, reward decomposition và
một quyết định: lỗi triển khai có thể sửa; một ablation có căn cứ; hoặc giữ
classical cho envelope này. Dừng vòng chẩn đoán sau báo cáo này; nếu còn
unknown thì ghi unknown và lập protocol mới, không tự nối training budget.

Nếu có lỗi contract: sửa đúng lỗi, kiểm parity trước khi đề xuất run mới.
Nếu không có lỗi và có giả thuyết kiểm được: chọn đúng một ablation/version
và budget riêng. Nếu không có cơ chế đáng thử: ưu tiên classical/SysID;
không cần giữ RL để chứng minh một đóng góp thuật toán.

Trước batch mới cần giải quyết dung lượng: lúc review còn khoảng **1,9 GiB**,
thấp hơn dự toán continuation trước (~4,15 GiB gồm reserve). Lưu trữ/di chuyển
artifact có kiểm checksum là một lựa chọn; không tự xóa dataset hoặc hạ gate.

Nhánh hardware vẫn cần wheel/body reference và motor-response evidence riêng;
kết quả sim cùng các công cụ GUI không thay các phép đo đó. Laya không quyết
định checkpoint thắng baseline; nhận xét trái counts vẫn giữ nhãn bất đồng.
