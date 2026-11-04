# TD3 residual trên factory Gazebo — 04/11/2026

## 1. Map và đường điều khiển thực sự dùng

**[N — code và mô phỏng]** Job `factory-td3` dùng
`src/nino_description/worlds/factory_floor_mixed.sdf`: mesh factory có cáp,
hõm và rãnh. World đã chuẩn bị chỉ thêm contact instrumentation; giữ nguyên
collision/mesh, không thêm mặt hộp bên dưới để lấp hõm.

Robot là **Nino URDF có hai bánh chủ động, hai caster swivel và bracket**.
Mỗi episode lưu expanded `robot.urdf` nhận từ robot_state_publisher và
readback tham số của controller. Không dùng robot DiffDrive đơn giản của
fixture sàn phẳng trước đây.

```text
Baseline tiến thẳng E1 (v = 0,2 m/s sau warmup; omega = 0)
  + IMU / encoder / final-reference / history
      → Observation History 20 × 5 = 100
      → TD3: normalized common / differential proposal
      → giới hạn residual từng bánh + tốc độ / acceleration
      → /cmd_vel
      → effort_drive: wheel velocity PI conditional_v1
      → ros2_control effort → bánh và thân Nino trong Gazebo

GT / contact → reward, outcome, audit; không vào actor
```

Factory smoke hiện **không bật reactive Governor** trong environment; đó là
nhánh so sánh/ablation riêng. Shared ResidualPipeline vẫn giữ History và
projection. Có bộ so sánh TD3/PPO/Governor trên fixture giảm bậc trước đó;
chưa có đối chứng công bằng tương ứng trên factory trong đợt này.

Đây là backend PI mô phỏng xuất torque. Chưa hiệu chuẩn nó thành CyberGear
Speed Mode của robot thật; không chồng thêm vòng PI lên motor thật.

## 2. Protocol smoke

| Mục | Cấu hình |
|---|---|
| Map/route | Factory mixed cố định, reference thẳng E1; goal gốc x=6,45 m |
| Physics/control | 1 ms / 100 ms; hai chunk physics 50 ms, có completion barrier |
| Observation | IMU/encoder/command history; IMU mô phỏng body-aligned |
| Geometry sim | Radius 0,0625 m; separation 0,34273666 m |
| Reference | Cruise 0,2 m/s; acceleration reference bánh 0,1 m/s²; residual ≤0,04 m/s mỗi bánh |
| PI readback | Kp=0,30; Ki=0,10; 500 Hz; torque cap 4 Nm; effort slew 10 Nm/s; wheel-target accel 12 rad/s² |
| Mode | `accept_torque=false`; TD3 không phát torque residual |
| Preflight | 48 transition, kiểm frame/space/reference/feedback/body response |
| Learning | Fresh TD3, seed learner 7, 128 transition, CPU, MLP 32×32; không resume checkpoint fixture |
| Episode/setup | Tối đa hai episode mỗi backend; reset là launch mới, chưa có snapshot/restore exact-state |
| Settling bản đã sửa | Zero, cần yên liên tục 0,5 s trong tối đa 5 simulation seconds |
| Deadline | 900 s wall/job; không tự tăng budget hoặc gửi lại multi-step |

Các giới hạn trên là **contract mô phỏng**. Profile robot thật vẫn giữ
0,05 m/s, ramp 0,10 m/s², source 2 s, thu 60 s. Đợt này không SSH/Pi,
flash, enable motor hoặc thu thêm real dataset.

Gazebo noise seed chưa được chốt; seed 7 là seed learner. Hai run có cùng
seed learner không là hai training seed độc lập hoặc cùng trạng thái caster/load.
Khởi động mesh tốn phần lớn thời gian của job. Reset bằng launch mới phù
hợp smoke; cần adapter reset được kiểm riêng trước khi train dài.

## 3. Các lượt được giữ riêng

| Lượt | Artifact | Kết quả |
|---|---|---|
| A: adapter đầu | `~/nino_research/factory_td3_smoke_v1/20261104T020634384256Z_factory-td3` | Preflight 48, learn 128, optimizer 112 updates; replay 128/128 đạt. GT x cuối ≈1,158 m; chưa hoàn tất route |
| B: thêm gate reset/readback | `~/nino_research/residual_build_v1/20261104T021640485244Z_factory-td3` | Preflight 48 đạt; lỗi RPC sau 50 learning transition hợp lệ. Giữ raw/trace; không promote hoặc resume |
| C: sửa transport | `~/nino_research/residual_build_v1/20261104T022937969043Z_factory-td3` | Preflight 48, learn 128, optimizer 112 updates; replay 128/128 đạt. GT x tối đa ≈0,399 m; chưa đi qua C1. 392/392 physics requests hoàn tất đúng, 0 retry. |

Không gộp các lượt thành bằng chứng benefit hoặc mở rộng thống kê. A có
fingerprint backend trước correction, giữ làm lịch sử. B không được vá dữ
liệu rồi gọi là phiên hoàn tất. B xảy ra trước khi có logic lưu partial model;
không giả vờ đã lưu checkpoint cuối của lượt B.

### Lỗi tìm được và correction

Lượt B ghi bước hợp lệ cuối tại **7,347 s**, raw contact tiếp tục tới
**7,397 s**. Server báo `NodeShared::RecvSrvRequest() error sending response:
Host unreachable`; requester báo timeout. Có bằng chứng physics đã chạy
chunk 50 ms nhưng ACK không tới. Không gửi lại chunk đó hoặc cộng nó thành
một transition RL hoàn tất của lượt B.

