# Goal100: review gap drive và so sánh frozen 10k/15k/20k — 14/11/2026

## 1. Kết luận đo được

- Đã tiêu thụ **24/24** lượt đã chốt; **23** lượt có measurement QC đạt, **18** task success trên các lượt có measurement hợp lệ.
- Phạm vi: sàn sạch và một gờ cứng Ø6mm tại0,65/1,05m; tuyến thẳng2m, một robot Sim, một training seed11.
- Ba checkpoint chạy deterministic, không exploration, không optimizer/replay update. B0 là cùng estimator/follower/velocity PI với residual bằngzero.
- Kết luận pilot có cấu trúc: `no_strict_task_count_advantage_even_best_case_missing_in_this_pilot`.
- Đây là hai fresh launch cho mỗi arm/layout, không có snapshot/restore. Mỗi block dùng cùng reset seed trong metadata, không coi đó là cùng trạng thái Gazebo hoặc một training seed độc lập.

**Quyết định:** giữ B0 làm reference, chưa đầu tư train dài thêm. B0 đạt5/6;10k đạt5/6;15k đạt4/6;20k có4pass,1fail và1unknown. Ngay cả khi lượt20k thiếu dữ liệu thành công, số task pass cũng chỉ đạt5/6, bằngB0 trong pilot đã cấp. Đây là nhận định về24slot này, không phải chứng minh TD3 luôn kém hơn ở mọi điều kiện.

## 2. Gap cũ đã được review

Raw episode57 vẫn khớp manifest gốc. Diagnostics tại2,616s báo `control_updates=1`, `control_raw_dt_sum_s=0,054` và `control_raw_dt_max_s=0,054`, trong khi chu kỳ cấu hình là0,002s. Chu kỳ dài này nằm ngay trong thông tin nodePI phát ra; không chỉ là thiếu một dòng ở recorderPython.
Hai recorder joint độc lập ghi51/51 payload khớp trong cửa sổ2,54–2,64s, max source gap2ms. World-control50ms có ACK, đủ physics iterations, không retry/overstep. Reference đangzero trong warmup nguồn.
Chưa tách được nguyên nhân sâu hơn giữa executor scheduling và clock delivery. Không suy ra từ chu kỳ cấu hình500Hz rằng PI thực thi đều mỗi2ms. Cũng không coi toàn bộ54ms là lỗi body motion vì đây là đoạn zero.
Job train ngày11/11 vẫn **failed rawQC**, ngưỡng40ms giữ nguyên. Evaluation là experiment mới với QC từng rollout; không sửa dữ liệu, cắt warmup hoặc đổi job cũ thànhpass.
Chi tiết nguồn và hash: [gap_review.json](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/goal100_gap_and_checkpoint_evaluation_2026-11-14/gap_review.json).

## 3. Điều kiện so sánh và giới hạn

- 4arm ×3layout ×2block =24slot; tối đa250task decisions/slot và6000decisions, wall cap45phút; không tự chạy bù.
- B0/10k/15k/20k dùng cùng world/envelope, damping caster0,001, PI Kp0,3/Ki0,1, torque cap4Nm, ramp/slew và scorer đã khóa. Physics1ms, policy100ms; nhịp control thực được audit riêng.
- Task gate giữ cross-track40mm, goal50mm/15°, quiet liên tục2s, deadline25s, toàn robot qua gờ. Đây là threshold engineering của Sim.
- Thứ tự arm được shuffle trước, cùng bộdev ở mỗi block. Không dùng layout validation1,25m/test1,50m.
- 10k có0optimizer update, là mốc trước học;15k có4.999critic;20k có10.000critic. Việc gọi cả ba là checkpoint không có nghĩa10k đã tối ưu actor.
- Những slot data-invalid được giữ và thể hiện làunknown, không được tính thành pass hoặc thay bằng runkhác. Kết quả từ tập data còn thiếu coverage không đủ chọn controller.
- B0 là baseline follower+PI, chưa đại diện cho mọi classical speed profile hoặc governor đã tune. Nếu có lợi ích soB0 thì vẫn cần đối chứng đơn giản phù hợp trước khi tuyên bố lợi thế thuật toán.

