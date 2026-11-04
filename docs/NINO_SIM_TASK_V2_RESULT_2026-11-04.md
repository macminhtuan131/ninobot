# Nhánh sim v2 — kết quả và quyết định 04/11/2026

## Chốt hiện tại

**[N — sim] Đã xây và chạy xong task/reward/stop v2:** baseline 4 lượt,
TD3 h5 512 transition/496 optimizer updates, evaluation 6 lượt trên mô hình
Nino có caster + wheel PI trong Gazebo. Không dùng robot thật hoặc dataset
thật. Các artifact v1 giữ nguyên, không sửa horizon hoặc reward sau kết quả.

**Chưa promote checkpoint và chưa tăng ngân sách train.** Sáu lượt evaluation
đều tới mốc và dừng, nhưng hai lượt TD3 có tracking và lệch ngang kém hơn
từng lượt B0. Phần stopping của task đã đo được; learned benefit chưa có.
Đây không phải bằng chứng TD3 không thể hữu ích khi train/đặt bài toán khác.

## 1. Đã sửa và kiểm điều gì?

- Module/config/script v2 riêng; reward v1 và observation/action ABI giữ
  nguyên. History 20×5=100D, common/differential wheel-linear residual,
  projection ≤0,04 m/s mỗi bánh. Governor hiện chưa bật trong ba arm v2;
  PPO/history ablation chưa chạy ở protocol này.
- Bỏ positive progress, so vận tốc GT với profile B0-shaped **độc lập**.
  Không để reference do policy tăng trở thành target reward của chính nó.
- Giữ task cố định 14 s, source tiến 0,2 m/s từ 0,5–8 s, sau đó zero;
  dành 6 s cho giảm reference/body và quiet liên tục 2 s.
- Phân biệt source zero, accepted reference zero, wheel/body quiet và
  task success. Mốc đã qua + stop đạt là gate feasibility; chưa có gate
  chất lượng ứng dụng được chấp nhận.
- Deadline thuộc finite task: success/miss đều true terminal, không là
  time-limit timeout để bootstrap. Budget cutoff giữa episode không tạo
  terminal giả. Failure/partial đều giữ.
- Ghi được caster joint positions/velocities thực sự do Gazebo xuất,
  chỉ làm audit labels, không vào actor hoặc thay đổi physical reset.

Chi tiết frozen trước chạy: [protocol v2](NINO_SIM_TASK_V2_PROTOCOL_2026-11-04.md).
PI Kp/Ki, torque/current, physics và hình học không được tune ở v2. Mọi
ngưỡng stop/scale ở đây là đề xuất kỹ thuật sim, chưa là giới hạn hardware.

## 2. B0 trước learning — hai fresh launches/điều kiện

| Môi trường | GT x cuối (m), từng lượt | RMSE v chuẩn (m/s) | RMSE ngang (mm) | Mốc + stop |
|---|---|---|---|---|
| Clear box | 1,4665; 1,4675 | 0,00495; 0,00494 | 0,80; 0,84 | 2/2 |
| Box + C1 rigid cylinder Ø6 mm | 1,4004; 1,2055 | 0,04170; 0,06394 | 63,05; 171,65 | 2/2 |

Theo rule đã chốt, chọn 6 mm cho learning. Kết quả lateral xấu được giữ;
không đổi selection rule sau khi thấy chúng. Đây chỉ là functional release,
không chứng minh baseline đã tốt hoặc contact repeatability đã giải quyết.
World mixed gốc Ø22 mm không chạy lại và không sửa; các world controlled
không đại diện full factory route, pothole/groove hoặc dây mềm.

## 3. Train và replay

Artifact: `~/nino_research/sim_task_v2/20261104T084149528335Z_sim-v2-train/`.

- Checkpoint mới, seed 7, smoke MLP 32×32; 512 transition, 496 updates;
  actor parameter L1 change ≈100,718. Không gọi là hội tụ.
- Replay kiểm đủ 512 observation/proposal/next-observation/reward và
  done/timeout. Action trong replay là proposal, accepted/final/readback
  giữ riêng trong trace. Không có torque residual.
- Ba episode hết deadline: hai task success, một task failure do chưa đủ
  quiet ở deadline; episode cuối dừng ở budget 9,2 s, **không gắn failure
  hoặc terminal giả**. Không loại episode failure khỏi replay/report.
- Portable NumPy so SB3 trên đủ 512 observation replay: max error
  **2,0862×10⁻⁷**. Metadata checkpoint có task ID/fingerprint riêng ngoài ABI.

## 4. Evaluation — từng lượt, không CI

Các arm đều ở scenario đã dùng train, không là unseen test bank. Một learner
seed, mỗi arm hai fresh launches; thứ tự đối xứng không tạo exact-state pairs.
Không pool với baseline release hoặc v1 để tăng cỡ mẫu.

| Arm/lượt | RMSE v chuẩn (m/s) | RMSE ngang (mm) | RMSE yaw (rad) | x cuối (m) | Task / stop |
|---|---:|---:|---:|---:|---|
| B0/1 | 0,01952 | 16,55 | 0,02832 | 1,4413 | Đạt / đạt |
| B0/2 | 0,01839 | 2,28 | 0,00672 | 1,4561 | Đạt / đạt |
| Speed control/1 | 0,02169 | 10,32 | 0,01402 | 1,6218 | Đạt / đạt |
| Speed control/2 | 0,02555 | 6,30 | 0,01392 | 1,6321 | Đạt / đạt |
| TD3 h5/1 | 0,03446 | 86,02 | 0,25281 | 1,2304 | Đạt / đạt |
| TD3 h5/2 | 0,02875 | 130,00 | 0,31592 | 1,2243 | Đạt / đạt |

