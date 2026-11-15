# Sim TD3: bộ chấm goal và adapter gờ không biết trước

Ngày 10/11/2026. Tiếp tục nhánh Sim theo mục tiêu người dùng đã chọn:
**vượt gờ không biết trước, bám quỹ đạo, tới đích và dừng**.

## 1. Quyết định

1. Giữ checkpoint common103_v2 50k làm bằng chứng của task cũ; chưa promote.
2. Hoàn thiện các thành phần phần mềm cho task mới và kiểm bằng fixture.
3. Tiếp theo nối chúng với backend Gazebo, khóa geometry/bank/protocol rồi
   kiểm B0 trước pilot TD3 của task mới. Không dùng checkpoint 103D như
   checkpoint tương thích của task 100D.

Lượt công việc này không khởi động Gazebo, optimizer hoặc hardware. Không
đổi gain/current, learning rate, lịch sử 5 frame hoặc source của trainer cũ.

## 2. Cập nhật kết quả train thực sự đã có

Job được đọc:

```text
~/nino_research/td3_recovery_20261109/
  20261110T003411337787Z_common_v2_seed11_train/
```

| Nội dung | Kết quả đã lưu và đối chiếu |
|---|---|
| Nhánh/model | common103_v2, seed 11, resumed từ checkpoint 40k |
| Bước thêm trong segment | 10.000 |
| Checkpoint cuối | 50.000 global steps; replay size 50.000 |
| Critic / actor updates tổng | 39.998 / 19.999 |
| Episode terminal trong segment này | 71; 62 có task_success của task cũ |
| Phần cuối segment | 60 bước chưa hết episode, giữ là right-censored |
| Trạng thái job | **failed ở evaluation**, không phải chưa có optimizer |

Các counter là một nhánh checkpoint đã resume, không phải ba training seed
độc lập, không cộng các đoạn đã bỏ sau checkpoint vào replay này, và không
phải số lượt vượt gờ/tới goal của task mới.

### Integrity và phạm vi evaluation

Audit đọc toàn bộ **1.893 file được manifest gốc liệt kê**: 1.892 khớp;
`evaluation_progress.json` không khớp vì nội dung hiện có khác bản niêm
phong. Không sửa manifest, không dùng index đó để xác nhận kết quả. Hash
model/replay/metadata trong checkpoint 50k và source engine được kiểm riêng.

Manifest gốc chỉ chứa raw/trace của `6_B0` và `6_Classical_scheduled`.
Trace `6_B0` đạt marker và stop. Trace `6_Classical_scheduled` kết thúc ở
progress khoảng **0,6804 m**, chưa tới marker **0,95 m**, dù đã dừng.
Exception của job là task/feasibility gate tại lượt này; nó không chứng minh
actor TD3 hỏng hoặc TD3 thua baseline.

Bốn thư mục `6_TD3`, `8_B0`, `8_Classical_scheduled`, `8_TD3` xuất hiện ngoài
manifest gốc. Các summary của chúng và summary classical stop6 báo timestamp
diagnostic không hợp lệ do source gap. Đây là các summary đã có, không phải
diagnostic được tính lại trong lượt này. Giữ riêng dữ liệu bổ sung, chưa
gộp thành một batch sáu lượt hợp lệ hoặc kết luận winner từ bảng RMSE.

Đây vẫn là **development nominal gờ Ø6 mm/lịch stop6–8**, không phải test
bank DR độc lập hoặc task gờ không biết/tới goal. Tên exception cũ có chữ
"Held-out" không biến các lượt này thành held-out test.

## 3. Phần mềm đã thêm

### `unknown_step_runtime.py`

- `TraversalScore`: dùng physical labels riêng để chấm body tới goal,
  heading, path RMSE/max, deadline, stall, fault/intervention và dừng liên tục.
- Clearance dựa trên **toàn bộ bounding box bảo thủ của robot**, tính cả
  roll/pitch/yaw. Tâm hoặc trục bánh qua gờ chưa có nghĩa phần sau đã qua.
  Box phải bao cả swept caster envelope, có identity từ geometry được khóa.
- Clear-floor control không yêu cầu contact. Contact với gờ dự định vượt
  không tự là failure. Không lấy estimator/encoder arrival làm physical success.
- Source/header clock và decision clock được giữ riêng; source age phải hợp
  lệ. Stop duration dùng source time; path RMS tích phân theo các khoảng
  source đã quan sát. Không thay timestamp nguồn bằng decision timestamp.
- Thiếu/nonfinite/stale/future dữ liệu gây `UnknownTaskData`, không chuyển
  thành zero, success hoặc một transition thất bại giả tạo để đưa vào replay.
- `TraversalReward`: progress tới goal, path/heading, time, accepted correction
  và outcome. Không còn mục tiêu duy nhất là nominal velocity ISE. Trọng số
  phải được truyền tường minh; chưa có bộ trọng số được chấp nhận để chạy.
