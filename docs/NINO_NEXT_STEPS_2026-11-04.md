> **04/11 — bước sim mới đã hoàn tất:** [checkpoint V2 trên sàn sạch](NINO_SIM_CLEAR_BIAS_RESULT_2026-11-04.md). Bốn lượt, không train thêm; bias yaw vẫn có. [Guidance contract](NINO_SIM_GUIDANCE_CONTRACT_2026-11-04.md) đạt offline, chưa nối Gazebo. V1/V2 giữ lịch sử.

## Việc tiếp theo trên nhánh sim

1. Nối estimator wheel+IMU causal vào guidance adapter với frame/clock/epoch đã khai báo; không lấy GT sửa estimate. Encoder odometry không là ground truth.
2. Protocol V3 cho B0 có guidance, residual zero, trên clear floor: kiểm initial heading error, tracking tuyến/reference, ramp và stop. So constant-straight B0. Chốt điều kiện/lặp/deadline trước chạy; chưa chạy ở cập nhật này.
3. Sau baseline hợp lệ mới định nghĩa velocity/yaw tracking reward và checkpoint/baseline identity V3; xem xét zero-init residual, rồi budget TD3 riêng. Không resume policy V2 dưới reference mới chỉ vì cùng ABI.

**GUI:** NHÁNH SIM → **Tiếp theo · kiểm bias sàn sạch + reference follower**. Hai stage đã đóng: xem bảng 4 lượt và kết quả 5 fixture offline. Chưa cần bấm chạy lại, chưa cần thu real data cho bước sim này.

# Các việc cần làm tiếp theo — Nino

Ngày 04/11/2026. Theo hồ sơ đã review, dữ liệu thật mới nhất vẫn đến 02/11; chưa kiểm live Pi trong lần làm rõ này.

## Đang ở đâu?

- **Đã có:** code History/Governor/projection, TD3/PPO optimizer smoke, ROS/Gazebo integration fixture và công cụ SysID.
- **Chưa có:** model Nino được hiệu chuẩn/kiểm holdout, benchmark learning đủ mạnh, real shadow và lợi ích residual trên robot.
- **Gate riêng của robot thật:** giải thích command, feedback hai bánh và chuyển động thân; không chặn việc nghiên cứu sim.
- Các nút kiểm phần mềm đã có artifact hiện hành không cần bấm chạy lại nếu source/config/hash không đổi.

## Nhánh robot thật song song — thứ tự thực hiện

**01 diagnostic → 02 đánh giá → 03 độ lặp → 04 wheel ID + reference thân → 05 model/baseline → 06 train/evaluate → 07 real shadow → 08 bounded robot trial.**

Các bước sau là kế hoạch có điều kiện; không mở lại ledger đã đóng hoặc tự cấp ngân sách motion/training.

## 01. Hoàn thiện một phiên tiến–dừng có video

**Trạng thái:** KHI MỞ NHÁNH ROBOT THẬT. **Người làm:** Bạn thao tác robot; assistant chuẩn bị/kiểm bộ thu.

**Làm gì:** Kiểm live Agent/topic/owner/STOP sau khi nối Pi. Dùng lại phiên cũ nếu đã có bag và video đủ rõ; nếu thiếu thì thu một diagnostic mới trên sàn trống. Giữ 0,05 m/s, ramp 0,10 m/s², source 2 s, zero/disable, bag 60 s. Quay đồng thời bánh, thân và mốc sàn; ghi mốc đồng bộ.

**Dữ liệu cần:** Raw IMU; motor_fb từng bánh; motor_status; các tầng command có thật; motor_enable; scan/STOP; TF; events; pose/caster/sàn/tải; video. Chưa có actuator target readback thì giữ thiếu.

**Đầu ra:** Một gói bag + metadata/events + video + quan sát xe, có cùng session ID.

**Điều kiện chuyển bước:** Recorder đóng, integrity/hash và các kênh/cửa sổ cần thiết được review. Video đủ phân biệt bánh quay và thân tiến. Phiên thiếu giữ incomplete/unknown; chưa chạy lặp.

## 02. Giải thích lệnh → bánh → thân xe

**Trạng thái:** SAU 01. **Người làm:** Assistant phân tích; bạn cung cấp quan sát/video.

**Làm gì:** Đối chiếu bốn pha yên, tiến, zero, sau dừng. Kiểm lệnh có qua Collision Monitor tới STM32; feedback trái/phải có đổi; video cho thấy bánh và thân phản ứng ra sao. Khoanh nguyên nhân nếu chúng mâu thuẫn.

**Dữ liệu cần:** Gói bước 01; source/header time và bag/receipt time giữ riêng; video và uncertainty đồng bộ.

