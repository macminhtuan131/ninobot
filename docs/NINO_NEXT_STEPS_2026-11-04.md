> **Mới nhất06/11 — Gain baseline Gazebo đã đóng9/9:** 1.260ticks;283hashes/3.834support checks đạt,0actor/train. Causal/fixed native: +23,0% tại1; +29,8% tại0,98; −15,3% tại1,02. SoB0 còn sampling-sensitive ở1/0,98; chưa promote/learner. Tiếp correction estimator cổ điển offline. [Kết quả](NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Backend/context gain đạt parity offline:** 41 software tests; 4.800 callbacks kernel và 840 transitions wrapper fixture, 0 Gazebo/train mới. Cùng gain=1 giữ observation/reward/reference/terminal, context ABI mới chặn checkpoint cũ. Tiếp runner/release baseline qualification riêng. [Kết quả](NINO_SIM_GAIN_CONTEXT_OFFLINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Benchmark đã chốt offline:** giữ cổ điển cho clear known-stop; câu hỏi mới chỉ về gain common cố định chưa biết. Đã kiểm causal encoder candidate và phân rã 840 hàng cũ; 0 physics/training mới. Tiếp backend/context riêng, parity gain=1 trước qualification baseline. [Quyết định](NINO_SIM_BENCHMARK_DECISION_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Mới nhất 06/11 — Eval reset-ready đã đóng 6/6:** 840 eval ticks, 0 train/optimizer. A seed11 có native velocity RMSE cao hơn cổ điển 71,5%/88,8%; hai GT grids cùng chiều. 199 hashes/2.561 support checks đạt. Giữ cổ điển cho clear known-stop; chốt benchmark trước training mới. [Kết quả](NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md). Real cutoff vẫn 02/11; các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Reset drive ACK qualification đạt2/2:** candidate gate giữcap5s,20zero ticks,0actor/optimizer;68hashes/72support checks/closure đạt. ACK muộn mới kiểm bằngfixture,không suy general reliability. Tiếp thiết kế eval-only A/B0/cổ điển,khôngtrain mới. [Kết quả](NINO_SIM_DRIVE_READINESS_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Coverage V2 đã đóng:** A seed11 hoàn tất, C seed11 partial; **1.864 replay /1.736 critic /868 actor updates,0eval**,15launches;49slot còn lại đóng. Lỗi initial drive readiness/permission, không phải thiếu joint của observer. Candidate correction chỉ kiểm offline; [kết quả](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Cập nhật06/11 — Coverage V2:** runner mới đã nối metadata vào full train path; preflight qua GUI **80 tests đạt**, GUI **54 tests đạt**, build2package. Chưa release physics hoặc có scientific train/eval mới. V1 vẫn đóng; [kết quả V2](NINO_SIM_COVERAGE_V2_IMPLEMENTATION_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — coverage V1 đã đóng lỗi wiring:** [kết quả](NINO_SIM_COVERAGE_RESULT_2026-11-06.md):1Gazebo launch/1raw tick,0replay/optimizer/eval,63slot còn lại đóng. Correction metadata riêng kiểm offline; chưa release V2. Các đoạn dưới giữ lịch sử.

> **Cập nhật06/11 — coverage implementation:** sampler/runner và preflight qua nút GUI đã đạt;91tests/build2package. [Báo cáo](NINO_SIM_COVERAGE_IMPLEMENTATION_2026-11-06.md). Chưa release study6144train+2240eval; không có training/Gazebo/hardware mới. Các đoạn dưới giữ lịch sử.

> **Kế tiếp06/11 — draft critic/coverage:** [Protocol mới](NINO_SIM_CRITIC_COVERAGE_PROTOCOL_DRAFT_2026-11-06.md) đã chuẩn bị:2arm×3seed×1024, cùng960critic/480actor updates mỗi learner;16eval đề xuất. Chưa runner/release/train mới. Triển khai sampler/replay parity và software preflight trước chạy. Classical/B0 vẫn là reference; các cập nhật dưới giữ lịch sử.

> Cập nhật06/11: evaluation-only mới đã đóng, dùng ba checkpoint TD3 có sẵn; không train thêm. Xem [kết quả](../docs/NINO_SIM_RELIABLE_EVAL_ONLY_RESULT_2026-11-06.md) và [protocol](../docs/NINO_SIM_RELIABLE_EVAL_ONLY_PROTOCOL_2026-11-06.md). Chưa promote/hardware.

> Cập nhật06/11: pilot TD3 RELIABLE với lifecycle từng episode đã đóng; xem [kết quả](../docs/NINO_SIM_RELIABLE_TD3_RESULT_2026-11-06.md) và [protocol](../docs/NINO_SIM_RELIABLE_TD3_PROTOCOL_2026-11-06.md). Chưa promote hoặc mở training/hardware mới.

> **Cập nhật06/11 — candidate joint RELIABLE:** fixturepaired1000messages +1handshake/pause100ms đạtcompatibility, cảBE/RELIABLE1000/1000; candidateB0stop6/8 đạt2launches/280ticks. GUI hai nút cógate +QC/metric;khóa stageđãđóng. Chưa optimizerload/training hoặc rootcauseproof, partialTD3700ticks giữ. Tiếp learnerfresh103D/1D protocol riêng. [Kết quả](NINO_SIM_JOINT_RELIABILITY_RESULT_2026-11-06.md).

> **Cập nhật06/11 — joint diagnostic đã đóng2/2:**200zero ticks/612checks đủsupport; hai observer trùng15.220source stamps, payloadfield không lệch. Chưa tái hiện50ms, nguyênnhânunknown; khôngtraining/hardware hoặc reopenpartialTD3. GUI có profile và bảngage/parity/error. Tiếp tốiđa mộtcandidateQoSjointRELIABLE riêng, chưa áp/chạy. [Kết quả](NINO_SIM_JOINT_BOUNDARY_RESULT_2026-11-06.md).

> **Cập nhật06/11/2026 — TD3 common103D/1D đã train partial:**700ticks/636critic +318actor updates,5training episodes đạt task/stop. Episode6 thiếu joint support50ms tại half-tick zero; batch đóng, seed22/33 +10eval chưa chạy. GUI có profile riêng và partial/error review, khóa retry. Chưa có learned-benefit comparison hoặc hardware. Xem [kết quả](NINO_SIM_COMMON_TD3_RESULT_2026-11-06.md).

> **Mới nhất05/11:** [Wrapper103D/1D đã đạt4/4Gazebo integration](NINO_SIM_EQUAL_GAZEBO_RESULT_2026-11-05.md),560ticks,actor/optimizer0. Tiếp [fresh TD3 common-only pilot](NINO_SIM_COMMON_TD3_PILOT_NEXT_2026-11-05.md) theo draft3seeds×1024, chưa mở budget/chạy. Các cập nhật dưới là lịch sử theo thời điểm.

> **Mới nhất05/11 — phần mềm:** [Contract103D/1D cùng preview đã qualify offline](NINO_SIM_EQUAL_INFORMATION_RESULT_2026-11-05.md).840bước fixture,không train/Gazebo; [draft qualification wrapper trong Gazebo](NINO_SIM_EQUAL_INFORMATION_GAZEBO_NEXT_2026-11-05.md) tối đa4launches/560ticks, chưa chạy. Tiêu chí benefit và gate integration tách riêng; không cần đợi real data.

> **Mới nhất05/11:** [Stop-time transfer đã đóng6/6](NINO_SIM_STOP_TRANSFER_RESULT_2026-11-05.md), actor/optimizer0. Native và hai GT-header grids đều tách tốt hơn B0; chưa promote. Tiếp [contract TD3/cổ điển cùng thông tin](NINO_SIM_EQUAL_INFORMATION_NEXT_2026-11-05.md), chưa mở train/physics mới. Các cập nhật dưới đây là lịch sử theo thời điểm.

> **Mới nhất05/11:** [Common cổ điển đã đóng6/6](NINO_SIM_CLASSICAL_COMMON_RESULT_2026-11-05.md), optimizer0. Velocity RMSE toàn14s tốt hơn B0/frozen common trong batch đã xem. Candidate chưa promote; tiếp [kiểm stop6s/withdraw5,5s](NINO_SIM_STOP_SCHEDULE_TRANSFER_NEXT_2026-11-05.md), draft chưa chạy.


> **05/11 — baseline V3 đã xong:** [8 lượt estimator + follower trong Gazebo](NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md), residual zero. Tất cả đạt marker + stop; guided RMSE tuyến 13,09–13,84 mm. Không train TD3 mới. V1/V2/clear-bias là các batch lịch sử riêng.

## Nhánh sim — thứ tự tiếp tục

1. **Đã làm:** estimator wheel+IMU causal, follower và reference pipeline đã nối vào Gazebo; clear-floor baseline V3 đóng đủ 8/8 lượt, không chỉnh GT vào estimate.
2. **Đã làm:** [screen guided clear/gờ 6 mm](NINO_SIM_GUIDED_CONTACT_RESULT_2026-11-05.md), đủ 4/4 lượt theo protocol mới, residual zero; giữ riêng V3 clear ±5°. Tất cả marker + stop; gờ RMSE path3,09–4,28 mm.
3. **Đã làm:** V3 giữ h5, actor/target zero-init và task/reward/baseline identity mới; kiểm replay/save-load. Train512/496 updates và evaluate8 đã đóng; không resume V2. Chưa có learned benefit.
4. **Đã làm:** ablation frozen actor full/common-only/B0 trên clear, đủ6 lượt/840 ticks/optimizer0. Diff là nhánh có hại trong batch; common bù tốt steady nhưng làm deceleration tệ hơn. Giữ B0, đối chứng bù common cổ điển có rút trước lịch dừng đã chạy6/6, velocity RMSE thấp hơn cả hai đối chứng. Stop-time transfer6s đã đóng6/6,840ticks,actor/optimizer0; native và hai grids cùng tách tốt hơn B0. Contract103D/1D đã qualify offline và4/4Gazebo integration; tiếp fresh TD3 common-only pilot theo draft mới, chưa mở learner budget. Gờ có B0 failure giữ nguyên; chưa mở multi-seed/history/scale-up.

**GUI:** Xây project → NHÁNH SIM → **Qualification103D/1D · Gazebo ·4lượt**. Xem bảng sáu lượt, primary/phase metrics và decision bù cuối; TD3 V3 cùng các baseline trước xem tại selector riêng. Stage hoàn tất hoặc lỗi đều khóa ngân sách đã tiêu thụ. Không cần Pi hoặc real dataset cho bước sim tiếp theo.

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
