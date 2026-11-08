# Protocol Sim: chuyển lịch dừng sang6s — chốt trước physics

05/11/2026 · Người dùng yêu cầu tiếp tục nhánh Sim. Triển khai từ dự thảo
`NINO_SIM_STOP_SCHEDULE_TRANSFER_NEXT_2026-11-05.md`; đây là budget mới,
không mở lại các batch đã đóng. Không cài Spec Kit trong phạm vi này.

## Câu hỏi và budget

Candidate +0,005m/s có giữ thứ tự tracking tốt hơn B0 khi source stop6s,
withdraw=planned stop−0,5s=5,5s? Không tune lại amplitude/lead.

- Clear box, tuyến0°, warmup0,5s, cruise0,2m/s, horizon14s/140ticks.
- B0/classical/classical/B0/B0/classical, ba fresh launches/arm,
  tối đa6 lượt/840 evaluation ticks; optimizer/train/actor/hardware0.
- Cùng seed reset701 là nhãn khai báo, không exact-state pairing hoặc
  ba learner seeds. Giữ estimator, follower, h5/100D, projection/ramp/PI.
- Root `~/nino_research/sim_stop_transfer_v1`; action `sim-stop-transfer`.
  Fingerprint mới pin parent common; kiểm parent artifacts/runtime/hash
  trước ghi ledger. Sau ledger không retry hoặc tăng mẫu tự động.
- Backend source, guidance, scorer và task config đều stop6s. Candidate
  chỉ dùng reference/history validity/permission và known decision schedule;
  không GT/contact/body-speed input. B0 không gọi actor.

## Metric, chất lượng và quyết định

Primary: per-run nominal velocity RMSE toàn14s/native100ms. Secondary:
path/estimate, steady/deceleration RMSE, accepted residual, marker0,95m,
quiet stop2s. Engineering bounds giữ maxpath40mm, maxestimate50mm/yaw0,05rad,
chưa là yêu cầu nhà máy được chấp nhận.

Chốt trước diagnostic GT-header grid20ms và dịch+10ms, từ0,1s đến14s;
latest raw GT tại/trước grid, nominal held theo interval native tại GT header.
Không nội suy body. Mọi source gap/support age >20ms làm diagnostic unknown;
không vá primary hoặc loại spike. Hai grids không tăng độ phân giải GT50Hz.
Metric này khác reference alignment/aggregation native; giữ cả hai riêng.

Tín hiệu transfer mô tả cần cả ba classical native RMSE thấp hơn cả ba B0,
cùng thứ tự tách biệt ở cả hai diagnostic grids, không mất constraint.
Overlap/đảo chiều/thiếu diagnostic →unknown/giữ B0. Minimum worthwhile effect
vẫn null: kể cả có separation cũng chưa promote hoặc gọi lợi ích ứng dụng.
Không suy contact/H2 hoặc kết quả thật từ sàn sạch.

Physical/source/guidance failure đóng slot chưa dùng và lưu raw. Functional
gate failure cũng đóng slot còn lại với kết luận thất bại/unknown. Không retry,
thay objective/coverage hoặc tune theo outcome. Tối đa một correction có
nguyên nhân rõ chỉ trong contract khác trước khi phải quyết định dừng/chuyển.

## Gate offline trước launch

Kiểm sync stop ở backend/task/guidance/scorer; boundaries5,4/5,5/6,0s;
nominal adapter/scorer parity, zero source, stale/permission/fault/history,
projection/ramp; diagnostic causal support; native win không che đảo chiều;
ledger đã có không mở lại và failure giữ progress trước đóng slot.

## Artifact bàn giao

Protocol/config/source fingerprint; parent dependency manifest; ledger;
raw sensor/physics requests/parameter readbacks; trace requested/proposal/
accepted reference; per-run summary và timestamp diagnostic; aggregate
decision; manifest SHA256; report + GUI bảng6lượt và budget đã đóng.

Nếu có tín hiệu mô tả: giữ candidate cổ điển trong envelope đã xem, cân nhắc
baseline này cho nghiên cứu sau. Nếu fail/unknown: giữ B0, dừng tăng ngân sách
compensation; chỉ mở learner mới khi có remaining gap và giả thuyết rõ.
