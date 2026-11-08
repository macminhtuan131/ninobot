# Nino: phân tích offline checkpoint20k /25k /30k

## Quyết định

**Giữ classical scheduled cho envelope clear-box/planned-stop hiện tại.** Không sửa controller, không release ablation/train mới. Giữ ba checkpoint làm bằng chứng; chưa kết luận TD3 không thể học hoặc đã hội tụ.

## 1. Phạm vi và tính toàn vẹn

- Một learner seed11, ba checkpoint: không phải ba training seeds.
- Cùng corpus1680packet =12trajectory: hai block20k/30k ×B0/classical/TD3 ×stop6/8,140packet/run. Giữ block/arm/stop; không random-split frame hoặc suy CI từ packet tương quan.
- Đọc thêm toàn30.000training rows để đối chiếu action/reward/projection. Không load replay để học, không learn()/optimizer/ROS/Gazebo.
- 26input/checkpoint file hash kiểm lại sau đọc đều khớp; params/targets/optimizers/counters trước/sau probe giữ nguyên.
- Hai final actors tái hiện requested actions của chính các eval packets đã ghi: max error20k≈1,43e-6 và30k≈5,96e-7 do batch float inference. Checkpoint25k không có rollout outcome mới.
- Script audit ban đầu dừng ở representation reward: SB3 callback lưu float32, env giữ float64. Correction chỉ đổi expected storage cast; max rounding3,28e-11. File lỗi ban đầu được giữ, không đổi controller/tolerance tùy kết quả.

## 2. Phases và quyền tác động

Phase dùng decision clock trong plan_projection, không lấy task.elapsed_s ở sample kế tiếp. Startup0..0,5s; ramp-up theo nominal_not_steady; open25..54 hoặc25..74 ticks; withdrawal0,5s trước source-stop; ramp-down theo nominal positive; zero khi nominal về0.

|Stop|Open ticks/140|TD3 20k open RMS mm/s|TD3 30k open RMS|Classical block30k|TD3 30k SSE ngoài window|
|---|---:|---:|---:|---:|---:|
|6s|30|4.542|3.249|2.501|87.39%|
|8s|50|3.553|2.715|2.053|86.09%|

TD3 open-phase RMS giảm mô tả khoảng28,5%/23,6% từ block20k sang30k. Vì fresh launches khác nhau, không quy toàn bộ cải thiện cho training. Nhưng điều này bác cách đọc rằng mọi phase đều tệ đi khi native full-run RMS tăng.

86,1–87,4% SSE nằm ngoài window chỉ nói vị trí lỗi trên trajectory đã ghi. **Không phải trần benefit hoặc bằng chứng mọi lỗi đó bất khả điều khiển**: ramp-down có thể chịu ảnh hưởng tích lũy từ action trước đó. Riêng ramp-up xảy ra trước lần mở đầu tiên, policy contribution được kiểm bằng0; khác biệt trước can thiệp và follower/physical state làm full-route comparison không là exact-state causal test.

## 3. Requested → projected → published / driver diagnostics

Đối chiếu khớp trên1680eval+30.000train rows: requested policy/replay/previous feature; common window; mapping1D→2D; stateful ResidualReference replay; accepted wheels/body reference; final_ros_reference; từng reward term. Trong1680eval packet, driver requested/executed reference và published targets khớp các field đã ghi; current-command stamp đạt. Đây là telemetry backend sim, không phải torque hoặc execution phần cứng.

Các projection shadows20k/25k/30k chỉ dùng source/history/window đã ghi. Previous-request và sensor history của packet thuộc behavior gốc, nên shadow không tự nhất quán như một rollout policy mới và **không có body outcome counterfactual**.

## 4. Actor trên cùng corpus

|Checkpoint|Critic / actor updates|Mean requested action khi OPEN|Mean requested action ở zero|
|---|---:|---:|---:|
|20000|10000 / 5000|0.580|-0.523|
|25000|14999 / 7499|0.636|-0.386|
|30000|20000 / 10000|0.767|-0.412|