Speed control là common boost cố định +0,02348807 m/s từ mean v1,
không tuned/optimal và **không speed/time matched chính xác với TD3 v2**.
Mean executed v ở 3–8 s: B0 0,2000; speed control 0,2235; TD3 khoảng
0,1728–0,1730 m/s. TD3 v2 không còn lấy progress bằng tăng tốc; nó chậm
hơn nhưng vẫn lệch nhiều. Thay reward không tự bảo đảm policy tốt hơn.

Native trace ghi source-zero đầu tiên sau pha đi ở sample 8,1 s; accepted
reference zero: B0 10,0 s, speed control 10,3 s, TD3 9,9 s. Hoàn thành
quiet 2 s: lần lượt 11,9 / 12,2 / 11,8 s. Đây là thời điểm sample 100 ms
của pipeline sim, không là latency hardware hoặc timing có độ phân giải 1 ms.

## 5. Audit nhỏ từ dữ liệu đã có — đã làm, không chạy thêm sim

**[N — sim]** Hai B0 baseline-release có caster swivel ban đầu gần hướng
thẳng (|angle| dưới khoảng 0,0004 rad), nhưng x ban đầu khác khoảng 20 mm.
RMSE y trước C1 chỉ khoảng 3 µm, sau đó RMSE toàn task là 63/172 mm.
Thứ tự caster first-manifold trái/phải đổi giữa hai lượt. Đây là manifold,
không là loaded contact và chưa nhận dạng nguyên nhân độc lập.

**[N — sim]** Trong evaluation, TD3 đã có RMSE y trước first C1 khoảng
2,19/2,21 mm; B0 khoảng 0,012/0,006 mm. Mean proposal common/diff ở
3–8 s của TD3 khoảng [−0,875; −0,414] và [−0,884; −0,423]. Trace cho
thấy residual differential âm xuất hiện trước tiếp xúc.

**[S]** Steering bias của checkpoint góp phần phù hợp với lệch hướng;
không thể quy toàn bộ lỗi TD3 cho contact hoặc initial caster. Cần kiểm
trên clear floor và reference yaw trước khi tăng training. Kết quả này
không tách dứt điểm contact numerics, caster dynamics và PI thành nguyên nhân.

**[S]** Task phạt y/heading thế giới trong khi actor chỉ có proprioception
h5 và lệnh thẳng. Sau khi nhiễu rời history, yaw rate≈0 không cho biết
heading/lateral tích lũy tuyệt đối. Đây là partial observability có ý nghĩa;
reward GT được phép dùng nhưng không hứa loại bỏ lỗi path bằng history ngắn.
Không tự thêm pose/GT/caster vào actor để làm đẹp kết quả.

## 6. Độ tin cậy dữ liệu và phần mềm

- Ba stage hoàn tất, **177 file** khớp manifest SHA256.
- **3.964/3.964** world-control request hoàn thành đúng clock/iteration;
  zero physics retries. 28/28 read-only parameter calls hoàn tất.
- Cửa sổ task baseline/evaluation: observed max gap joint/caster 3 ms,
  IMU/GT 20 ms, drive 21 ms; action-boundary source lag tối đa 19 ms.
  Startup được tách riêng. Không gọi những con số này là loss-free,
  full contact-load coverage hoặc độ phân giải body 100 Hz.
- 35 test simulation/reference + 8 test GUI đạt. Colcon `nino_pi`,
  `nino_rl` đạt. GUI đã load artifact thật: V2 sáu dòng, V1 ba dòng vẫn
  được kiểm hash. Không có job hoặc kết nối Pi phát sinh khi mở panel.
- [Ledger kiểm chứng](NINO_SIM_TASK_V2_VERIFICATION_2026-11-04.json).

QA/biểu đồ/raw-derived report:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_task_v2_2026-11-04/`.
Root job bất biến: `~/nino_research/sim_task_v2/`.

## 7. Việc tiếp theo — có thứ tự và điểm dừng

1. **Ưu tiên baseline/task:** làm rõ tầng path follower giữ tuyến và tầng
   motor/velocity tracking. Chọn reference yaw/heading deployable ở baseline;
   so với constant straight reference hiện tại. GT follower nếu dùng chỉ là
   oracle sim riêng. Không thêm absolute pose vào actor mà giữ nguyên ABI.
2. **Pilot tiếp theo được đề xuất, chưa chạy:** clear-floor evaluation của
   checkpoint v2 giữ nguyên so B0 để phân biệt steering bias có tồn tại khi
   không contact; kiểm common/diff/accepted yaw và body yaw. Nếu bias có từ
   clear floor, xử lý objective/action/baseline trước contact learning. Nếu
   chỉ xuất hiện sau contact, dùng caster/raw đã có cho cơ chế contact.
3. Chỉ mở multi-seed/h1–h5–h8 khi task/baseline có câu hỏi so sánh rõ và
   budget/protocol mới. Reward/path architecture thay đổi cần **v3 riêng**,
   không sửa v2 rồi tính lại thành success. Hardware/SysID song song phục
   vụ calibration, không là prerequisite của hai bước sim trên.

**Một việc nên làm tiếp:** hoàn thiện contract giữa path follower và velocity
residual, bắt đầu bằng kiểm steering bias trên sàn sạch với checkpoint v2
đóng băng. Chỉ đổi khuyến nghị sang train lớn khi residual không tạo bias
trước contact, baseline/reference công bằng và có tín hiệu chất lượng ổn
định vượt baseline theo protocol. Không tăng steps chỉ vì optimizer chạy được.
