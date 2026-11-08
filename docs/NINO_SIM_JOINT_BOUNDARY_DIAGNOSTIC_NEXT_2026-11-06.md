> Cập nhật06/11: diagnostic riêng đã chạy/đóng2launches/200zero ticks;612supportchecks đều đạt, chưa tái hiện50ms, nguyên nhânunknown. Không mở lại TD3. Xem [kết quả](NINO_SIM_JOINT_BOUNDARY_RESULT_2026-11-06.md) và [candidate tiếp](NINO_SIM_JOINT_RELIABILITY_CANDIDATE_NEXT_2026-11-06.md). Nội dung draft bên dưới giữ làm lịch sử.

# Bước kế: phân biệt joint source / DDS / consumer ở biên physics

06/11/2026 · **Draft, chưa release/chạy thêm physics hoặc training.**

## Bằng chứng đã đủ, không cần train lại để xác nhận

Pilot common TD3 đóng sau700transition. Episode6 reset +settle đạt; request
50physics steps đầu đưa sim2,651→2,701s, ACK/completion đạt, retry0.
Wheel callback cuối stamp2,651s; IMU/GT tới2,700s, drive2,688s. Request bằng
zero, chưa đến source forward. Đợi feedback5wall seconds vẫn không đủ.
Đây là thiếu support cho tick đang thực hiện, không phải TD3 phát action
quá lớn hoặc task/stop thất bại. Giữ gate40ms, không thêmphysics để “lấy mẫu mới”.

Khoảng joint liên tiếp lớn nhất trong raw chỉ4ms **không phủ nhận** thiếu
đuôi50ms: chưa có mẫu mới ở cuối để tạo một inter-sample gap. QC phải có
source endpoint age/coverage, không chỉ max(diff(stamps)).

## Làm offline trước

1. Giữ nguyên77file/manifest và source113file trước chạy. Đối chiếu world
   ACK/clock với receipt monotonic và cuối từng channel; phần này đã audit.
2. Đọc wiring chính xác: joint_state_broadcaster ROS → observer best-effort
   depth100/SingleThreadedExecutor; không phải joint đi qua Gazebo parameter
   bridge. IMU/GT dùng đường bridge khác. Tránh sửa bridge không nằm trên đường joint.
3. Đối chiếu cấu hình broadcaster/realtime publisher và consumer callbacks.
   Raw hiện có chỉ cho biết observer không nhận joint mới; chưa phân biệt
   upstream publication, DDS hay executor. Không quy CPU/GC/QoS là nguyên nhân chắc.

## Nếu cần live: một diagnostic độc lập, không learner

Đề xuất tối đa **2fresh launches**, mỗi launch tối đa100native ticks zero
(10simulation seconds; setup settling cùng parent, giới hạn riêng). Trước
chạy phải có protocol/hash/ledger mới và freeze script. Không coi đây là
slot còn lại của pilot TD3, không auto retry hoặc dời gate.

- Không actor/optimizer/forward source. Cùng model, physics1ms, chunk50ms,
  source intervals100ms, PI/estimator và tải ghi instrumentation tương đương.
- Hai process ROS nhận `/joint_states` độc lập; một process chỉ ghi stamp,
  sequence nội bộ/receipt/hash payload, không convert contact hoặc phát lệnh.
- Discovery/log QoS và identity publisher. Nếu có thể instrument chính
  broadcaster bằng counter gửi/thành công thì phải version source thay đổi;
  không coi hai ROS subscribers đủ chứng minh source thật đã publish.
- Log cuối half-tick: targetclock, lastsource stamp và receipt của từng
  observer, source count trước/sau, ACK/iterations, explicit timeout.
- Không suy real transport latency từ simstamp hoặc clockpaused.

| Quan sát | Kết luận được | Hành động |
|---|---|---|
| Observer phụ có mẫu mới, primary thiếu | Thu hẹp lỗi về đường delivery/consumer primary | Chỉ một correction có căn cứ; fixture parity/source/ABI phải giữ |
| Cả hai thiếu, có counter upstream publish thành công | Nghi đường ROS transport/delivery; chưa tách DDS/OS | Giữ raw; không sửa reward/gain |
| Cả hai thiếu, counter upstream cũng không tiến | Thu hẹp về broadcaster/source | Correction source riêng, không “vá” bằng GT/primary khác |
| Cả hai đủ ở cả2launches | Chưa tái hiện; **unknown**, không chứng minh loss-free | Không tự kéo dài diagnostic hoặc release full training |

Một lỗi: đóng lượt/slot còn lại, retain. Kết quả không phân biệt được cơ chế:
unknown và quyết định ưu tiên classical/measurement trước; không lặp nhiều
pilot train để tìm lần chạy may mắn. Chỉ sau correction riêng đã có bằng
chứng readiness mới đề xuất một ngân sách learner mới; partialcheckpoint
hiện tại không tự được resume.
