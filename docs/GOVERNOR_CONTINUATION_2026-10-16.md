# Governor Nino — vòng tiếp tục theo Deep Research, 16/10/2026

**Follow-up đã hoàn tất:** [PI timing và randomized-order contact repeatability](CONTACT_REPEATABILITY_TIMING_2026-10-16.md).
Thêm 13 arrival/stop checks; không chọn sửa PI/reset. Batch mới giảm post-contact
RMS 5/5 cặp, nhưng mean slip/time tăng. Đây là dữ liệu bổ sung, không ghi đè
kết quả 18 episode của vòng bên dưới; predictor/PPO/Optuna vẫn chưa chạy.

## Kết luận hiện tại

**Có tiến bộ ở mô hình contact và detector, nhưng governor cảm biến chưa
chứng minh chất lượng tốt hơn Full PI.** Giữ predictor/PPO/Optuna chưa chạy;
không promote candidate hoặc tự đổi reward. Vòng này dừng tại điểm quyết
định đã đặt, sau một đối chứng vật lý và một ablation trigger có căn cứ.

Đã chạy **18 episode arrival** và **3 maneuver sàn sạch**. Toàn bộ 18 episode
đến đích vật lý/dừng ổn định 2 s; ba maneuver không có physical termination.
Không cộng maneuver vào tỷ lệ arrival. Các simulator thuộc vòng này đã đóng.

## Công việc đã hoàn thành

| Bước | Kết quả | Quyết định |
|---|---|---|
| Cylinder box-floor, 3 profile × 3 cold starts, oracle sau first contact | 9/9 arrival/stop; quality biến thiên, Pulse có outlier peak 267 m/s² | Không chọn theo mean; audit contact |
| Cylinder→capsule, Full PI × 3 seeds | Contact points cách robot ~2 m không còn được ghi; peak ổn định hơn; 3/3 arrival/stop | Giữ candidate riêng cho mechanism check |
| Capsule, Moderate oracle × 3 seeds | RMS/peak/slip²/m đều thấp hơn Full trong ba cặp; 3/3 arrival/stop | H2 local có tín hiệu tích cực |
| Một ablation trigger: vertical không tự mở event | 3 maneuver sạch không event; giữ ramp/threshold/release | Được thử closed-loop trên cáp |
| Capsule, Moderate sensor-only × 3 seeds | Không trigger trước cáp; 3/3 arrival/stop, nhưng chất lượng kém Full | Candidate chưa đạt quality gate; dừng sửa tiếp |

## So sánh trên capsule — ba development seeds 76210–76212

Các controller giữ physical scoring, robot, PI và terrain; sensor candidate
đổi contract trigger và source core, có provenance riêng. Không gọi chúng là
cùng snapshot. Post-contact window: first+0.05 s → body x=3.40 m.

| Controller | Arrival/stop | Time (s) | Post RMS (m/s²) | Post peak (m/s²) | Slip²/m (s/m) |
|---|---|---:|---:|---:|---:|
| Full PI | 3/3 | 16.667 | 2.146 | 11.572 | 0.12102 |
| Moderate oracle | 3/3 | 16.933 | 1.609 | 6.947 | 0.07598 |
| Moderate sensor-only | 3/3 | 17.233 | 2.490 | 19.239 | 0.13897 |

Oracle có thông tin contact đặc quyền, chỉ là thí nghiệm authority trong sim.
Sensor-only không nhận contact/pose/preview/GT. **Không lấy hàng oracle để
tuyên bố governor deployable đã cải thiện.** Slip²/m là tích phân tỷ lệ
trượt bình phương theo thời gian/chia quãng đường, không phải năng lượng J.

## Vì sao không train/tune tiếp ngay?

- Deep Research đặt H2 trước H1/H3. Tín hiệu oracle tích cực mới chỉ ở một
  vật cản dạng cáp, một tốc độ, ba cold starts; chưa hoàn tất ma trận
  feasibility, chưa kiểm tra unseen geometry/dynamics hay hardware.
- Candidate đã hết precontact trigger trong screen nhưng fail quality. Chỉ
  tăng penalty hoặc chỉnh thêm hold sẽ không xử lý được nguyên nhân chưa biết.
- Seed 76210 có timing HOLD/recovery oracle và sensor gần trùng nhau (~2 ms
  khác biệt), trong khi caster-wheel state và contact sequence khác đáng kể.
  Same seed/approach speed không bảo đảm cùng trạng thái tiếp xúc.
  Peak 50 ms đầu seed 76210 đã là 63.15 so với Full 8.72 m/s², trước khi
  sensor governor bắt đầu tác động ở ~101 ms. Không quy phần chênh lệch đó
  cho controller; đây là dấu hiệu phép ghép initial/contact state còn yếu.
- Chưa kiểm chứng H1: history có chọn action tốt hơn reactive/speed features
  hay không. Không train predictor từ các frame chồng lấn của ít run này.
- Fixed-speed 0.394 m/s reference chỉ được chuẩn bị có điều kiện; **chưa chạy**
  vì sensor candidate không qua quality gate. Chưa tuyên bố time-matched/H3.

## Bước cần làm trong vòng kế tiếp

Ưu tiên **repeatability của contact và ranking profile theo caster support/
rolling state**, với điều kiện đầu có kiểm soát và đo lường trạng thái đó.
Chỉ dùng caster/GT làm nhãn/audit trong sim. Không ép bánh caster không chịu
tải phải quay như bánh đang lăn để “sửa slip”. Đối chiếu clearance caster,
đáp ứng motor và phép đo IMU thật trước khi chọn khoảng randomization vật lý.

Sau đó mới quyết định giữ reactive governor, mở dataset H1 hoặc dừng nhánh
predictive cho operating envelope này. Không yêu cầu PPO thắng để cho mọi
tuning; hiện chưa có setup/split chất lượng ổn định cho một study có ý nghĩa.

## Thay đổi code/config

- Research-only oracle evaluator dùng native scoring; evaluator thường từ
  chối oracle config nếu không qua entry riêng. ROS governor triển khai không
  nhận oracle. Metadata phân biệt rõ source oracle/sensor.
- World capsule riêng, invariant test chỉ đổi primitive C1; map mixed, carved
  pothole/groove và robot geometry giữ nguyên.
- `vertical_only_trigger_enabled` mặc định **true**, giữ logic lịch sử.
  Hai config `factory_floor_motion_trigger_*_check.yaml` opt-in false.
  Vertical vẫn tham gia quiet/release, chỉ bỏ quyền tự khởi động event.
- Runner/audit giữ unavailable/failures và phân biệt obstacle arrival với
  low-tilt diagnostic của sàn sạch. Không sửa native gate để promote candidate.
- 23 focused software tests pass sau thay đổi cuối; build hoàn tất. Gazebo
  vẫn có lỗi shutdown sau khi thu xong dữ liệu; logger đã đóng, lỗi đó không
  được gán thành crossing failure.

## Báo cáo chi tiết

1. [Oracle H2 trên cylinder](CONTACT_ORACLE_H2_2026-10-16.md).
2. [Đối chứng primitive collision](CABLE_COLLISION_FIDELITY_2026-10-16.md).
3. [Refinement H2 trên capsule](CAPSULE_POST_CONTACT_H2_2026-10-16.md).
4. [Sensor governor, negative controls và quality failure](MOTION_TRIGGER_GOVERNOR_2026-10-16.md).

Checkpoints, studies và kết quả cũ được giữ. Chưa có bằng chứng sim-to-real
hoặc hiệu quả chung cho cáp mềm, pothole, groove hay mọi vật cản nhà máy.
