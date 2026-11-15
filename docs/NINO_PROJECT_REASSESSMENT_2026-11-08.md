# Rà soát Nino sau PI stop6, prestop và common103_v2 — 08/11/2026

> **Tiếp sau E1:** [E2 đã chuẩn bị offline](NINO_FIXED6MM_AUTHORITY_PREPARATION_2026-11-08.md), 12 lượt đề xuất/0 allocated; oracle manifold, chưa có runner/release physics.

> **Cập nhật sau review:** E1 đã đóng 280 train +840 eval transitions; 2 episode train và 6 evaluation đạt integration, có một correction GUI reader. [Kết quả và việc tiếp theo](NINO_COMMON103_V2_INTEGRATION_RESULT_2026-11-08.md). Nội dung dưới là review trước E1, không phải trạng thái live sau chạy.

## 1. Quyết định

**Giữ nhánh Sim, sửa v2 và kiểm integration trước; chưa chạy campaign 3×50k.**
TD3 có train thật ở v1 và smoke thật ở v2. Chưa có bằng chứng nó hơn baseline
trong benchmark hiện tại. Chuyển sang gờ là một câu hỏi nghiên cứu mới, không
phải kết luận TD3 sẽ thắng hoặc classical không thích nghi được.

Ký hiệu: **[N]** code/dữ liệu Nino đã đọc; **[S]** suy luận có giới hạn;
**[Đ]** kế hoạch chưa chạy/chưa được cấp ngân sách trong lượt review này.

## 2. Tiến độ và hiệu quả thực tế

| Thành phần | [N] Đã đạt | Chưa thể kết luận |
|---|---|---|
| TD3 common103_v1 | Một learner seed11 đạt global 30k; đã có 20k/25k/30k và evaluation | Chưa thắng classical trong clear-box/planned-stop; không dùng một training seed để suy ổn định đa seed |
| PI Ki0.15, stop6 | 4 lượt/560 ticks; native vRMSE giảm 21,41% và 11,36% theo hai block | GT block1 chỉ giảm khoảng 0,24%; chưa chứng minh tối ưu toàn cục hoặc lợi ích trên gờ |
| Prestop Tail− | 12 lượt/1.680 ticks đã ghi, mô tả ISE thấp hơn Tail0 | Verdict vẫn `unknown_preintervention_approach_caliper_exceeded`; chưa promote Tail− hoặc ghép với Ki0.15 |
| common103_v2 | History 5×10 Hz, observation 103D, action common 1D; reward gated, gờ và DR có code | Chưa có full-episode/evaluation chứng minh chất lượng v2 |
| Smoke v2 gốc | 64 transition, 48 critic/24 actor update; 34 tick đóng gate không thu request penalty | **0 episode hoàn chỉnh, evaluation tắt**; không chứng minh crossing/stop hoặc DR robustness |
| Governor | Core/reactive và dữ liệu screen lịch sử còn trong phần dùng chung | V2 trainer hiện không bật contact governor trong `make_environment`; không gọi nó là TD3+governor đã kiểm |
| Predictor / history | History đã được triển khai, không chỉ dự kiến | Predictor action-conditioned chưa có evidence đủ; history5 chưa được ablate với history1 trong v2 |
| Real | Có sensor/sign/command commissioning và raw bag lịch sử | Chưa có body reference độc lập đủ cho slip/body-response claim; chưa deploy TD3 |
| Storage | Rough và run cũ đã dọn; checkpoint/Sim tháng11 và bag thật giữ lại | Summary không khôi phục raw đã xóa; không mở lại archive cũ để giả có đủ dữ liệu |

**[S] Nút thắt hiện tại:** tính đúng của đo/evaluation và benchmark có giá trị
cho ứng dụng, sau đó mới là learning efficiency. Chưa có căn cứ đổ lỗi cho
TD3 chỉ vì một smoke ngắn, hoặc gọi 3,5 mm/s là noise floor của Gazebo.