- `SensorOnlyCommonAdapter`: 20 feature × 5 frame = **100D**, một action common
  ±0,02 m/s như authority obstacle v2; differential vẫn zero. Reuse projection
  cũ và giữ requested/replay action khác accepted correction. Không có ba
  feature lịch stop common103, không thêm position/contact/GT vào actor.
- `EstimatedGoalReference`: follower dùng estimator và đường/goal đã biết;
  dừng theo estimated goal, không dừng mặc định ở 6/8 s. Physical scorer
  vẫn có thể báo thất bại nếu estimate làm xe dừng sai chỗ.

### `unknown_step_environment.py`

`UnknownStepEnv` đã có reset/step/spaces/reward/outcomes, kiểm bằng backend
synthetic. Contract là 100D observation / 1D requested action. Identity pin
cả task settings, reward, controller và environment source; cùng kích thước
tensor không đủ để load checkpoint.

Deadline là một phần task hữu hạn nên timeout là terminal failure. Cutoff
bên ngoài là truncation/right-censored, không phạt như failure đã quan sát.
Boundary thiếu dữ liệu không tạo transition. Projection fault có dữ liệu
hợp lệ được giữ là explicit failure. Info/traces giữ requested → projection
→ accepted reference và physical labels ở đường đánh giá riêng.

## 4. Điều đã kiểm và chưa kiểm

**50 tests đạt**, gồm Gymnasium `check_env` trên backend synthetic, success,
stall/timeout/override, continuous stop, geometry clearance, clock separation,
missing data, reward terms, action semantics, metadata perturbation và ABI.
Số này gồm fixture task selection cũ; không phải 50 rollout Gazebo hoặc
50 episode train. Giá trị geometry/tolerance/reward trong tests là số giả lập
để kiểm logic, không phải số đo robot hoặc ngưỡng đã được người dùng chấp nhận.

**Chưa có:** adapter backend Gazebo phát `PhysicalSample` có provenance đúng;
physical integration/feasibility của task mới; hidden-layout bank đã khóa;
protocol/budget được release; optimizer hoặc evaluation của task mới.

Guard metadata chỉ kiểm boundary đã khai báo. Backend vẫn phải được audit
để chứng minh follower/observation thật sự không dùng oracle. Conservative
box chưa được trích xuất và kiểm từ expanded URDF trong lượt này.

JSON task selection ngày 09/11 giữ nguyên như snapshot quyết định ban đầu.
Trạng thái tiến độ phần mềm hiện tại nằm ở qualification mới; không sửa
snapshot lịch sử thành bằng chứng đã chạy physics.

## 5. Studio

SIM-R4 hiển thị **SOFTWARE ĐÃ KIỂM · CHƯA GAZEBO**, kết quả test và bước kế.
Badge kiểm hash qualification, source và XML test; không được tự nâng thành
training release/hardware authorization. Thêm ghi chú 50k có thật nhưng job
evaluation failed; giữ kết quả lịch sử E1/E2 riêng.

**32 kiểm tra Studio/evidence đạt**, gồm từ chối proof đổi hash hoặc gán
nhầm software fixture thành Gazebo integration. Đây là kiểm phần mềm, không
phải một lượt bấm GUI end-to-end có simulator.

## 6. Ba bước tiếp theo

1. **Backend + bank offline:** lấy conservative envelope từ robot sim đang
   dùng; tạo boundary typed labels từ GT source và command/drive evidence;
   nối estimator-goal follower thay lịch dừng. Khóa vị trí development /
   validation / test, có clear-floor control. Chưa mở rộng height/angle hoặc
   tự cho phép mọi layout factory. Không thêm metadata gờ vào controller.
2. **B0 integration có giới hạn:** chốt numeric contract Sim và một protocol
   smoke có số lượt/stop rule trước launch. Kiểm full arrival/clearance/stop,
   acquisition và command chain. Nếu lỗi, giữ failed/unknown; correction có
   căn cứ, không hạ coverage hoặc tăng số lượt tự động.
3. **Pilot TD3 mới:** sau environment qualification, train từ đầu với ABI
   mới; giữ LR/history/authority ban đầu để chỉ thay task đã định nghĩa.
   Sau train so B0/reactive đã qualify/TD3 trên cùng bank và limits. Không
   yêu cầu model chưa train thắng B0 mới cho train; cũng không dùng return
   hoặc một lần arrival để tuyên bố tốt hơn baseline.

**Việc ngay tiếp theo:** hoàn tất boundary Gazebo và bank cho B0 integration.
Nếu baseline không vượt được họ gờ này, hoặc can thiệp speed không có tác
dụng hữu ích, quay lại feasibility/cơ khí/action contract trước đầu tư thêm
training. Chưa cần thao tác robot thật cho các bước offline này.

Artifact:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_unknown_step_preparation_2026-11-10/`.
