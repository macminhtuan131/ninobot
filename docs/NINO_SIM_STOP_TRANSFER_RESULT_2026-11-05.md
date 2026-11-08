# Kết quả Sim: chuyển planned stop8s →6s

05/11/2026 · **Đóng đủ6/6 fresh launches,840 evaluation ticks; actor/optimizer0.**
Không có train mới hoặc thao tác phần cứng. Protocol và diagnostic được
chốt trước chạy tại [contract](NINO_SIM_STOP_TRANSFER_PROTOCOL_2026-11-05.md).

## 1. Quyết định

**[N — mô phỏng]** Cả ba lượt common cổ điển có whole-task nominal velocity
RMSE thấp hơn cả ba B0, ở native100ms và cả hai GT-header diagnostic grids.
6/6 đạt marker0,95m, quiet stop2s và engineering bounds đã đề xuất.

**[S]** Rule +0,005m/s ở steady, rút0,5s trước source stop, giữ được tín hiệu
tracking mô tả khi đổi lịch dừng sang6s trong clear fixture này. Giữ common
cổ điển làm **candidate đối chứng nghiên cứu**, B0 giữ riêng. Chưa promote
ứng dụng: minimum worthwhile effect chưa chốt, chỉ ba launches/arm ở một
điều kiện phát triển, chưa có test bank độc lập hoặc model hiệu chuẩn thật.

**[Đ]** Dừng chuỗi tune/thu thêm gần giống cho compensation này. Bước tiếp
là [chốt contract so TD3/cổ điển cùng thông tin](NINO_SIM_EQUAL_INFORMATION_NEXT_2026-11-05.md),
offline trước; chưa mở train/physics mới. Không suy TD3 không thể cải thiện:
batch này không có actor hoặc optimizer và không so thuật toán cùng thông tin.

## 2. Đã chạy gì?

- Thứ tự B0/classical/classical/B0/B0/classical, ba fresh launches mỗi arm.
- Clear box, yaw0, warmup0,5s, cruise0,2m/s; source stop6s, horizon14s.
- Cùng estimator wheel+IMU, follower, h5/100D, geometry/projection/ramp/PI.
  Backend, guidance, task config và scorer đều stop6s.
- Classical active đúng30 ticks/lượt, decision2,5..5,4s; proposal0 từ5,5s.
  Nominal adapter khớp scorer từng tick. Không dùng GT/contact chọn action.
- B0 không gọi actor. Không load actor/model, không xuất replay để train.
  Seed reset701 là khai báo, không snapshot/restore cùng trạng thái vật lý.

Root:
`/home/tuanmac/nino_research/sim_stop_transfer_v1/20261105T075810956156Z_sim-stop-transfer`.
Fingerprint:
`43e0f6eb3912dffdd3255cac7e54d3622b0b130476ee531d2574251ef37e006d`.
Parent common pin:
`02a7fc89d1614a44685ca15abc8a88ad4ca4caf925911369312d7f81263dba07`.

## 3. Primary và diagnostic giữ riêng

Primary: RMSE body v so nominal zero-residual shaped reference, toàn14s,
native100ms; không thay bằng tốc độ sau cộng residual hoặc steady-only.

| Arm/lượt | Native RMSE v, m/s | GT-header20ms, m/s | Grid dịch10ms, m/s | Path RMSE, mm | Marker/stop/bounds |
|---|---:|---:|---:|---:|---|
| B0/1 | 0,004782 | 0,006634 | 0,006639 | 0,025 | Đạt |
| Classical/1 | 0,003716 | 0,005687 | 0,005691 | 0,049 | Đạt |
| Classical/2 | 0,003873 | 0,005671 | 0,005675 | 0,024 | Đạt |
| B0/2 | 0,004958 | 0,006313 | 0,006318 | 0,009 | Đạt |
| B0/3 | 0,005074 | 0,006954 | 0,006959 | 0,011 | Đạt |
| Classical/3 | 0,003805 | 0,005877 | 0,005881 | 0,157 | Đạt |

Tỷ lệ trung bình RMSE classical/B0−1 là **−23,09% native**, **−13,40% ở mỗi
diagnostic grid**. Đây là secondary mô tả ratio-of-means, không paired causal
estimate, CI, mức effect ứng dụng được chấp nhận hoặc giảm slip/contact risk.
Không pool thêm stop8s thành nhiều lặp cùng điều kiện.

