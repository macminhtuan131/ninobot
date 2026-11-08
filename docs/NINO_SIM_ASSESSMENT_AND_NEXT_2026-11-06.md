> **Mới nhất06/11 — Gain baseline Gazebo đã đóng9/9:** 1.260ticks;283hashes/3.834support checks đạt,0actor/train. Causal/fixed native: +23,0% tại1; +29,8% tại0,98; −15,3% tại1,02. SoB0 còn sampling-sensitive ở1/0,98; chưa promote/learner. Tiếp correction estimator cổ điển offline. [Kết quả](NINO_SIM_GAIN_BASELINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Backend/context gain đạt parity offline:** 41 software tests; 4.800 callbacks kernel và 840 transitions wrapper fixture, 0 Gazebo/train mới. Cùng gain=1 giữ observation/reward/reference/terminal, context ABI mới chặn checkpoint cũ. Tiếp runner/release baseline qualification riêng. [Kết quả](NINO_SIM_GAIN_CONTEXT_OFFLINE_RESULT_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Tiếp theo 06/11 — Benchmark đã chốt offline:** giữ cổ điển cho clear known-stop; câu hỏi mới chỉ về gain common cố định chưa biết. Đã kiểm causal encoder candidate và phân rã 840 hàng cũ; 0 physics/training mới. Tiếp backend/context riêng, parity gain=1 trước qualification baseline. [Quyết định](NINO_SIM_BENCHMARK_DECISION_2026-11-06.md). Các đoạn dưới giữ lịch sử.

> **Mới nhất 06/11 — Eval reset-ready đã đóng 6/6:** 840 eval ticks, 0 train/optimizer. A seed11 có native velocity RMSE cao hơn cổ điển 71,5%/88,8%; hai GT grids cùng chiều. 199 hashes/2.561 support checks đạt. Giữ cổ điển cho clear known-stop; chốt benchmark trước training mới. [Kết quả](NINO_SIM_READY_EVAL_ONLY_RESULT_2026-11-06.md). Real cutoff vẫn 02/11; các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Reset drive ACK qualification đạt2/2:** candidate gate giữcap5s,20zero ticks,0actor/optimizer;68hashes/72support checks/closure đạt. ACK muộn mới kiểm bằngfixture,không suy general reliability. Tiếp thiết kế eval-only A/B0/cổ điển,khôngtrain mới. [Kết quả](NINO_SIM_DRIVE_READINESS_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — Coverage V2 đã đóng:** A seed11 hoàn tất, C seed11 partial; **1.864 replay /1.736 critic /868 actor updates,0eval**,15launches;49slot còn lại đóng. Lỗi initial drive readiness/permission, không phải thiếu joint của observer. Candidate correction chỉ kiểm offline; [kết quả](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Cập nhật06/11 — Coverage V2:** runner mới đã nối metadata vào full train path; preflight qua GUI **80 tests đạt**, GUI **54 tests đạt**, build2package. Chưa release physics hoặc có scientific train/eval mới. V1 vẫn đóng; [kết quả V2](NINO_SIM_COVERAGE_V2_IMPLEMENTATION_2026-11-06.md). Các cập nhật dưới giữ lịch sử.

> **Mới nhất06/11 — coverage V1 đã đóng lỗi wiring:** [kết quả](NINO_SIM_COVERAGE_RESULT_2026-11-06.md):1Gazebo launch/1raw tick,0replay/optimizer/eval,63slot còn lại đóng. Correction metadata riêng kiểm offline; chưa release V2. Các đoạn dưới giữ lịch sử.

> **Cập nhật06/11 — coverage implementation:** sampler/runner và preflight qua nút GUI đã đạt;91tests/build2package. [Báo cáo](NINO_SIM_COVERAGE_IMPLEMENTATION_2026-11-06.md). Chưa release study6144train+2240eval; không có training/Gazebo/hardware mới. Các đoạn dưới giữ lịch sử.

# Đánh giá nhánh Sim và hướng đi tiếp theo

06/11/2026. Cập nhật sau khi hoàn tất evaluation-only và audit offline.

## Kết luận hiện tại

**Hạ tầng đã đủ cho phép so sánh controller trong bài thử này. Chất lượng
policy TD3 và phạm vi đánh giá là hai vấn đề cần tập trung tiếp.**

| Hạng mục | Bằng chứng đã có | Kết luận được phép |
|---|---|---|
| Learner | 3 seed × 1.024 bước; model/targets/optimizer/replay được kiểm | Pipeline train hoạt động; chưa chứng minh hội tụ |
| Evaluator | 10/10 lượt, 1.400 tick, task/dừng đạt; optimizer mới 0 | Đã sửa lỗi wiring và có comparison hợp lệ |
| Acquisition | 4.260 support checks; joint age tối đa 1 ms ở hai reader | Đủ support theo contract; không chứng minh toàn luồng loss-free |
| Tracking | Cổ điển có vRMSE thấp hơn cả 6 lượt TD3 trên native và hai grids | Giữ cổ điển/B0 làm baseline cho clear known-stop |
| Actor/critic | Seed 11/33 gần −1 trong steady-open; Q1 cũng chọn −1 trên 20/20 state được audit mỗi seed | Phù hợp với vấn đề critic/coverage trong pilot; chưa chứng minh nguyên nhân độc lập |
| Generalization | Sàn sạch, stop 6/8 s đã dùng khi train | Chưa có holdout, contact benefit hoặc sim-to-real |

Các checkpoint giữ nguyên; learner V1 vẫn mang trạng thái failed do evaluator
cũ. Eval-only mới là một job completed riêng. Không mở lại partial 700 bước.

## Số liệu quyết định

Native vRMSE toàn 14 s, đơn vị m/s:

| Source stop | B0 | Common cổ điển | TD3 seed 11 | TD3 seed 22 | TD3 seed 33 |
|---|---:|---:|---:|---:|---:|
| 6 s | 0,0047897 | **0,0039691** | 0,0065726 | 0,0041568 | 0,0064231 |
| 8 s | 0,0051594 | **0,0039610** | 0,0073493 | 0,0041573 | 0,0071773 |

Seed 22 gần baseline mạnh hơn hai seed còn lại, nhưng vẫn kém cổ điển về
vRMSE. So với B0 ở stop 6 s, seed 22 tốt hơn khoảng 13,22% trên native nhưng
tệ hơn khoảng 1,77% trên hai grid GT. Vì vậy không chọn riêng native để
tuyên bố lợi ích. So với cổ điển, cả sáu lượt TD3 đều kém trên cả ba grids.

Path RMSE các arm trong khoảng 0,018–0,642 mm và đều đạt bound đã chốt;
không kết luận một controller thắng mọi metric. Chưa có mức hiệu ứng tối
thiểu được chấp nhận theo yêu cầu ứng dụng. Mỗi condition chỉ một lượt eval.

## Vì sao chưa nên tăng timesteps mặc định

**[N]** Trong steady-open, seed 11/33 bù khoảng −0,005 m/s; seed 22 bù
khoảng +0,00325 đến +0,00337 m/s; cổ điển bù +0,005 m/s. Trace giữ đúng dấu
requested → windowed → issued reference; không thấy dấu hiệu đảo mapping.

**[N]** Replay mỗi seed có 289 mẫu open-window, các seed 11/33 tập trung vùng
action âm. Q1 của hai seed đó ưu tiên −1 trên tập state được audit; actor
đang đi theo critic của mình. Audit không thêm physics hoặc optimizer update.

**[S]** Điều này gợi ý ưu tiên kiểm critic ranking, coverage/warmup và tính
phụ thuộc seed. Chưa đủ để kết luận TD3 nói chung không phù hợp, hoặc chỉ
cần train lâu hơn sẽ sửa được. Giá trị Q cho action khác chưa có outcome
counterfactual trên cùng state, và return có nhiều term ngoài vRMSE.

## Việc tiếp theo, theo thứ tự

1. **Giữ các job đã đóng và dùng cổ điển/B0 làm reference Sim.** Review kết
   quả/phase/critic đã có trong GUI và báo cáo. Chưa deploy controller này
   lên robot hoặc gọi nó là governor post-contact đã thành công.
2. **Nếu tiếp tục nghiên cứu RL: chỉ thiết kế một study có giới hạn về
   warmup/action coverage và critic ranking.** Khóa trước transition và
   optimizer budget, seed, conditions, baseline, metric và điểm dừng. Nêu
   rõ thay đổi cả coverage và timing cập nhật nếu có; không gọi nó là một
   ablation đơn yếu tố khi còn confound. Chưa release training mới ở lượt này.
   **Cập nhật cùng ngày:** [draft critic/coverage](NINO_SIM_CRITIC_COVERAGE_PROTOCOL_DRAFT_2026-11-06.md)
   đã chuẩn bị: Gaussian so với probe phân tầng, hai arm fresh × ba seed ×
   1.024 bước, giữ warmup64 và update schedule. Config/planner offline có
   kiểm budget; sampler/runner và release chưa có, chưa train thêm.
3. **Sau study đó mới quyết định learning tiếp hay chuyển trọng tâm.** Nếu
   vẫn không hơn cổ điển hoặc policy tiếp tục bão hòa sai hướng, dừng mở rộng
   TD3 cho bài toán clear known-stop. Chuyển sang baseline/operating envelope
   và bài toán ứng dụng có yêu cầu cụ thể. Nếu có lợi ích, kiểm holdout riêng
   trước khi mở rộng contact, history ablation hoặc domain randomization.

Không thêm logging fixture giống hệt khi chưa có failure hoặc câu hỏi đo
mới. Không tự đổi gain/current/reward/QoS, chạy Optuna/PPO/DR hoặc tăng mẫu
để làm kết quả thuận lợi hơn. Dữ liệu thật phục vụ SysID/calibration và
reference thân theo protocol riêng; chưa cần real bag mới cho quyết định Sim này.

**Một việc nên làm ngay:** chốt câu hỏi và protocol của một study critic/
coverage cuối cùng, nếu mục tiêu vẫn cần RL. Đầu ra trước khi chạy là ma
trận biến giữ cố định, budget, baseline và go/no-go. Khuyến nghị thay đổi
khi có lợi ích so baseline dưới constraints và phép đánh giá phù hợp.

## Tài liệu gốc

- [Kết quả và audit đầy đủ](NINO_SIM_RELIABLE_EVAL_ONLY_RESULT_2026-11-06.md)
- [Protocol evaluation-only](NINO_SIM_RELIABLE_EVAL_ONLY_PROTOCOL_2026-11-06.md)
- [Pilot train và lỗi evaluator cũ](NINO_SIM_RELIABLE_TD3_RESULT_2026-11-06.md)
