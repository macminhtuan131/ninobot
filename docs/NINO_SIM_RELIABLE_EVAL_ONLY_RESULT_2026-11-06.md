# Kết quả evaluation-only: B0, common cổ điển và ba TD3 RELIABLE

06/11/2026 · [N] Sim local mới; không thêm dữ liệu thật hoặc điều khiển robot.

## Quyết định

Đã đủ **10/10 lượt, 1.400/1.400 tick**, tất cả đạt task/dừng và gate đo. **Training/optimizer updates trong đợt: 0**; dùng ba checkpoint final của pilot3.072bước trước. 0/6 điều kiện TD3 seed/stop thấp hơn cả B0 và cổ điển ở native và hai grids.

[S] **Giữ common cổ điển/B0 làm baseline, chưa promote TD3 hoặc mở train dài.** Pilot chưa cho thấy ưu thế TD3 nhất quán so với baseline mạnh.

[N] Lỗi namespace evaluator trước đã được sửa bằng đúng lifecycle ở mọi arm và kiểm namespace trước control. Hai trạng thái được giữ riêng: learnerV1 failed ở evaluator nhưng train3seed đủ; eval-only mới hoàn tất. Không đổi trạng thái hoặc nối slot batch cũ.

## Thiết kế và bằng chứng

- Clear-box factory lab, tuyến thẳng, lịch dừng nguồn6/8s biết trước; không mixed map hoặc contact test.
- Cùng observation103D/action1D, history5, common±0,005m/s, preview/window/projection/follower/PI/reward/geometry. TD3 inference deterministic, không exploration.
- Mỗi arm có lifecycle/context/observer/partition mới; primary joint RELIABLE/depth100, independent BEST_EFFORT audit, không vá primary. Gate40ms không đổi.
- Kiểm hash ba checkpoint trước dùng; policy state và num_timesteps/critic_updates trước/sau giữ nguyên. Counter960 là số update lịch sử của mỗi learner, không là update trong eval.
- GUI đã thực sự bấm nút chạy job, có log tiến độ, bảng kết quả và khóa chạy lại budget đã đóng.

| Đại lượng | Kết quả |
|---|---|
| Status | completed |
| Artifact | `/home/tuanmac/nino_research/sim_reliable_eval_only_v1/20261106T031232193116Z_sim-reliable-eval-only` |
| Fingerprint | `66143dc17d9396944efa69d9668d859bf13973726dd4f49cfd6461d069abdd4f` |
| Manifest SHA256 | `2e111a3de591c2b5c616d9264392dc4f9cae3dadd74ae5962500edd50b645144` |
| Wall | 451.312s / deadline1.800s |
| Artifact hashes | 323 |
| Source pins trước job | 171 |
| Valid transitions / attempts | 1400 / 1400 |
| Launches | 10 / tối đa10 |
| Actor inference calls | 840 |
| Training / optimizer / hardware actions | 0 / 0 / 0 |
| Feedback checks | 4260 (không là số trial độc lập) |
| Joint endpoint age max, primary / independent | 1.0 / 1.0 ms |
| Canonical payload lệch trên stamp chung | 0 |
| Reader-only stamps theo phase | `{'independent_before_task': 69}` |
| Physics requests / retries | 2900 / 0 |
| Physics ACK/completion | True |
| Parameter readbacks | 20, complete=True |
| Causal estimator updates | 7000 |

## Kết quả từng lượt

Primary là vRMSE body so với nominal độc lập toàn14s tại native100ms. GT-header20ms/+10ms là diagnostics riêng; không nội suy body hoặc chọn grid thuận lợi.

