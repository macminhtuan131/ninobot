# Nhánh sim trước — protocol pilot v1, 04/11/2026

Người dùng yêu cầu triển khai nhánh sim; real dataset không là prerequisite
cho các job dưới đây. Không nối Pi, phát command thật hoặc thay firmware.
Các gain/limit hiện hành của simulated wheel PI được giữ nguyên.

## Câu hỏi và phạm vi

1. B0 có body response trên solid-box floor không? Vướng gờ nhỏ và mixed
   original có cùng cơ chế không?
2. TD3 h5 có thực sự cập nhật optimizer, đúng replay semantics và portable
   actor trên actual Nino/Gazebo velocity backend không?
3. Một checkpoint pilot có trade-off mô tả thế nào so B0 và yaw P đơn giản?

Đây là một seed/pilot ngắn, không phải train hội tụ, held-out terrain benchmark,
tuned-classical comparison hoặc learned-benefit confirmation.

## Các job hữu hạn

| Job | Điều kiện | Budget |
|---|---|---|
| `sim-baselines` | B0 trên clear box; box + C1 rigid cylinder Ø6 mm; factory mixed nguyên bản C1 Ø22 mm | 100 transition/condition |
| `sim-train` | h5; chọn 6 mm nếu B0 tới marker x=0,95 m; nếu chưa tới thì chọn clear box | 256 transition, learner seed 7, tối đa 3 episode |
| `sim-evaluate` | B0, B1 yaw P gain 0,6, TD3 deterministic; cùng scenario được chọn | 100 transition/arm, một fresh launch/arm |

Chu kỳ policy/scoring 100 ms, physics 1 ms; warmup source zero 0,5 s, cruise
0,2 m/s với wheel-linear acceleration bound 0,1 m/s², source về zero tại
elapsed 8 s, horizon 10 s. Đây là cấu hình sim, không phải motion profile thật.
Mỗi job có wall deadline 1500 s, không retry một physics multi-step request.
Marker x=0,95 m chỉ là mốc local trong sim, không phải goal E1 6,45 m hay
bằng chứng loaded contact/risk đã giảm. Không gọi các rollout fresh-launch
là exact-state pairs hoặc nhiều training seeds.

## Điều kiện / metric

- Clear-floor displacement dưới 0,30 m hoặc physical-envelope failure: không
  mở training từ artifact đó. Đây là functional engineering check, không là
  ngưỡng chất lượng được chấp nhận trên robot.
- B0 không đạt marker trên gờ 6 mm: vẫn có thể train clear-floor pilot;
  không coi đây là cấm train do thiếu real data hoặc yêu cầu PPO thắng B0.
- Giữ return, progress, lateral/yaw RMSE, body→executed-reference error,
  target→wheel error, final speed, projection modifications, source gaps và
  contact manifolds. Projection modifications không tự là safety interventions.
- Báo cáo thêm body tracking so **nominal baseline reference**, nhất là đoạn
  steady 3–8 s: TD3 tự nâng reference có thể tăng progress/return nhưng chưa
  chứng minh tracking tốt hơn ở cùng nhiệm vụ. Đây là diagnostic mô tả,
  không retroactively chọn một objective/effect threshold thắng cuộc.
- IMU/contact samples chỉ hỗ trợ mô tả; counts/max gap không thay coverage,
  acceleration proxy không là force/damage, commanded torque không là sensor
  torque của robot thật. Không tự kết luận slip từ encoder odom.
- Không accepted minimum effect, không CI/generalization claim ở quy mô này;
  checkpoint luôn `benefit_verified=false`, `hardware_authorized=false`.

## Traceability và lỗi được giữ

World mixed gốc không đổi, không thêm ground box dưới depressions. Hai world
controlled là file mới trong artifact, chỉ giữ hall của factory và thay nền
bằng solid box, với/không một cylinder C1 6 mm. Chúng không đại diện toàn
factory hoặc dây mềm. Actual Nino URDF/caster + velocity PI được giữ.

Mỗi job lưu protocol/config/world SHA, raw/trace, physics request journal,
parameter readback, manifest, model/replay nếu có. Lỗi không xóa, không resume
partial checkpoint. Hai lỗi engineering phát hiện trong triển khai:

1. Read-only `GetParameters` response timeout, trước transition học đầu tiên.
   Giữ warning/raw; thêm discovery wait và tối đa một retry có journal cho
   **đọc tham số**. Không retry world-control/multi-step.
2. Source clock float lệch dưới 1 ns, gây strict future rejection khoảng
   −8,88e−16 s. Canonicalize theo tick nanosecond Gazebo/ROS; không nội suy,
   không mở tolerance cho future sample thực. Test +1 ns vẫn bị từ chối.

Artifact trước/sau correction có fingerprint khác và không gộp thành cùng
một experiment hoặc sửa hash lịch sử. Các correction này không đổi gains,
reward, geometry hay outcome thresholds để làm controller thắng.

## GUI và bước tiếp

**Xây project → NHÁNH SIM** có ba nút theo dependency, log, progress, hủy job
và xem kết quả. Thư mục pilot: `~/nino_research/sim_branch_pilot_v1`.
Job không cần Pi/Studio/real dataset; GUI khóa chạy đồng thời với collector.

Sau pilot: review thực nghiệm để chọn classical/backend/obstacle envelope
hay mở protocol train dài hơn. Real SysID/calibration chạy song song cho
sim-to-real; nó không là gate bắt đầu mọi simulation training.
