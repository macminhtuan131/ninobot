> **Continuation đã khởi chạy07/11:** user đã chốt một lượt20k→30k, cùng profile/Ki0,10, không warmup mới;6eval cuối. [Trạng thái/log](NINO_COMMON_STUDIO_CONTINUATION_2026-11-07.md). Đoạn “proposal chưa chạy” bên dưới là trước quyết định này.

# TD3 common103D/1D — đánh giá pilot20k và khuyến nghị

Ngày07/11/2026. Pilot đã đóng **COMPLETED**, không còn là “đang warmup”.
Phạm vi: clear-box Sim, kế hoạch dừng6/8s đã biết, baseline Ki0,10 frozen.
Chưa có thí nghiệm vật cản hoặc robot thật mới.

## 1. Đã hoàn thành

| Hạng mục | Kết quả thực |
|---|---:|
| Fresh learner | seed11, common103D/1D, history5/10Hz |
| Transitions / replay | 20.000 /20.000 |
| Warmup | 10.000 transitions |
| Critic / actor optimizer updates | 10.000 /5.000 |
| Training launches / complete terminals | 143 /142 |
| Đoạn cuối | 120steps, right-censored; giữ riêng |
| Evaluation | 6/6runs,840ticks, tất cả task/stop/functional gates đạt |
| Tổng launches mới trong pilot | 149, không gồm smoke64 trước đó |
| Wall time worker | 7.425,99s, khoảng123,8phút |
| Integrity | 3.488file khớp SHA256; source identity khớp |
| Checkpoint load | model/targets/optimizer hữu hạn; counters khớp |
| Replay audit sau load | toàn20.000rows khớp observation/action/reward/next/terminal/timeout |
| Lifecycle | đóng sạch |

Worker lúc train audit256rows cuối; watcher và lần đánh giá offline này đã
đưa toàn20.000rows vào helper audit, không có buffer wrap. Chuỗi scope
“last up to256” cố định trong output helper của watcher không mô tả đúng
phạm vi lần gọi này; `rows_checked=20000` đã được kiểm lại bằng code thực.
Không sửa engine frozen chỉ để thay nhãn báo cáo.

Artifact:
`~/nino_research/td3_studio/20261107T054154365880Z_common_train`.
Manifest SHA256:
`1c0dba102f39adaaa419a682738713e701bbd8e9070113828821dbfe6e2db37f`.

Checkpoint final:
`checkpoints/step_000000020000_final/` trong artifact trên. Checkpoint5000 và
10000 có0update; checkpoint15000 có4999critic updates vì được lưu trước
optimizer call kế tiếp; final20000 có10000critic/5000actor. Không suy update
count bằng cách nhìn tên checkpoint hoặc progress log9999 trước update cuối.

## 2. So sánh kết quả cuối

**Primary: native velocity RMSE toàn14s, đơn vị mm/s; thấp hơn là tốt hơn.**

| Source stop | B0, không residual | Classical scheduled | TD3 final20k |
|---|---:|---:|---:|
| 6s | 4,750 | **3,971** | 4,129 |
| 8s | 4,965 | **4,148** | 4,163 |

- So với B0, TD3 giảm native RMSE **13,07% /16,16%** tại stop6/8.
  Hai GT grids cùng chiều giảm: khoảng11,05% /9,14%.
- So với classical, TD3 có native RMSE **cao hơn3,98% /0,37%**.
  Stop6: hai GT grids cũng cao hơn khoảng0,93%.
  Stop8: hai GT grids thấp hơn khoảng0,067%, trong khi native cao hơn.
  Chênh lệch rất nhỏ và đổi dấu theo reporting grid: **UNKNOWN** về ưu thế.
- Path RMSE của TD3 là **0,731mm /0,126mm**; classical là
  0,104mm /0,011mm. Các con số tuyệt đối nhỏ, nhưng không được giấu metric
  bất lợi. Mỗi arm là fresh launch, không exact-state branching; chưa quy
  toàn bộ chênh lệch cho actor hoặc sửa yaw/caster từ một so sánh này.
- 6/6task/stop đạt không tự chứng minh chất lượng tốt hơn. Chưa có repeat
  đủ để ước lượng variance/equivalence, CI hay lợi ích tổng quát.

**Kết luận được bảo vệ:** TD3 đã train thực sự và có tín hiệu tốt hơn
zero-residual trong screen này; **chưa chứng minh hơn classical scheduled**.
Đây không là kết luận TD3 hội tụ hoặc không thể cải thiện nếu train tiếp.

## 3. Những gì phân tích offline làm rõ

- Window residual mở ở **5.710/20.000transitions =28,55%**; còn lại14.290
  bị shared gate chặn tác động actuator. Dữ liệu này vẫn hợp lệ, không được
  tự loại để làm đẹp metric hoặc gọi tất cả là “data lỗi”.
- Warmup có2.865transition window mở; phần thu sau warmup có2.845.
  **Không gọi2.845 là số optimizer updates hữu ích:** updates lấy minibatch
  từ replay chứa cả dữ liệu warmup và các phase.
- Trên **cùng840observation packets đã ghi** từ sáu eval runs, actor mean
  ở window mở đổi **0 →−0,272 →+0,552** tại checkpoint10k/15k/20k.
  Đây là probe hành vi, không phải rollout mới hoặc chứng minh outcome
  checkpoint15k kém hơn checkpoint20k trong cùng trạng thái vật lý.
