> **Mới nhất06/11 — coverage V1 đã đóng lỗi wiring:** [kết quả](NINO_SIM_COVERAGE_RESULT_2026-11-06.md):1Gazebo launch/1raw tick,0replay/optimizer/eval,63slot còn lại đóng. Correction metadata riêng kiểm offline; chưa release V2. Các đoạn dưới giữ lịch sử.

# Release một study critic/coverage trong Gazebo

06/11/2026 · Tiếp yêu cầu “Tiếp tục làm theo recommandation cho nhánh Sim”.

## Phạm vi được mở

Chốt thực hiện đúng [draft](NINO_SIM_CRITIC_COVERAGE_PROTOCOL_DRAFT_2026-11-06.md)
và [implementation đã preflight](NINO_SIM_COVERAGE_IMPLEMENTATION_2026-11-06.md):
**một attempt** tại `~/nino_research/sim_coverage_study_v1`, action
`sim-coverage-study`. Sáu learner fresh theo order A11/C11/C22/A22/A33/C33,
mỗi learner1.024transition/960critic/480actor updates; rồi16evaluation×140tick.
Tổng tối đa6.144train +2.240eval,64launches,10.800wall seconds. Không retry,
resume, thêm smoke hoặc chạy bù slot. Một failure/cancel đóng các slot còn lại.
Không phần cứng, PPO, DR, Optuna hoặc thay gain/current/reward/QoS.

Pin implementation:
`1cd68b11dea8aee0302094294d89636276df23d6dfc2dc314af1c4a6433d89be`.
Pin preflight manifest:
`43981a39f32afdce9da8803ade22e49dc42b6d476a240896fe52515ca5978e83`.
Preflight45software tests và46GUI tests đạt; kiểm lại source/manifest/runtime
và root chưa tiêu thụ trước release. Dung lượng được đối chiếu với artifact
train/eval trước; không xóa dữ liệu cũ để chạy study.

## Quy tắc quyết định chốt trước dữ liệu mới

Giữ native velocity RMSE toàn14s làm primary; GT20ms/+10ms báo riêng. Mean
qua hai stop rồi qua ba seed bằng trọng số; giữ từng seed/stop và failure.
Không chọn grid hoặc checkpoint thuận lợi. Task/stop/support/integrity giữ
nguyên các gate của draft; sample gaps/spikes không bị bỏ.

- Cần coverage C mỗi bin≥10mẫu và≥5% open requests ở mọi seed. A cũng đủ
  coverage hoặc accepted profiles gần nhau thì contrast yếu/unknown.
- Chỉ xem là ứng viên cho **holdout riêng** nếu C tốt hơn A; mean vRMSE
  thấp hơn classical ít nhất5% trên cả ba grids;≥2/3seed tốt hơn classical
  ở cả hai stop/cả ba grids; không seed/stop nào tệ hơn classical quá5%;
  mọi constraint đạt. Đây là quy tắc nghiên cứu tạm thời, không phải yêu
  cầu nhà máy đã chấp nhận. `minimum_effect_accepted` vẫn null.
- Measurement hợp lệ nhưng không hơn classical: no-go cho mở rộng TD3
  clear known-stop; giữ baseline. Effect nhỏ/grid-sensitive/contrast yếu
  hoặc thiếu điều kiện: unknown, không tự tăng mẫu/budget. Q-grid chỉ là
  diagnostic, không counterfactual outcome hoặc safety guarantee.

## Release overlay và provenance

Draft JSON được giữ nguyên byte để không thay preflight fingerprint.
`residual_coverage_release_v1.json` là overlay chốt riêng: `released:true`,
`research_effect_rule_reviewed:true`, đúng hai pin trên, hardware=false.
Worker lưu release snapshot/protocol/dependencies và seal manifest khi đóng.
Không thay source runner/learner trong lúc study chạy. Bản train/eval cũ
vẫn đóng, không dùng checkpoint cũ thay learner A mới.

Kết quả sẽ được báo theo số slot thực tiêu thụ. Software readiness và
arrival đạt không tự chứng minh TD3 có lợi ích hoặc đủ triển khai robot.