Đã sửa:

1. Dùng **ROS world-control client/bridge tồn tại suốt phiên** thay vì tạo
   process `gz service` mới cho mỗi chunk.
2. Chỉ hoàn tất bước khi clock **và số iteration** tăng đúng yêu cầu. Nếu
   ACK thiếu, vẫn cần chứng cứ completion độc lập; thiếu/thừa physics đều
   fail. Journal lưu ACK, clock/iteration trước–sau và `request_retries=0`.
3. Giữ budget episode/reset, zero-settling gate, tham số PI và installed
   mesh/launch verification. Không sửa gain, reward, vật cản hoặc hạ gate.
4. Nếu learner lỗi ở bản mới, lưu partial checkpoint/replay với nhãn failed,
   `resume_allowed=false`. Không dùng artifact đó để tiếp tục hoặc deploy.

## 4. Kết quả cần đọc đúng mức

**[N — bản cuối C]** Actor parameter L1 change ≈29,5632; portable actor so
SB3 đã nạp lại có sai số tối đa **1,1921×10⁻⁷** trên 128 observation của
trace. Replay observation/action/next-observation/reward/done đều khớp.
Settling trước validation đạt sau 1,5 sim s; trước training sau 0,5 sim s.
126 request của validation/setup và 266 của training/setup đều đủ clock và
iteration, có ACK; không gửi lại bước. Wall time job ≈322,1 s.

**Outcome vật lý C chưa đạt vượt C1:** thân chỉ tới khoảng x=0,399 m trong
12,8 s đã cấp. Lượt A từng tới x≈1,158 m, nhưng A/C khác reset/caster/load và
bản adapter; không dùng kết quả A để che C hoặc quy chênh lệch cho TD3 hay
correction transport. Kết quả này ủng hộ dừng train dài để kiểm baseline và
contact fidelity trước. Không có bằng chứng learned benefit.


**[N — mô phỏng lượt A]** Raw ghi manifold của C1 ở bracket caster phải,
bracket trái, caster wheels rồi drive wheels. Đây là **manifold**, không là
first loaded contact được xác định từ lực. C1 trong factory gốc có đường
kính 22 mm; không trộn cơ chế này với capsule 6 mm của các screen lịch sử.

Trace có các đoạn body/wheel chậm hoặc vọt ngay cả trước contact C1 được
ghi. Giữ toàn bộ spike. **[S]** Cần tách động lực học PI/caster/mesh và
scheduling trước khi quy khác biệt cho learned residual. Lượt smoke này
chưa làm phép phân biệt đó.

**[Giới hạn]** 128 bước = 12,8 s tương tác sau reset. Dùng map factory đầy
đủ không đồng nghĩa đã thử mọi cáp, hõm, rãnh, hướng đi hoặc payload. Chưa có
baseline tuned/time-matched, unseen test, nhiều training seed hoặc claim
giảm slip/rung/impact. Return và x tiến được không tự chứng minh giảm risk.

## 5. GUI và artifact

Mở **Nino → Xây project / sơ đồ → Công cụ kiểm phần mềm**. Nút mới:

**FACTORY · TD3 + Nino + wheel PI · 128 bước**

Nút fixture giảm bậc được đổi tên rõ để tránh chạy nhầm map. Factory job
tự preflight trước learn, hiển thị tiến trình và giữ lỗi/hủy. Chọn dòng
FACTORY trong bảng kết quả để đọc `factory_result.json`. Map/robot/backend
đổi fingerprint thì artifact cũ được giữ như lịch sử, không hiện đạt cho bản mới.

Mỗi artifact giữ config/ABI, world đã chuẩn bị, expanded URDF, driver
parameters, settling/raw/journal, training JSONL, model/replay/portable actor,
audit và manifests/hashes. Raw/header clocks tách receipt monotonic. Counts
không được gọi là full coverage; GT/force và encoder/command không tráo nhãn.

Thư mục QA:

```text
/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/factory_td3_smoke_2026-11-04/
```

## 6. Quyết định tiếp theo

**Go cho kiểm tích hợp:** bản cuối replay/clock/driver gate đạt. GUI gắn nhãn
**SMOKE ĐẠT · TASK CHƯA XÁC NHẬN**, không promote chất lượng vượt vật cản.
**Chưa mở train nghiên cứu dài hoặc triển khai residual lên Pi.**

Việc tiếp theo có giá trị là baseline B0 trên factory và đối chứng sàn sạch
riêng với cùng PI, để giải thích dao động trước C1. Không đặt box dưới mixed
map để che hõm. Sau khi fidelity và operating envelope đủ rõ mới chốt
baseline comparison, objective, split, seed và ngân sách nghiên cứu riêng.

## 7. Kiểm chứng bàn giao

49 tests phần mềm đạt: 26 GUI/process/artifact và 23 History/reference/
backend, gồm mất ACK có/không clock proof, không retry physics, episode
budget, settling và bảo toàn collision factory. Build dependency packages
control/description/pi/rl đã đạt; bản pi/rl cuối được đóng gói lại sau
correction. Chi tiết hashes, version, lượt lỗi và kết quả hiện hành nằm ở
`NINO_FACTORY_TD3_SMOKE_VERIFICATION_2026-11-04.json`.

Biểu đồ/analysis đặt ở QA `final_analysis/`; source/assets snapshot của bản C
được lưu riêng trong artifact C. Log/source của A/B có fingerprint lịch sử;
không giả vờ source hiện hành chính là mã đã chạy A/B.