Đối chiếu offline sáu evaluation ở 30k: stop6 có classical **3,900 mm/s** so
TD3 **4,236 mm/s** (+8,62%); stop8 là **4,140** so **4,351 mm/s** (+5,08%).
Đây là native metric trên dữ liệu đã ghi, không phải một batch mới hoặc
ước lượng tổng quát về mọi obstacle/speed/controller.

## 3. Những lỗi đã sửa trong lượt review

| Vấn đề tìm thấy | Sửa cụ thể | Giới hạn còn lại |
|---|---|---|
| `action_jerk_rms` thực chất là gia tốc | Metric v2 tính đạo hàm bậc hai velocity reference, m/s³; tách acceleration m/s² | Đây là reference jerk, không phải body jerk hoặc tải hư hại |
| Saturation so target với 12 | Dùng target rad/s × nominal radius so với wheel speed cap của config | Không gọi đây là đo torque/current saturation |
| Thiếu target có thể thành zero; task fail bị chia theo số tick | Missing/clock gap/stop chưa quan sát đủ là lỗi/unknown; task fail giữ episode incidence=1 | Metric native vẫn có độ phân giải 100 ms; không thay native/grid contract cũ |
| Campaign chỉ kiểm disk một seed | Tính cả ba seed, raw peak, trace/checkpoint/eval giữ lại, reserve; runtime giữ reserve 1 GiB | Là estimate, không upper bound; cleanup sau seed không giảm peak trong seed |
| Campaign gọi `_plan` rồi unlink trực tiếp | Dùng public retention API có khóa, receipt trước unlink/stat checks; lỗi thì đóng seed còn lại | Không tự xóa episode/checkpoint của job failed/cancelled |
| Checkbox đa seed ảnh hưởng cả Smoke | Smoke luôn một seed/64 bước; campaign chỉ nhận train+evaluation và seeds hợp lệ | Smoke64 vẫn không đủ full episode |
| Worker/event v2 chưa được observer nhận | Bổ sung discovery/log tail v2, phân biệt counter giữa các seed và giữ khóa GUI giữa seed | Chưa kiểm dưới tải Gazebo mới trong lượt này |
| DR map không có entry theo scenario hiện tại | Ghi world path/hash từng episode; dashboard vẽ đúng world hiện tại và refresh khi đổi | Biên friction trong SDF chưa phải calibration hoặc xác nhận engine đã thể hiện đúng uncertainty thật |
| Evaluation danh nghĩa được gọi held-out/robust | Đổi nhãn development, ghi rõ chưa thử DR; checkpoint chỉ được đề cử | Chưa xây test bank độc lập hoặc evaluator cho mọi periodic checkpoint |
| Báo cáo vượt quá dữ liệu | Bỏ kết luận noise floor/giải quyết triệt để/classical bất lực trước gờ; sửa đơn vị ISE | Giữ raw manifest, original failed state và posthoc unknown nguyên vẹn |
| Outline GUI lỗi thời | Trang tiến độ/việc cần làm dùng review mới, tách đã kiểm offline và chưa chạy runtime | Đây là snapshot review có ngày, không trạng thái phần cứng live |

Không đổi nhánh v1, gain, reward hoặc profile của checkpoint 20k/25k/30k.
V2 sau correction có fingerprint khác: checkpoint smoke64 gốc đọc/hash được
nhưng bị từ chối resume vào code mới. Không sửa identity để vượt kiểm tra.

## 4. Objective còn thiếu so với đề tài

**[N]** Reward v2 hiện gồm velocity tracking, yaw tracking và request costs.
Nó chưa trực tiếp tối ưu rung/slip/contact risk. Giảm vRMSE qua gờ có thể đi
kèm rung/impact tăng; vì vậy không được gọi thắng tracking là giảm rủi ro.

**[Đ]** Trước learning mới cần chọn rõ một bài toán:

- Nếu là **velocity tracking dưới nhiễu có biên**, giữ objective hiện tại,
  báo task/stop/path và proxy rung/slip riêng, không phát biểu bảo vệ hàng hóa.
