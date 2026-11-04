# Protocol trước chạy — V3 causal estimator + guided baseline

04/11/2026. Người dùng yêu cầu tiếp tục nhánh sim. Không SSH/hardware,
không optimizer/actor/checkpoint, không sửa PI/current hoặc kết quả v1/v2.

## Câu hỏi và điều kiện

Estimator wheel+IMU causal và follower có giữ được tuyến/reference/stop trên
clear floor khi có initial **heading error so với tuyến** không?

- Robot spawn yaw 0 như launch cũ. Tuyến dài 3 m xoay bearing +5° hoặc −5°,
  nên initial robot-heading minus path-heading là −5°/+5°. Không teleport
  robot, không đọc GT để khởi tạo estimator hoặc làm reference điều khiển.
- Initial estimated pose `[0,0,0]` là **metadata scenario tại task epoch**,
  không là số đo GT sau settling. Drift/offset ban đầu phải giữ trong error.
- Hai arm: constant straight B0 và estimated-pose guided B0. Cả hai dùng
  cùng estimator/acquisition để đánh giá; chỉ guided dùng yaw follower.
- 2 arm × 2 path bearings × 2 fresh launches = **8 lượt**, tối đa 1.120
  transition. Thứ tự cố định trong YAML cân đối, không exact-state pairing.
  Không training seed hoặc confidence interval mới; residual luôn `[0,0]`.
- Giữ Nino URDF/caster + wheel PI, clear solid-box factory hall. Physics
  1 ms, policy/native 100 ms, cruise 0,2 m/s; source zero 0–0,5 s và từ
  8 s; task 14 s gồm 6 s giảm tốc/stop. Ramp/limits giữ như v2.
- Path dài 3 m để tránh goal-approach slowdown trong cửa sổ đi khoảng 1,5 m.
  Không gọi đạt marker 0,95 m là đã tới goal 3 m hoặc full factory navigation.

## Estimator và clock

- Tích phân ở từng gyro-Z source stamp; forward speed từ trung bình hai
  drive wheel velocities × radius danh nghĩa. Heading từ gyro, không từ GT.
- Mỗi gyro chỉ dùng wheel sample mới nhất có **stamp ≤ gyro stamp**;
  dữ liệu tương lai không được nội suy/ngược lại sửa pose đã dùng.
- Gyro dt và wheel-support age tối đa 40 ms; source reversal, buffer đầy,
  thiếu support → fail closed. Output pose dừng ở source stamp cuối, không
  extrapolate tới policy tick. Duplicate không renew lease hoặc tích phân lại.
- Header time trong sim được chuẩn hóa nanoseconds như backend cũ. Raw
  callback receipt monotonic giữ riêng. Pose receipt ở boundary là thời điểm
  estimate có sẵn trên common sim clock, không là hardware transport latency.
- Geometry và gyro bias=0 là giả định sim. Wheel odometry không là body GT;
  chưa kết luận real localization hoặc chịu slip tốt.

## Metric và gate đề xuất trước dữ liệu

Primary: GT cross-track RMSE tương đối tuyến đã xoay, toàn task cố định.
Secondary: max/final cross-track, path heading error, body v/yaw tracking so
reference shaped, source/accepted/final/target, estimator position/yaw error,
quiet 2 s và marker progress theo path. GT chỉ vào evaluator/reset settling.

Gate engineering **đề xuất trong sim**, chưa là factory/hardware acceptance:

1. Guided cả bốn lượt tới marker path ≥0,95 m, stop quiet liên tục 2 s,
   không guidance/physics/source fault, đủ 140 tick.
2. Max guided cross-track ≤0,04 m; max estimator position error ≤0,05 m và
   yaw error ≤0,05 rad. Pose bound cho phép offset settling chưa biết (~cm
   ở các batch cũ), không căn chỉnh GT sau kết quả để đạt gate.
3. Ở mỗi path bearing, max RMSE guided < min RMSE constant trong hai lượt
   mỗi arm: ghi separation **mô tả**, không là statistical benefit test.

Stop quiet giữ các bound v2: accepted wheel reference ≤1e−6 m/s; body speed
norm <0,01 m/s; |body yaw rate|<0,05 rad/s; wheel |speed|<0,15 rad/s.
Deadline task là true terminal; không bootstrap deadline miss như timeout.

Nếu fail, giữ unknown/failure; không thêm mẫu, hạ gate, sửa target hoặc
loại spike. Tối đa một correction có nguyên nhân integration cụ thể và root/
protocol revision mới; không retry world multi_step hoặc mở lại batch đã đóng.
Wall deadline 1.800 s. Raw IMU/wheel/drive/GT/caster và estimator-support/
guidance audit cùng trace/provenance phải giữ để phân biệt model và logging.

## Artifact và bước sau

Root mới `~/nino_research/sim_guided_baseline_v3`; action `sim-v3-baselines`.
Module/estimator/config/script có fingerprint riêng, guidance contract và
actor ABI được lưu. V1/v2/clear-bias artifacts giữ nguyên.

Qua gate chỉ mở việc thiết kế/release v3 learning riêng, chưa tự train hoặc
deploy robot. Baseline identity/estimator/task thay đổi nên không resume
checkpoint v2 chỉ vì observation vẫn 100D. Nếu chưa qua, sửa baseline hoặc
clock/estimator trước, không tăng PPO/TD3/history để che lỗi.