## 4. Task success theo từng layout

| Arm | Sàn sạch: success/valid/attempted | Gờ0,65m | Gờ1,05m | Tổng success/valid/attempted |
|---|---:|---:|---:|---:|
| B0 | 2/2/2 | 1/2/2 | 2/2/2 | 5/6/6 |
| TD3_10k | 2/2/2 | 2/2/2 | 1/2/2 | 5/6/6 |
| TD3_15k | 2/2/2 | 1/2/2 | 1/2/2 | 4/6/6 |
| TD3_20k | 2/2/2 | 1/2/2 | 1/1/2 | 4/5/6 |

20k không được báo4/6failure hoặc80% đáng tin cậy trên tập đủcoverage: một slot thiếu measurement. Bound sốpass trên6slot đã cấp là **4–5**. B0 và10k có5pass/6slot;15k có4pass/6slot. Không chạy bù slot16 để làm đầy dữ liệu sau khi thấy kết quả.

## 5. Tracking và thời gian

RMSE là trung bình bằng trọng số theo rollout có measurement hợp lệ, gồm cả task failures. Thời gian chỉ trên successful rollouts, đọc cùng success count; không gọi failure dừng sớm là nhanh hơn.

| Arm/layout | Path RMSE từng block (mm) | Max cross-track (mm) | Thời gian success từng block (s) |
|---|---:|---:|---:|
| B0/dev_clear | 0.302 / 0.049 | 0.507 / 0.066 | 17.100 / 17.100 |
| B0/dev_early | 0.174 / 2.989 | 0.253 / 4.823 | unknown/fail / 17.100 |
| B0/dev_late | 3.905 / 0.110 | 9.771 / 0.236 | 17.000 / 17.000 |
| TD3_10k/dev_clear | 0.355 / 0.043 | 0.740 / 0.058 | 17.100 / 17.000 |
| TD3_10k/dev_early | 9.479 / 4.358 | 15.640 / 8.080 | 17.100 / 17.100 |
| TD3_10k/dev_late | 1.135 / 2.463 | 2.002 / 5.117 | unknown/fail / 17.100 |
| TD3_15k/dev_clear | 0.609 / 0.657 | 0.916 / 1.004 | 16.000 / 15.800 |
| TD3_15k/dev_early | 3.381 / 0.280 | 7.810 / 0.444 | 16.000 / unknown/fail |
| TD3_15k/dev_late | 3.101 / 2.483 | 5.164 / 4.767 | 16.100 / unknown/fail |
| TD3_20k/dev_clear | 0.056 / 0.024 | 0.081 / 0.039 | 16.700 / 16.800 |
| TD3_20k/dev_early | 5.512 / 11.126 | 11.025 / 46.355 | 16.400 / unknown/fail |
| TD3_20k/dev_late | 2.368 / unknown/fail | 4.109 / unknown/fail | 16.800 / unknown/fail |

## 6. Không chắc chắn và giới hạn diễn giải

Hai lượt/arm/layout là pilot. Báo cả hai block và range; không dùng bootstrap nhỏ mẫu để gắn nhãn thắng chắc. Cùngreset seed không giữ caster/load/contact sequence như nhau. Initial physical pose/caster audit và source/control timing được lưu trong `evaluation_review.json`.
Tỷ lệ thành công của train113/126 trước đó không phải đối chứng cho các rollout frozen này. Không gộp với smoke384, với common103 taskstop6/8 hoặc với evaluation ngoài manifest của nhánh50k cũ.
Reward/loss không dùng để chọncontroller trong pilot; đọc task success, path và thời gian cùng nhau. Không chốt trade-off nhà máy chưa được chọn.

### Các failure có cơ chế khác nhau