Diagnostic đã predeclare: latest raw GT tại/trước grid20ms/dịch10ms, nominal
held theo interval native tại GT header. Mỗi lượt696/695 điểm grid; support
age≤20ms, không nội suy body. Khác aggregation/reference alignment so native,
không gọi hai mức phần trăm là cùng estimand. GT50Hz không có độ phân giải10ms.

## 4. Trade-off và giới hạn cơ chế

| Pha/chỉ số | B0 | Classical |
|---|---:|---:|
| Steady RMSE v, m/s | 0,006412–0,006882 | 0,002548–0,002909 |
| Deceleration RMSE v, m/s | 0,005377–0,006156 | 0,005431–0,005793 |
| Max path error, mm | 0,0119–0,0499 | 0,0311–0,1980 |
| Max estimate position error, mm | 2,57–2,96 | 2,94–9,37 |

**[S]** Tín hiệu chính nằm ở steady tracking; pha hạ vẫn chồng lấn B0,
không kết luận stopping tốt hơn. Path không cải thiện đồng thời; mọi lượt
vẫn dưới bounds đề xuất40mm path/50mm estimate/0,05rad yaw. Classical/2 có
initial GT x≈−7,17mm trong khi estimate khởi tạo0 theo protocol: không loại
lượt hoặc align GT để che khác biệt. Đây là giới hạn nhân quả/fresh launch.

Known stop là thông tin từ reference generator; không phải preview gờ/cáp.
Kết quả chỉ hỗ trợ hai lịch stop6s/8s đã thử ở clear fixture, không toàn bộ
miền liên tục giữa chúng, mọi tốc độ/tải/caster hoặc nhiều vật cản. Reward
return không được dùng để promote; đây chưa là nghiên cứu H1/H2/H3 contact.

## 5. Integrity và software

**[N — artifact]** 103 batch files khớp SHA256; prelaunch snapshot92 file
khớp trước cập nhật hồ sơ kết quả. Parent chain và53 file checkpoint V3
lịch sử giữ hash, dù không load actor trong batch này. 1.740 physics requests
đúng ACK/completion/iteration và clock delta1ms/step; retry0.12 parameter
readbacks hoàn tất. 840 trace rows giữ proposal/accepted/final riêng;
4.200 estimator updates có causal gyro/wheel support hợp lệ. Source age tại
native boundaries tối đa19ms; không là latency phần cứng.

Raw joint/drive có gap tới109/203ms trong artifact, gồm giai đoạn startup;
native boundary support vẫn mới. Counts/hash và causal boundary checks
không chứng minh mọi transient đã được ghi liên tục hoặc loss-free. Primary
và hai diagnostic dùng body GT/nominal tương ứng, không dùng gap drive để
suy actuator limiter đầy đủ hoặc kết luận slip.

16 contract/control tests +16 GUI tests đạt; build và source/install parity,
GUI6×10/default profile mới/khóa rerun được ghi trong
[verification](NINO_SIM_STOP_TRANSFER_VERIFICATION_2026-11-05.json).
Software tests không cộng vào6 physics launches. Job/outer exit0, không còn
process Sim do job sở hữu; ledger đã đóng, không retry hoặc thêm lượt.

QA gồm audit/plot, source snapshot, XML tests và screenshot tại:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_stop_transfer_2026-11-05/`.

## 6. GUI và việc tiếp theo

**Xây project → NHÁNH SIM → Chuyển lịch dừng · stop6s / withdraw5,5s / B0**:
bảng từng lượt, primary/diagnostic/path/pha hạ và trạng thái budget đã đóng.
TRAIN TD3 và các profile lịch sử vẫn riêng. Dữ liệu robot thật chưa thêm,
cutoff02/11; không SSH, flash, enable hoặc phát lệnh motor.

**Một việc tiếp:** chốt remaining gap, information budget và acceptance
contract cho TD3 so baseline cổ điển. Không có gap đáng quan tâm thì dùng
baseline trong envelope Sim hẹp và dừng learning cho envelope đó. Chỉ mở
pilot learner mới khi contract trả lời được lý do cần học, không tự tăng
timesteps dựa trên6 lượt thắng của classical hoặc512 bước cũ của TD3.