**Đầu ra:** Báo cáo một lượt: lệnh đi tới đâu, hai bánh phản ứng thế nào, thân có tiến/tự dừng không, phần nào còn unknown.

**Điều kiện chuyển bước:** Chỉ mở bước 03 khi đường lệnh và chuyển động quan sát nhất quán hoặc nguyên nhân mâu thuẫn đã được giải thích. Nếu lỗi: tối đa một correction có căn cứ rồi quyết định protocol mới; không lặp vô hạn.

## 03. Đo độ lặp trên sàn sạch

**Trạng thái:** ĐỀ XUẤT · CHƯA MỞ ĐỢT. **Người làm:** Assistant chốt protocol; bạn chạy từng lượt sau review.

**Làm gì:** Chuẩn bị một đợt mới tối đa 3 lượt, cùng profile 0,05 m/s / 0,10 m/s² / source 2 s / bag 60 s. Giữ vùng trống, tải, hướng xuất phát; ghi hướng caster hoặc unknown. Review xong lượt trước mới mở lượt tiếp; không dùng lại slot pilot đã đóng.

**Dữ liệu cần:** Các kênh bước 01 + video cho từng session riêng + điều kiện sàn/tải/caster + failures/STOP/interventions.

**Đầu ra:** Bảng từng bánh: thời điểm đáp ứng theo clock có thể đo, vận tốc/overshoot, chênh trái–phải và biến thiên giữa các lượt; outcome thân xe riêng.

**Điều kiện chuyển bước:** Đây là pilot mô tả, không phải xác nhận tổng quát. Lượt lỗi/STOP/missing làm kết quả invalid hoặc unknown theo protocol; không tự thêm mẫu hoặc chỉnh gain/current.

## 04. Nhận dạng đáp ứng và bổ sung reference thân

**Trạng thái:** SAU 02–03; HAI NHÁNH. **Người làm:** Assistant fit/đánh giá model; bạn thu phép đo còn thiếu.

**Làm gì:** 4a: dùng command cuối + wheel feedback để fit combined delay/lag/gain, giữ nguyên cả session làm holdout. Nếu profile 2 s chưa đủ excitation thì đề xuất protocol ID riêng trước khi thu. 4b: thiết lập reference thân độc lập (ví dụ video có hiệu chuẩn và đồng bộ) cho displacement/speed/stopping; ghi uncertainty.

**Dữ liệu cần:** CSV command/wheel + raw bag/provenance, SI units, clocks, session split, geometry danh nghĩa; thêm reference thân theo thời gian khi cần body/slip claim.

**Đầu ra:** Model command→reported wheel có sai số holdout; reference thân có frame/unit/time/uncertainty. Công cụ SysID có thể tạo candidate, chưa tự cập nhật controller.

**Điều kiện chuyển bước:** Có thể làm wheel ID khi thiếu body reference, nhưng chỉ kết luận về bánh. Thiếu excitation/clock/reference thì unknown; không suy encoder odom là body GT hoặc fit đồng thời radius/slip/lag từ dữ liệu không đủ.

## 05. Làm mô hình Nino và baseline đáng tin

**Trạng thái:** SAU 04. **Người làm:** Assistant sửa model/evaluator; bạn xác nhận yêu cầu ứng dụng.

**Làm gì:** Đưa geometry và đáp ứng đã đo vào backend velocity phù hợp motor. Đối chiếu dự báo với session chưa dùng fit. Tuning B0/B1/governor trong ngân sách riêng. Chốt scenario, metric chất lượng, thời gian/tracking và mức cải thiện đáng quan tâm trước final evaluation.

**Dữ liệu cần:** Model/holdout bước 04; geometry/tải/caster cần cho claim; mục tiêu ứng dụng. Nếu claim qua gờ sau first contact, cần kiểm H2: actuator còn kịp tác động và cải thiện phase nào.

**Đầu ra:** Backend/model discrepancy report + baseline report + protocol benchmark có mục tiêu, split, metric và stop rule.

**Điều kiện chuyển bước:** Không dùng fixture sàn phẳng hiện có làm model Nino đã hiệu chuẩn. Nếu actuator không có useful authority cho contact envelope, chuyển sang shaping/preview/navigation/cơ khí. Nếu baseline đáp ứng mục tiêu, quyết định riêng giá trị cần thêm từ learning.

## 06. Train và so TD3/PPO/History/Governor

**Trạng thái:** CHƯA MỞ TRAIN NGHIÊN CỨU. **Người làm:** Assistant triển khai/chạy theo protocol và ngân sách được chốt.