- Slot8/10k vàslot11/B0 stall; slot20/15k cũngstall. Tại cuối các cửa sổ này wheel actual gầnzero dù wheel target vẫn khoảng3rad/s; effortSim khoảng1,3–1,5Nm, chưa chạm cap4Nm. Chưa có bằng chứng quy mọi stall thành giới hạn công suất motor hoặc gán hết cho algorithm.
- Slot15/15k đã qua gờ nhưngtimeout25s: thân xe còn cáchgoal58,8mm trong khi odometry ởx≈1,983m, thân xe thậtx≈1,941m. `estimated_goal_stop_latched` đã phátzero. Đây là lỗi hoàn thành nhiệm vụ liên quan estimator/follower stop; thêm optimizer update không tự sửa được lệnhbaseline đãlatchedzero.
- Slot19/20k vượt path gate40mm; maxcross-track≈46,35mm. Giữfailure, không bỏ spike.
- Slot16/20k lỗi trước taskepoch: wheel source age117ms, không tạo được reset hợp lệ. Chỉ códiagnostic; không coi là policy thất bại qua gờ.
Nguồn từngslot và finalstate: [failure_diagnoses.json](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/goal100_gap_and_checkpoint_evaluation_2026-11-14/failure_diagnoses.json).

## 7. Kiểm dữ liệu và đúng thực thi

- **789** file evaluation khớp manifest; mismatch0.
- **3648** native rows kiểm100D/1D, reward component sum và khôngtruth guidance. Tất cả action của TD3 được tính lại từ checkpoint deterministic và khớp trace.
- Policy tensors và counters được kiểm bất biến sau từng rollout; không có training step mới.
- Trong23taskepoch cóQC hợp lệ: drive source gap lớn nhất25ms; control dt lớn nhất7ms, không códtfallback/future-joint update được ghi trong các window đã đọc. Không coi cấu hình500Hz là bảo đảm mọi callback đúng2ms. Slot16 không cótaskepoch hợp lệ.
- Model/replay/checkpoint gốc chỉ được đọc; job train giữfailed. Raw mới được giữ đầy đủ.
- Software gate10tests kiểm matrix/budget, QC40ms, giữtaskfailure, xử lýdata-invalid và wall deadline. Các test này không phải10lượtGazebo.

## 8. Artifact và bước tiếp

Quyết định từ dữ liệu: Keep B0 as the reference and do not extend long training now. Even a successful missing learned-policy slot cannot exceed the B0 success count in this allocated pilot. Review goal-stop/odometry and startup timing before a targeted classical/reference ablation.
Không tự promote policy hoặc cấp thêm ngân sách train dài từpilot này. Bước nhỏ ưu tiên: đặc tả riêng việc dừng theoestimate có dự phòng sai số, giữ physical goalgate50mm, rồi kiểm fixture và một so sánhB0 có giới hạn. Đồng thời khoanh vùng startup wheel/clock ởslot16 từ raw đã giữ. Không sửa goallatch/PI/QC giữa24lượt hoặc dùngGT vào controller để ép đạtgoal.
Nếu sau đó đánh giá lại giá trịresidual về thời gian, cần đối chứng classical tốc độ/ramp phù hợp (ví dụ một common boost cố định trong giới hạn hiện tại, khóa trước khi chạy). Lượt này chưa thực hiện ablation đó. Không đổi đồng thờireward/history/actionscale/learningrate.

- [Biểu đồ so sánh](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/goal100_gap_and_checkpoint_evaluation_2026-11-14/checkpoint_comparison.png).
- [Review có cấu trúc, từngslot và timing](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/goal100_gap_and_checkpoint_evaluation_2026-11-14/evaluation_review.json).
- [Ledger24slot](/home/tuanmac/nino_research/goal100_checkpoint_eval_20261114_v1/ledger.json).
- [Protocol](/home/tuanmac/nino_research/goal100_checkpoint_eval_20261114_v1/protocol.json).
- [Raw và trace evaluation](/home/tuanmac/nino_research/goal100_checkpoint_eval_20261114_v1).
- [Log worker](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/goal100_gap_and_checkpoint_evaluation_2026-11-14/worker.log).
