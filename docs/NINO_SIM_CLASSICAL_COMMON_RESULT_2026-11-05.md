# Kết quả Sim: bù common cổ điển có planned-stop withdrawal

05/11/2026 · **Đã đóng đủ6/6 fresh launches,840 evaluation ticks, optimizer0.**
Không train thêm, dùng checkpoint V3 cũ đóng băng cho arm TD3 common-only.

## 1. Quyết định

**[N — mô phỏng]** Trong scenario clear đã xem, common cố định +0,005m/s,
rút trước lịch dừng, có RMSE vận tốc toàn14s thấp hơn cả B0 và frozen TD3
common-only ở cả hai lượt. Tất cả đạt marker/quiet stop và engineering bounds.

**[S]** Đây là bằng chứng ủng hộ ưu tiên baseline cổ điển cho tracking sàn
sạch. Không có lý do từ batch này để tăng ngân sách TD3/history/PPO hoặc
học steering residual. **Chưa promote ứng dụng hoặc triển khai thật**:
effect tối thiểu đáng quan tâm chưa được chấp nhận, chỉ hai launches/arm,
reference/stop schedule đã biết và chưa có kiểm tra transfer của lịch dừng.

**Giới hạn information budget:** candidate cổ điển được cấp decision clock
và lịch source stop đã biết; actor frozen h5 không có feature preview lịch
dừng tương ứng. Đây là so sánh hai cấu hình hệ thống như đã chốt, **không
là bằng chứng thuật toán cổ điển thắng TD3 dưới cùng thông tin**. Amplitude
cũng khác. Muốn so thuật toán công bằng phải chốt contract mới cho preview
ở cả hai, hoặc cùng rule rút action; không sửa arm sau khi đã thấy kết quả.
Actor này đã train512 transition trên gờ6mm trong pilot V3; candidate cổ
điển được chọn từ B0 clear đã xem. Batch không match training/tuning
budget, không chứng minh TD3 không thể học tốt hơn với contract khác.

**[Đ]** Giữ B0 là đối chứng, giữ common cổ điển là candidate nghiên cứu.
Bước tiếp là [kiểm chuyển lịch dừng sang6s](NINO_SIM_STOP_SCHEDULE_TRANSFER_NEXT_2026-11-05.md),
tối đa6 lượt mới/optimizer0, **chưa chạy**. Không mở lại batch này.

## 2. Đã chạy gì?

[Protocol chốt trước chạy](NINO_SIM_CLASSICAL_COMMON_NEXT_PROTOCOL_2026-11-05.md)
và config `residual_classical_common_v1.yaml`:

- Arm B0; common cổ điển; frozen V3 common-only, mỗi arm hai fresh launches.
  Thứ tự B0/classical/TD3/TD3/classical/B0, đúng6 lượt, không retry.
- Clear box, yaw0, cruise0,2m/s; source0,5–8s, horizon14s,100ms/tick;
  giữ wheel/IMU estimator, follower, h5/100D, projection/ramp và wheel PI.
- Common cổ điển chỉ bật khi zero-residual nominal shaper đạt0,2m/s và
  source/history/permission hợp lệ; proposal là `[0,125;0]`, tương ứng
  +0,005m/s mỗi bánh trước projection. Rút proposal từ decision7,5s.
- Yaw follower vẫn hoạt động; không sửa gain/current/torque cap hoặc
  bypass projection. Không dùng GT/contact để chọn action.
- Mỗi arm classical bật **50 ticks**, decision2,5..7,4s; nominal adapter
  khớp scorer **đúng từng tick**. Dấu thời gian outcome cuối tick muộn hơn
  decision đầu tick0,1s theo định nghĩa step, không là latency đo mới.
- Frozen TD3 giữ raw actor và proposal sau mask riêng. B0/classical không
  gọi actor; hai lượt TD3 tổng280 actor calls. Không xuất replay để học từ
  masked action, không cập nhật checkpoint.

Root:
`/home/tuanmac/nino_research/sim_classical_common_v1/20261105T042614286503Z_sim-classical-common`.
Fingerprint module/config/script:
`02a7fc89d1614a44685ca15abc8a88ad4ca4caf925911369312d7f81263dba07`.

## 3. Primary và constraints: toàn14s

**[N — mô phỏng]** Primary giữ RMSE body v so nominal shaped reference
độc lập với residual trực tiếp; không đổi sang steady-only sau kết quả.

| Arm / lượt | RMSE v, m/s | RMSE path, mm | Max path, mm | Marker + stop | Engineering bounds |
|---|---:|---:|---:|---|---|
| B0 /1 | 0,004916 | 0,145 | 0,191 | Đạt | Đạt |
| Classical /1 | 0,004162 | 0,052 | 0,080 | Đạt | Đạt |
| TD3 common /1 | 0,005808 | 0,282 | 0,440 | Đạt | Đạt |
| TD3 common /2 | 0,005884 | 0,633 | 0,971 | Đạt | Đạt |
| Classical /2 | 0,004253 | 0,122 | 0,159 | Đạt | Đạt |
| B0 /2 | 0,005092 | 0,022 | 0,030 | Đạt | Đạt |

Tỷ lệ trung bình hai RMSE classical so trung bình hai RMSE B0 là **−15,92%**.
Đây là secondary summary mô tả, không paired causal estimate, CI hoặc gate
benefit ứng dụng. Giá trị per-run phía trên vẫn là primary. Không gọi nó là
giảm15,92% slip/contact risk hoặc hiệu quả được bảo đảm.

