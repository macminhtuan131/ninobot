> Cập nhật: phần software đã hoàn tất và kiểm offline; xem [kết quả](NINO_SIM_PI_SCREEN_OFFLINE_RESULT_2026-11-07.md). Phạm vi physics bên dưới vẫn là đề xuất, chưa có slot/release.

# Draft bước tiếp: kiểm một candidate Ki trong Sim

07/11/2026 · **Chưa release physics, training hoặc hardware.**
Đây là đề xuất cụ thể từ [dynamics audit](NINO_SIM_DYNAMICS_AUDIT_RESULT_2026-11-07.md),
không phải thông số đã được chấp nhận hoặc triển khai.

## Câu hỏi duy nhất

Tăng Ki vừa phải có giảm phần tracking error chậm sau ramp, đồng thời giữ
tracking/path/stop và effort limits, so với PI hiện tại không?

Đề xuất giữ Kp=0,30; so Ki=0,10 với **một candidate Ki=0,15**. Hệ số1,5
là thử nghiệm bounded, chưa suy ra từ mô hình motor đã nhận dạng. Nó đổi
tỷ số Kp/Ki từ3s xuống2s trong công thức PI; không bảo đảm actual response,
ổn định hoặc stopping. Không chọn thêm candidate sau khi thấy outcome.

## Phạm vi đề xuất — chưa cấp slot

- Clear-box, B0 residual zero, gain-map=1; không governor/TD3/hold-estimator
  action. Source stop8s,horizon14s,nominal0,2m/s,ramp/follower giống9/9cũ.
- Hai lần lặp fresh reset mỗi Ki: **4launches×140=560tick tối đa**; integration
  đầu nằm trongbudget. Thứ tựblock: baseline/candidate rồi candidate/baseline.
- Không exact-state branching; hai lặp chỉ pilot mô tả, không reliability/CI.
- Giữ physics1ms,PI500Hz,policy/scoring100ms,IMU/GT rates, geometry,caster,
  torque cap4Nm,slew10Nm/s,target acceleration12rad/s² và conditional integrator.
- 0actors,optimizer,training,probes,hardware;0retry hoặc smoke ngoàibudget.
  Một failure measurement/task/closure đóng mọi slot còn lại, giữraw.

## Việc cần làm trước khi có thể release

1. Backend/context/launch/readback riêng, chấp nhận đúng Ki của condition,
   pin toàn bộ thông số còn lại. Không đổi frozen gain-v1 driver/runner,
   không dùng root9/9 cũ, không patch readback để giả controller đã đổi.
2. Offline kernel/reset/limits tests; baselineKi0,10 parity với frozen kernel
   trên input fixtures; typed identity mới ngay cả khi103D/1D shape giữ nguyên.
   Chưa dùng checkpoint cũ vì plant đã thay.
3. Kiểm observed command/target/PI/effort flags, source support, reset ACK+quiet,
   observer closure, actual installed entries/source pins. GUI chọnprofile
   không tự chạy; release tách khỏi draft và khóaroot đã dùng.
4. Chốt profile/budget/gate trong protocol cóhash riêng trướcphysics.
   Không đổi gate/timegrid hoặc chia lại block sau khi thấy kết quả.

## Metric và quyết định đề xuất

- Primary giữ whole14s native nominal-body velocity RMSE; GT20ms/+10ms riêng.
- Constraints giữ arrival/marker,physical pathRMSE≤40mm và quiet stop2s trước
  horizon14s. Không gọi stop command/watchdog là actual stopping time.
- Secondary: target→wheel tracking,overshoot,PI/effort saturation/slew,
  settling,source timing; rawquery có ambiguity phảiUNKNOWN, không chọn variant.
- Candidate đạt screening mô tả nếu primary giảm≥5% trên cảhai cặp và hai
  GT sensitivity grids cùng chiều, constraints đều đạt. **5% chưa là yêu cầu
  nhà máy hoặc statistical significance.**
- Tệ hơn/gatefail: no-go candidate. Sampling-sensitive, nhỏ hoặc khác chiều
  giữa lặp:unknown; không tự tănglặp hoặc quét thêmKi. Giữ baseline cho tới
  quyết định mới có căn cứ.
- Qua gate vẫn chỉ candidate classical: cần validation riêng trước mở rộng
  gain/contact. Không tự trainTD3 sau khi classical được cải thiện.

**Điểm dừng:** draft chỉ cho phép chuẩn bị software; chưa có launch physics
nào được cấp ở đây. Đây không là correction estimator thứhai hoặc chỉnh
gain/current trên robot thật.