| Slot | Arm / seed | Stop(s) | Native vRMSE(m/s) | GT20ms | GT+10ms | PathRMSE(mm) | Task/stop |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | B0 | 6 | 0.0047897 | 0.0060905 | 0.0060948 | 0.0181 | True/True |
| 2 | TD3/11 | 6 | 0.0065726 | 0.0078636 | 0.0078692 | 0.0561 | True/True |
| 3 | Classical_scheduled | 8 | 0.0039610 | 0.0059506 | 0.0059549 | 0.4305 | True/True |
| 4 | TD3/22 | 8 | 0.0041573 | 0.0059724 | 0.0059766 | 0.4885 | True/True |
| 5 | TD3/33 | 6 | 0.0064231 | 0.0077051 | 0.0077107 | 0.4879 | True/True |
| 6 | Classical_scheduled | 6 | 0.0039691 | 0.0059557 | 0.0059600 | 0.0230 | True/True |
| 7 | TD3/11 | 8 | 0.0073493 | 0.0085038 | 0.0085099 | 0.0526 | True/True |
| 8 | B0 | 8 | 0.0051594 | 0.0070434 | 0.0070485 | 0.6419 | True/True |
| 9 | TD3/22 | 6 | 0.0041568 | 0.0061980 | 0.0062025 | 0.0201 | True/True |
| 10 | TD3/33 | 8 | 0.0071773 | 0.0084458 | 0.0084519 | 0.0220 | True/True |

### TD3 so baseline theo cùng stop

Delta tương đối vRMSE (%), thứ tự native / GT20ms / GT+10ms. Âm là TD3 thấp hơn; không pooled ratio hoặc đổi estimand hậu nghiệm. Một launch/condition, chưa CI xác nhận.

| Seed | Stop(s) | TD3 so B0 (%) | TD3 so cổ điển (%) | Thấp hơn cả hai trên3grids |
|---|---:|---|---|---|
| 11 | 6 | +37.22 / +29.11 / +29.11 | +65.59 / +32.03 / +32.03 | False |
| 33 | 6 | +34.10 / +26.51 / +26.51 | +61.83 / +29.37 / +29.37 | False |
| 22 | 6 | -13.22 / +1.77 / +1.77 | +4.73 / +4.07 / +4.07 | False |
| 22 | 8 | -19.42 / -15.21 / -15.21 | +4.96 / +0.37 / +0.37 | False |
| 11 | 8 | +42.44 / +20.73 / +20.73 | +85.54 / +42.91 / +42.91 | False |
| 33 | 8 | +39.11 / +19.91 / +19.91 | +81.20 / +41.93 / +41.93 | False |

![So sánh native/header và path](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_reliable_eval_only_2026-11-06/evaluation_comparison.png)

## Giới hạn và chất lượng bằng chứng

- [N] Bằng chứng đủ cho controller comparison trên cấu hình này. Không mở lại audit logging giống hệt nếu không có failure/câu hỏi đo mới. Joint endpoint age ở biên không là latency actuator/body hoặc độ phân giải body1ms.
- [N] Không có upstream publication counter trong Gazebo. Không gọi loss-free chỉ vì hai reader cùng payload hoặc vì boundary support đạt; reader-only stamps được giữ nguyên theo phase.
- [N] Ba learner seeds đã train, mỗi eval condition một fresh launch. Không exact-state snapshot/pairing hoặc kiểm đầy đủ physics RNG. Native ticks và source samples không là trial độc lập.
- [N] Điều kiện stop6/8 đã thấy khi train, chưa holdout, history ablation hoặc generalization. Không có bằng chứng giảm impact/slip khi contact, vượt cáp mềm hoặc sim-to-real.
- [S] Effect nhỏ hoặc ranking đổi theo grid vẫn là unknown; minimum worthwhile effect chưa được chấp nhận. Không dùng return/loss/arrival thay chất lượng task.
- [N] Learner3.072bước là pilot có giới hạn, không phải chứng minh TD3 đã hội tụ hay TD3 nói chung không phù hợp. Đợt này chỉ đánh giá đúng các checkpoint đó.

## Audit offline sau kết quả: action, critic và coverage

[N] Trong steady-open, seed11/33 yêu cầu gần−1 ở mọi mẫu: common khoảng−0,005m/s. Seed22 yêu cầu trung bình+0,6744(stop6)/+0,6497(stop8), common+0,003372/+0,003248m/s. Classical yêu cầu+1/common+0,005m/s. Ánh xạ giữ đúng dấu và giới hạn; không thấy bằng chứng đảo dấu ở adapter.