Actor có thay đổi chức năng: open proposals đi về bù dương mạnh hơn; không phải TD3 chưa có optimizer updates. Requested âm lúc gate đóng không là command quay lùi: mapping và driver đã được đối chiếu.

## 5. Reward và critic ranking

Reward hiện gồm tracking và phạt requested size/change cả khi gate đóng; source khớp thiết kế, chưa có bằng chứng đó là lỗi triển khai. Sau withdrawal cuối không còn window mở: có thể thay riêng chuỗi requested bằng nghiệm chi phí bậc hai, giữ nguyên hoàn toàn reference/body trajectory đã ghi. Với TD3 block30k, return tăng0,000682/0,000455 chỉ do giảm request cost; **không có cải thiện vận tốc mới**.

Critic được probe trên grid21actions[-1,1], min(Q1,Q2), cùng observation. Bellman residual dùng actor_target deterministic không thêm target noise; đó là diagnostic, không phải training target đầy đủ. MC return của behavior khác không là Q ground truth cho policy khác.

Kiểm mạnh hơn ở terminal: window đóng, horizon còn1decision, nên action ranking từ size/change cost biết chính xác theo previous requested; không cần counterfactual physics. Toàn reward≤0 cũng cho bound giá trị thực≤0. Kết quả:

|Checkpoint|minQ(actor)>0 trên corpus|Đúng grid ranking terminal /12|Mean abs Q error terminal|
|---|---:|---:|---:|
|20000|94.40%|2/12|0.001321|
|25000|84.94%|0/12|0.000799|
|30000|75.42%|1/12|0.000634|

Critic còn lệch giá trị và ranking dù error giảm; twin agreement hoặc loss nhỏ không tự chứng minh Q đúng. Đây là chẩn đoán approximation/optimization của một learner, **chưa xác định duy nhất nguyên nhân** là reward scale, coverage, architecture hay thời gian học. Không sửa một loạt hyperparameters dựa vào nó.

## 6. Điểm dừng và hướng sau

1. Khép phân tích offline này: không phát hiện lỗi contract cần sửa trong phạm vi audit; giữ classical cho benchmark đã xem, TD3 chưa promote.
2. Không chọn checkpoint25k từ probe để gọi là thắng: không có eval rollout25k. Không dùng analytic reward gain để gọi là motion gain.
3. Không tự mở ablation/train mới để chữa một nhãn critic. Giữ20k/25k/30k và các bảng làm tài nguyên; muốn mở TD3 tiếp phải chốt câu hỏi ứng dụng hoặc cơ chế còn quyền tác động và protocol riêng.
4. Tiêu chí đổi khuyến nghị: bằng chứng có lỗi implementation cụ thể; hoặc candidate có cải thiện task-quality phù hợp ứng dụng trên block/seed độc lập với native/GT reporting nhất quán. Loss/reward/Laya label riêng không đủ.
5. Đĩa còn1.88GiB lúc phân tích; mọi batch mới cần storage preflight riêng, không tự xóa raw hoặc hạ reserve.

Confidence cao cho kết quả số học/chain trong corpus này; vừa cho quyết định classical ở screen đã xem; chưa có cơ sở về generalization/contact/sim-to-real hoặc giới hạn cuối của TD3.

## Artifact

`protocol.json`, `corpus_index.csv`, `recorded_phase.csv`, `policy_phase.csv`, `critic_phase.csv`, `terminal_critic_check.csv`, `action_chain_packets.csv`, `projection_shadow_phase.csv`, `training_phase.csv`, `closed_request_cost_alternative.csv`, `analysis.json`, `decision.json`, `phase_review.png`, `reward_terms.png`. Scripts `analyze.py`/`summarize.py` chỉ ghi thư mục QA này.