Path hai arm cổ điển đều nhỏ, nhưng không có phân tách mọi classical tốt hơn
mọi B0. Engineering bounds giữ maxpath40mm, maxestimate50mm/yaw0,05rad,
marker0,95m +quiet stop2s, chưa là yêu cầu nhà máy được chấp nhận.
Marker0,95m không là full navigation/arrival goal3m.

## 4. Diagnostic pha đã định nghĩa trước

| Arm | Steady RMSE v, m/s | Deceleration RMSE v, m/s |
|---|---:|---:|
| B0 | 0,005159–0,005561 | 0,006334–0,006599 |
| Classical | 0,002189–0,002438 | 0,006958–0,007088 |
| TD3 common | 0,002898–0,002938 | 0,012666–0,012855 |

**[S]** Bù nhỏ hơn, rút trước known stop, giữ được phần cải thiện steady và
tránh phần lớn chi phí deceleration của frozen common actor. Pha hạ của
classical **vẫn hơi tệ hơn B0**; không tuyên bố đã tối ưu stopping hoặc
chứng minh nguyên nhân cơ khí/PI duy nhất. Hai hành vi cùng đổi amplitude
và thời điểm rút theo candidate đã chốt; batch không tách riêng effect hai
tham số. Không dùng nó để suy ảnh hưởng thuần của withdrawal0,5s.

Common cổ điển có maxestimate position error4,25–12,24mm, so B0
2,73–2,95mm. Lượt classical/1 có initial GT x khoảng−9,89mm trong khi
estimate được khởi tạo0 theo metadata. Không căn chỉnh GT hoặc loại lượt;
khác initial state này làm rõ giới hạn so sánh nhân quả, không đủ kết luận
compensation làm estimator kém hơn. Fresh launch/seed701 không snapshot
đầy đủ trạng thái caster/contact.

## 5. Integrity và software readiness

**[N — artifact]**

- **91 file** manifest batch khớp SHA256; prelaunch source hashes không đổi.
  **53 file** checkpoint V3 vẫn khớp manifest pin, SHA256
  `8cc9cbeafeea220074638185535d7a23d6a84156424b2e2a8f656414c6e71578`.
- **1.740 physics requests** đúng ACK/completion và iteration/clock delta,
  physics1ms; retry0. **12 parameter readbacks** hoàn tất.
- **840 rows** giữ requested/controller/projection/final/target riêng;
  **4.200 estimator updates** đạt causal gyro/wheel support checks.
  Tuổi source lớn nhất tại native boundaries15ms; không là hardware latency.
- Một số raw drive-publication gaps tới291ms; source drive tại native
  boundaries vẫn mới trong trace. Không dùng batch để kết luận mọi transient
  limiter/target đã được quan sát. Primary body/nominal v dùng cùng native
  grid100ms; counts/hash không thay contract continuous coverage hoặc là
  bằng chứng loss-free. GT50Hz không cho timing body dưới20ms.
- Job và outer process hoàn tất **exit0**. Không còn process sim thuộc job.
  Ledger được giữ trước launch đầu; batch không được mở lại dù lỗi/hủy.
- **14 contract/control tests và20 GUI tests đạt**, build `nino_pi/nino_rl`.
  Đây là software tests, không cộng vào số6 physics launches.

**Diagnostic timestamp sau kết quả:** đọc lại raw GT theo header, dùng grid
20ms và dịch+10ms, latest sample tại/trước grid; nominal giữ theo native
control interval tại timestamp của GT. Không nội suy body. Primary endpoint
100ms phía trên giữ nguyên; cách đồng bộ/aggregation này là metric diagnostic
khác, không thay primary bằng cách có lợi hơn.

| Arm | GT-header diagnostic RMSE v, m/s; cả hai grids |
|---|---:|
| B0 | 0,006443–0,006504 |
| Classical | 0,006289–0,006347 |
| TD3 common | 0,007364–0,007698 |

Thứ tự classical tốt hơn vẫn giữ ở cả hai grids, nhưng tỷ lệ trung bình
RMSE so B0 chỉ khoảng **−2,4%** theo diagnostic này. Không đồng nhất hai
estimand/reference alignment để gọi −15,92% là lợi ích bền vững mọi cách đo.
Độ lớn nhỏ/phụ thuộc đánh giá và requirement chưa chốt là lý do giữ mức
candidate, chưa promote. Artifact `timestamp_sensitivity.json` giữ toàn bộ
per-run, support age, method và caveat; không chọn bỏ grid kém thuận lợi.

GUI mới: **NHÁNH SIM → Common cổ điển · planned stop / B0 / frozen common**.
Có bảng từng lượt, phase metrics, thời điểm bù cuối, kết quả gate và budget
đã khóa. Các profile lịch sử cùng GUI train/resume TD3 giữ riêng.

[Verification](NINO_SIM_CLASSICAL_COMMON_VERIFICATION_2026-11-05.json)
và QA tại
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/sim_classical_common_2026-11-05/`
giữ audit, source snapshot, plot và native GUI screenshot.

## 6. Điểm dừng và điều chưa kết luận

Chưa có evidence về stop-time transfer, payload, đường cong, gờ/rãnh/dây
mềm, first-contact H2, learned predictor/history benefit, robot thật hoặc
calibration actuator. Mọi dữ liệu trong báo cáo là sim/software; data-cutoff
robot thật vẫn02/11. GUI train là công cụ, không làm batch này có optimizer.

**Một việc kế tiếp:** kiểm candidate không tune lại ở source stop6s,
withdrawal=stop−0,5s, cùng B0 trong một protocol mới. Qua → cân nhắc giữ
baseline cổ điển cho envelope stop đã kiểm; fail/unknown → giữ B0 và dừng
đầu tư vào compensation này, không tự tăng số mẫu hoặc train để che lỗi.