- Final actor có requested action khác0 trong phase window đóng, mean
  khoảng−0,436 trên corpus này. Shared adapter vẫn map thành residual0;
  không phải lệnh motor vượt gate. Đây là tín hiệu cần theo dõi về
  critic/reward/action-change, chưa đủ căn cứ sửa gate hoặc reward.
- Critic loss giảm và model/optimizer hữu hạn; actor vẫn đổi hành vi rõ
  ở nửa sau. **Loss giảm không chứng minh convergence hoặc control benefit.**

QA scripts, số liệu chi tiết và biểu đồ:
`artifacts/common_studio_pilot_2026-11-07/assessment.json`,
`pilot_assessment.png`, `analyze_completed.py` trong workspace client.
Script đánh giá không launch Gazebo, train thêm, đổi checkpoint hay phát
lệnh hardware. Không có physics/optimizer budget mới trong lượt đánh giá này.
GUI/to-do đã chuyển sang counters20k/10kcritic/5kactor qua verifier hash
result/manifest/job; bản A1024 vẫn giữ làm lịch sử. **67kiểm tra liên quan
đạt** sau cập nhật, không phải67lượt robot. Source/controller của pilot giữ nguyên.

## 4. Khuyến nghị tiếp theo

**Ưu tiên: đề xuất một continuation riêng +10.000steps, từ20k lên30k,
giữ nguyên profile/controller/reward/history. Chưa khởi chạy.**

Lý do: actor gần đây còn thay đổi đáng kể; cần phân biệt “chưa ổn định sau
warmup” với hạn chế của thiết kế trước khi tune nhiều yếu tố hoặc bỏ TD3.
Không đặt điều kiện TD3 phải thắng classical trước khi được train tiếp.

### Budget đề xuất, không tự nối thêm

- Resume đúng final20k, cùng seed11, profile research h5, model/targets/
  optimizer/replay; episode physics mới, không bit-exact restore.
- Thêm10.000transitions, không có warmup mới. Nếu hoàn tất bình thường:
  global30.000, tổng20.000critic/10.000actor updates, replay30.000 vẫn nằm
  trong capacity32.768. Counters thực phải được kiểm sau chạy.
- Checkpoint mỗi5.000steps thêm; wall cap180phút; tối đa73training launches.
- Final eval cùng6condition/840ticks. Baseline mới là đối chứng của block
  mới; so20k với30k từ hai block vẫn chỉ mô tả, không exact-state causal test.
- Disk preflight dự toán4,15GiB trống bao gồm1GiB reserve; lúc chuẩn bị có
  khoảng4,68GiB. Phải kiểm lại trước launch; không hạ reserve/xóa dataset.
- Dừng khi lỗi measurement/physical/source hoặc hết budget; giữ failures,
  không retry/tự gia hạn hoặc chọn checkpoint thuận lợi từ eval cuối.
- Sau30k phải quyết định: có dấu hiệu tiến bộ đáng kiểm bằng repeat/seeds;
  hoặc unknown/cần đúng một ablation có căn cứ; hoặc giữ classical cho
  benchmark đơn giản này. Không hứa thêm budget vô hạn hoặc coi30k đủ hội tụ.
- Tiêu chí screening **đề xuất cho lượt tiếp**, chưa phải yêu cầu ứng dụng
  được chấp nhận: giảm ít nhất5% velocity RMSE so classical ở cảstop6/8 và
  cả3grids, đồng thời giữ task/stop/physical/tracking gates. Đạt thì chỉ là
  candidate cần repeat/seeds; nhỏ hơn hoặc đổi dấu thì UNKNOWN, không tự
  thêm bước. Không dùng ngưỡng này diễn giải lại pilot20k thành phép kiểm
  xác nhận hoặc cấm continuation trước khi TD3 thắng baseline.

Request **proposal chưa release**:
`artifacts/common_studio_pilot_2026-11-07/continuation_10k_PROPOSAL_NOT_RELEASED.json`.
Đã kiểm schema/resume compatibility offline; chưa tạo training job mới.

### Sau continuation, chưa làm ngay

1. Nếu tín hiệu ổn định: chốt repeat/block và independent training seeds;
   giữ seen evaluation tách holdout. Không cộng A/C/smoke vào số seed mới.
2. Nếu plateau hoặc vẫn đổi mạnh: xem requested/executed actions, critic
   ranking và reward theo phase; chọn **một** ablation/version mới, thay vì
   đổi LR/history/reward/action/DR cùng lúc. Chưa có căn cứ đổi ngay h5 hoặc LR.
3. Chỉ mở obstacle/contact/OOD khi có câu hỏi và protocol riêng. Kết quả
   planned-stop trên sàn sạch không chứng minh governor qua cáp hoặc sim-to-real.

**Một việc nên làm tiếp:** chốt budget continuation10k giữ nguyên cấu hình.
Khuyến nghị sẽ đổi nếu có bằng chứng replay/target/action contract sai,
physics/measurement failure, hoặc một ablation offline chỉ ra lỗi triển khai
cụ thể; các kiểm tra hiện tại chưa tìm thấy lỗi đó.