**Làm gì:** Train TD3 và PPO bằng tương tác với simulator đã kiểm, có nhiều training seed theo ngân sách mới. Real bags dùng để nhận dạng/kiểm model. So B0, B1, Governor và các policy qua cùng evaluator; ablation history một frame/nhiều frame, authority/projection và governor khi cần.

**Dữ liệu cần:** Rollouts observation→proposal→accepted reference→feedback→reward; config/checkpoint/hash; labels chỉ cho evaluator; split toàn session/layout/payload; failures/interventions và held-out tests.

**Đầu ra:** Checkpoint ứng viên + bảng chất lượng/thời gian/tracking/failure + ablation và giới hạn generalization. 128 bước smoke hiện tại giữ là bằng chứng tích hợp.

**Điều kiện chuyển bước:** Chỉ promote khi có lợi ích đáng quan tâm so tuned baseline theo protocol, không dựa return đơn lẻ. Effect nhỏ/đổi chiều theo sampling thì unknown; không đổi objective, bỏ failures hoặc tự tăng mẫu.

## 07. Chạy shadow trên Pi bằng dữ liệu thật

**Trạng thái:** SAU KHI CÓ ỨNG VIÊN PHÙ HỢP. **Người làm:** Assistant chuẩn bị observer; bạn vận hành phiên được chốt.

**Làm gì:** Nạp actor/config đúng ABI vào observer chỉ đọc. Thu inputs thật và proposal với residual authority = 0; đo tuổi dữ liệu, inference time/memory/deadline dưới tải dự kiến. Kiểm frame, timestamp, history gap, source ownership và fallback.

**Dữ liệu cần:** Raw sensors/commands/status + shadow trace + actor/ABI/hash + thông tin tải Pi và clocks. Real shadow không đồng nghĩa ROS fixture tổng hợp hiện có.

**Đầu ra:** Báo cáo shadow thật: input hợp lệ, inference chạy kịp hay không, proposal có hợp lý/OOD không, lỗi/fallback nào xuất hiện.

**Điều kiện chuyển bước:** Shadow đạt chỉ xác minh ingestion/inference; không chứng minh policy cải thiện chuyển động. Hardware residual vẫn 0 cho tới bước 08; deadline thực cần đo trước khi chấp nhận.

## 08. Thử residual có giới hạn trên robot

**Trạng thái:** CHƯA MỞ TRIỂN KHAI. **Người làm:** Assistant chuẩn bị release/protocol; bạn giám sát thử thực.

**Làm gì:** Triển khai đường command ownership/projection/backend được review; chốt giới hạn, stop, RC/ROS semantics, fallback và ngân sách thử riêng. Bắt đầu trong envelope đã xác nhận, so từng lượt với baseline; chỉ mở tải/vật cản/route khác theo protocol tiếp.

**Dữ liệu cần:** Toàn bộ command/proposal/accepted/final/telemetry thật, reference thân, stop/fault/interventions, điều kiện mỗi session và outcome ứng dụng.

**Đầu ra:** Bảng lợi ích và giới hạn trên robot thật: chất lượng, tracking, thời gian, thất bại và phạm vi được phép dùng.

**Điều kiện chuyển bước:** Chỉ mở sau model/baseline/shadow và stopping/authority đủ bằng chứng. Không tự tăng tốc, alpha hoặc phạm vi vật cản. Không đạt mục tiêu thì dùng baseline hoặc đổi hướng theo kết quả.

## Khi thực hiện nhánh robot thật trong GUI

1. Mở **Nino → Xây project / sơ đồ → Việc cần làm**; chọn bước 01.
2. Bấm **Mở phiên diagnostic** để đến tab thu hiện có. Đây chỉ là chuyển trang.
3. Khi thực sự chuẩn bị thu: chuẩn bị bộ thu → Agent/cảm biến → inventory → đường lệnh ZERO → metadata/video → thu 60 s → bấm tiến riêng → chờ recorder đóng → QC → lưu quan sát → tải gói dữ liệu.
4. Dừng ở bước 02 để đánh giá trước khi mở đợt lặp mới.

**Kết quả cần nhận cho nhánh thật:** một bag và video cùng session để trả lời “lệnh có đến đúng tầng, feedback có là phản ứng bánh, thân có tiến và tự dừng không?”. Chưa cần chạy lại TD3/PPO smoke hoặc tăng tốc.

Nguồn hiện trạng: [triển khai phần mềm](NINO_RESIDUAL_IMPLEMENTATION_2026-11-04.md), [ledger kiểm chứng](NINO_RESIDUAL_VERIFICATION_2026-11-04.json). Nội dung outline được dùng chung từ `research_plan.json` trong GUI.