Đây là diagnostic hậu nghiệm trên chính trajectory từng policy, không exact-state counterfactual, không thay primary toàn14s.

| Seed | Open-window replay n | Histogram request [−1,−0,5),[−0,5,0),[0,0,5),[0,5,1] | Q1 argmax trên20state, grid−1/−0,5/0/+0,5/+1 | Actor mean |
|---|---:|---|---|---:|
| 11 | 289 | [218, 53, 11, 7] | {'-1.0': 20} | -0.999966 |
| 22 | 289 | [5, 8, 99, 177] | {'0.5': 5, '1.0': 15} | 0.661615 |
| 33 | 289 | [216, 50, 17, 6] | {'-1.0': 20} | -0.999990 |

[N] Q1 của seed11/33 chọn−1 trên20/20state được lấy cách đều từ open-window của hai lượt eval chính seed đó; actor gần như tối đa hóa đúng Q1 của mình. Min(Q1,Q2) cũng nghiêng âm. Seed22 có Q1 chọn+0,5 hoặc+1. Replay mỗi seed chỉ289open-window samples; seed11/33 tập trung vùng âm. Snapshot parameters/counters trước/sau audit giữ nguyên, không có physics hoặc optimizer update.

[S] Kết quả phù hợp với vấn đề critic ranking/coverage và phụ thuộc seed trong pilot ngắn, thay vì riêng lỗi actor inference hoặc đảo dấu projection. Đây chưa là chứng minh critic sai counterfactual: chưa có outcome cho action thay thế trên cùng state, và Q học return gồm nhiều term.

**Quyết định:** giữ classical/B0 cho clear known-stop. Không tự tăng timesteps, đổi reward/gain hoặc thêm PPO/DR. Nếu vẫn theo nhánh RL, chỉ thiết kế một study có giới hạn để kiểm warmup/action coverage và critic ranking trước khi cấp training khác; phải khóa cả transition/optimizer budget, evaluation và điểm dừng. Không diễn giải dự đoán Q là risk probability hoặc safety guarantee.

Artifact phase audit: `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_reliable_eval_only_2026-11-06/phase_audit.json`; critic audit: `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_reliable_eval_only_2026-11-06/critic_audit.json`.

## Hướng đi kế tiếp

1. Giữ đợt này và learnerV1 đóng; không train lại để sửa evaluator. Kết quả adverse/unknown vẫn giữ.
2. Audit offline requested → windowed common → issued reference theo ramp/steady/withdrawal/deceleration/stop bằng trace đã có. Primary/gate không đổi; phase audit là diagnostic sau kết quả, không causal counterfactual.
3. Nếu TD3 chưa hơn common cổ điển: giữ classical/B0 cho clear known-stop và dừng mở train dài mặc định. Chỉ đề xuất một giả thuyết có thể bác bỏ từ phase audit trước protocol mới; không thêm PPO/DR/gain/reward search để che kết quả.
4. Nếu có tín hiệu đủ rõ: thiết kế holdout/baseline challenge riêng, chọn mức hiệu ứng có ý nghĩa và uncertainty trước thu. Contact/H2 hoặc triển khai real vẫn cần gate riêng.

**Một việc nên làm ngay:** dùng phase audit để quyết định giữ baseline hay có lý do kiểm thêm một giả thuyết learner. Không cần thêm physics, training hoặc real bag để trả lời bước này. Khuyến nghị chỉ thay đổi khi lợi ích so baseline và constraints đủ nhất quán trên phép đánh giá phù hợp.

## Truy xuất

- [Protocol](NINO_SIM_RELIABLE_EVAL_ONLY_PROTOCOL_2026-11-06.md)
- Audit: `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_reliable_eval_only_2026-11-06/analysis.json`; GUI review: `/home/tuanmac/nino_research/sim_reliable_eval_only_v1/review.json` (dẫn xuất ngoài raw, pin manifest đầu vào).
- `residual_reliable_eval_only.py`, correction evaluator, lifecycle frozen và YAML/script riêng.
- 22 kiểm tra evaluator/gates +41 GUI tests đạt; đây không phải63 trial robot. Build/install parity và GUI QA ghi trong verification riêng.