- Nếu là **motion quality qua gờ**, chốt primary/constraint về rung, tiến độ,
  tracking và crossing với trade-off tạm thời có phiên bản. Chỉ đổi reward
  sau kiểm phép đo, rồi ablate đúng một yếu tố; không đổi đồng thời LR,
  history, scale và reward.

Wheel PI, reference projection và contact governor có vai trò khác nhau.
Common1D v2 không phải traction control từng bánh, torque policy hay safety
certificate. Map hiện tại vẫn là controlled factory fixture, không toàn
factory mixed map, dây mềm, pothole hoặc groove.

## 5. Outline có điểm dừng — tối đa ba thí nghiệm tiếp

### E1 — integration code sau correction, chưa phải performance training

Draft đã chuẩn bị tại
`src/nino_rl/config/common103_v2_integration_review_draft_v1.json`, có pin
source, request, dự toán và hướng dẫn thao tác GUI; **release=false, 0 slot**.
Đây là wrapper proposal không thể đưa nhầm trực tiếp vào worker như request.

**[Đ]** Chuẩn bị một protocol riêng cho **một job 280 transition**, smoke
profile/seed11, hai episode stop6/8, tối đa **3 training launches** do SB3 có
thể auto-reset ở terminal cuối; nếu bật evaluation thì thêm đúng **6 lượt
development ×140 ticks**, không gọi chúng là test độc lập. Cần kiểm ngân
sách tổng trước chạy, không thêm smoke ngoài protocol. Có optimizer thật
theo smoke profile; số update thực phải ghi, không gọi đây là 0 training.

- Dữ liệu: toàn chuỗi requested→window/projection→executed reference→wheel/
  body; raw joint/IMU/GT; source stamps/epoch; world/DR hash; stop/lifecycle;
  replay/counters; disk; GUI progress.
- Qua: đủ hai episode, stop/task và measurement hợp lệ, counter/replay khớp,
  map/seed không nhầm, cleanup có receipt và không xóa eval/checkpoint.
- Dừng/unknown: thiếu support, lifecycle/stop fail hoặc identity sai. Giữ
  artifact; tối đa một correction có căn cứ rồi quyết định, không retry batch
  tự động. E1 qua chỉ xác nhận integration, không mở tự động 3×50k.

### E2 — một screen cổ điển về authority trên gờ cố định

**[Đ]** Sau E1: khóa gờ Ø6 mm, sàn/load/approach/actuator và PI có phiên bản
riêng. Ki0.15 là candidate từ sàn sạch, chưa gọi đã tune cho gờ. Không sửa
baseline v1. Đề xuất **3 reference profiles ×2 lịch dừng ×2 fresh-launch
blocks =12 attempts tối đa**: common0, −0,005 và +0,005 m/s trong một phase
được khai báo trước, các yếu tố khác giữ nguyên. Thứ tự block cần cân bằng.

- Nếu dùng first loaded contact đặc quyền để định phase, ghi đây là **oracle
  feasibility**; contact chỉ là nhãn/oracle, không vào deployable actor.
- Trả lời reference có khác không → driver có nhận không → wheel/body có
  đổi kịp phần contact còn lại không → quality/crossing có tốt hơn không.
- Primary, phase/window, minimum useful effect và ràng buộc progress/path/
  stop phải khóa trước release. Vibration/slip là chỉ tiêu riêng có coverage;
  không đổi sampling grid để tạo winner. Paired seeds không là state restore.
- Không có authority hữu ích hoặc effect đổi dấu theo block/grid: đóng
  envelope này cho speed adaptation, giữ classical; cân nhắc preview/memory
  hoặc cơ khí theo cơ chế. Unknown không tự tăng mẫu hay hạ gate.

### E3 — pilot học sau khi benchmark/đối chứng đã chốt

**[Đ]** Nếu E2 cho thấy còn lợi ích có thể học: chuẩn bị **một seed, 12k bước
research**, map gờ cố định trước; warmup10k nghĩa còn tối đa khoảng2k bước
update khả dụng. Không gọi learning thất bại nếu chưa có optimizer updates.
Đây là pilot signs-of-life, không là xác nhận đa seed. Giữ mọi failure/censor.

