# Qualification Gazebo cho gain common — v1

Ngày 06/11/2026. Tiếp theo parity offline đã seal; không thay backend/context
`deccb946…f469f`, không thay kết quả hoặc checkpoint của các đợt đã đóng.

## Câu hỏi và ngân sách

So sánh B0, Classical_scheduled và Causal_gain_candidate trên clear-box với
gain cố định chưa biết. Thứ tự: gain 1, rồi 0,98, rồi 1,02; mỗi gain chạy ba
baseline theo thứ tự trên. **9 fresh launches × 140 tick = tối đa 1.260 tick**.
Ba cell gain=1 là integration trong ngân sách. Không thêm smoke, retry, actor,
optimizer, training hoặc hardware. Lỗi bất kỳ đóng đợt và mọi slot chưa dùng.

Wall deadline tổng 2.700 s là giới hạn tài nguyên của đợt, không phải ước lượng
thời gian chạy hoặc ngưỡng realtime. Hết deadline giữ failure và không chạy bù.
Mỗi reset vẫn giữ deadline cũ; không nới thời gian hỗ trợ sensor.

Giữ source stop 8 s, horizon 14 s, nominal 0,2 m/s, common ±0,005 m/s,
103D/1D/history5/10Hz, follower/PI/projection/reset ACK+quiet cũ. Gain ±2%
là stress giả định trong sim, chưa phải SysID Nino. Một cell mỗi điều kiện chỉ
screening mô tả; không có CI/power/generalization hoặc exact-state branching.

## Release trước physics

- Prerequisite: manifest parity offline `e1301089…f2ec4`, context ABI
  `99e8488b…55219`; kiểm lại toàn bộ manifest và source chain.
- Runner, script và test có fingerprint riêng; release pin root duy nhất
  `~/nino_research/sim_gain_baselines_v1` và XML tests không fail/error/skip.
- Kiểm executable/entry point, source installed và launch installed khớp.
- Root đã có ledger, kể cả hỏng hoặc failed, không được mở lại.
- ROS domain129, discovery localhost, partition Gazebo riêng, global sim lock.

## Dữ liệu / gate

Lưu raw row trước validator, config, reset, initial view, source stamps và
support, requested/projected/final ROS/effective reference/target/encoder,
gain-map cùng stamp drive, GT riêng, physics ACK, observer và closure.
Gain và condition không vào observation hoặc hàm chọn action.

Validator giữ mọi gate inherited và kiểm map đúng một lần, gain đúng,
pre-map command trung thực, wheel targets và torque trong giới hạn. Ordinary
target ramp/effort slew giữ nguyên và giữ flags; speed clipping không được
coi là clean gain contrast. Không vá gaps bằng observer khác.

Primary: whole14s native nominal-body velocity RMSE. Hai GT header grids
20ms/+10ms báo riêng. Secondary: path≤40mm, marker, dừng yên2s, wheel error,
estimate validity, phase cost và interventions. Không đổi primary sau kết quả.
Rule5% chỉ ngưỡng mô tả đề xuất; yêu cầu nhà máy chưa được chấp nhận.

Nếu causal tốt hơn fixed ít nhất5% trên mọi gain/grid: chỉ ứng viên cần
validation riêng. Nếu causal tệ hơn trên mọi gain/grid: giữ fixed classical.
Đổi dấu theo grid hoặc phụ thuộc gain/hiệu ứng nhỏ: unknown. So cả B0 và
absolute differences; không suy learner cần thiết từ một gap. Không tự mở
holdout, training hoặc nâng biên residual sau đợt.

GUI: profile riêng “Gain baseline”, nút chạy, tiến độ, log, bảng từng cell và
kết quả/failure. Chọn profile không chạy; lỗi/hủy giữ artifact và khóa nút.