- Khóa train/validation/test theo toàn layout/run/seed; chọn checkpoint bằng
  validation, test riêng chưa dùng để chọn. Hiện evaluator mới có nominal
  development; cần xây bank/evaluator trước khi phát biểu generalization.
- Đối chứng: B0 và classical đủ mạnh cùng backend/estimator/reference limits;
  mọi gain/action/reward khác biệt phải ghi rõ, không gọi “công bằng tuyệt đối”.
- Qua pilot: metric/task/coverage hợp lệ, có optimizer thực, policy tạo action
  khác có ý nghĩa; chỉ là cơ sở xem xét ngân sách tiếp. Plateau, Q-loss/return
  đẹp hoặc seed tốt nhất không thay gate lợi ích vật lý.
- 50k×3 và DR là giai đoạn sau, có protocol/disk/test bank riêng. Không tự
  cấp thêm ngân sách hoặc chạy campaign từ kết quả review này.

## 6. Giữ / chưa mở

| Nhánh | Quyết định hiện tại |
|---|---|
| Classical, Ki0.15 candidate | Giữ làm đối chứng; chốt baseline có phiên bản theo envelope |
| TD3 v1 | Giữ checkpoint và kết quả đã đóng; chưa train tiếp cùng bài toán chỉ để tìm winner |
| TD3 v2 | Tiếp integration và benchmark có cap; chưa chạy dài |
| PPO/BC/Optuna rộng | Chưa mở thêm trước khi có câu hỏi ablation cụ thể |
| History5 | Giữ contract hiện tại; chưa tăng history hoặc tuyên bố có lợi vượt history1 |
| Reactive governor/predictor | Giữ source dùng chung; chưa promote, chưa ghép vào v2 rồi cộng thành tiến bộ TD3 |
| DR, factory mixed, sim-to-real | Code/resource có sẵn; generalization và hardware transfer chưa được chứng minh |
| GUI/Laya | Dùng vận hành và đọc bằng chứng; không chọn controller hoặc tự đổi gain |

## 7. Kiểm chứng và giới hạn lượt review

- **544 file** trong ba artifact PI/prestop/smoke khớp manifest gốc.
- **54 file niêm phong** được bảo vệ không đổi; v1 20k/25k/30k qua kiểm
  bundle/hash/runtime và preflight resume.
- **114 test phần mềm được chọn đạt**, gồm metric/fault, campaign, storage,
  live/DR map, outline và luồng hardware chỉ đọc; không phải toàn bộ test suite.
- Build thành công `nino_rl` và `nino_pi`; outline đã render kiểm đọc được.
- Tính lại metric trên **6 evaluation v1 cũ ×140 rows**, velocity RMSE khớp
  summary gốc; metric mới không được ghi đè kết quả cũ hoặc dùng làm claim v2.
- XML test/build log và bản trước sửa nằm ở
  [artifact review](/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/project_reassessment_2026-11-08/).
- Không chạy Gazebo, training mới, SSH hoặc hardware trong lượt này. Test
  fixture/offline không là episode robot/Gazebo hoặc xác nhận hiệu quả.

Nguồn chính là code và artifact local đã nêu; attachment là transcript công
việc, không tự là bằng chứng mọi acceptance gate đã đạt. Đã đối chiếu
[SB3 về evaluation tách riêng](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html)
và [ReplayBuffer](https://github.com/DLR-RM/stable-baselines3/blob/master/stable_baselines3/common/buffers.py)
ngày 08/11; không nâng thư viện, không suy default algorithm là tối ưu Nino.

**Một việc nên làm ngay:** chốt protocol E1 full-episode cho code sau
correction. Artifact cần nhận là integration report có counter/raw/stop và
GUI đúng; nếu E1 còn lỗi sau một correction, giữ v2 ở mức experimental và
quay lại sửa integration, chưa chuyển sang campaign dài.
