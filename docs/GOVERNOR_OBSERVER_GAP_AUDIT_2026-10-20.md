# Audit offline — observer gap ở attempt 9

**Ngày:** 20/10/2026. **Phạm vi:** trace đã lưu của attempt 9; tám attempt
còn lại chỉ dùng kiểm tra bối cảnh acquisition. Không chạy simulation,
không sửa controller, logger runtime, sampling, metric hoặc gate coverage.

## 1. Kết luận và quyết định

**Mất dữ liệu được khoanh vùng ở đường acquisition của observer riêng.**
Không có bằng chứng robot mất toàn bộ cảm biến hoặc vòng PI/governor bị
ngắt tương ứng. Bằng chứng phù hợp với logger không tiêu thụ subscription
trong một khoảng, rồi chỉ còn backlog ngắn trong các queue KEEP_LAST.

**Chưa xác định được nguyên nhân sâu hơn:** callback/executor bị chậm,
JSON/write/flush bị chặn, scheduling của process hay delivery tại participant
của observer. Không có wall-clock callback/write timing hoặc message-lost
telemetry trong dữ liệu đã lưu để phân biệt chúng. Không gọi disk I/O hay
CPU overload là nguyên nhân đã chứng minh.

**Quyết định:** giữ measurement failure của attempt 9 và giữ batch dừng ở
9/12. Không sửa governor, tăng queue, đổi QoS, giảm log rate, nội suy qua
gap hoặc đổi yêu cầu coverage để tiếp tục batch. Một thay đổi instrumentation
hợp lý tiếp theo là **thêm monotonic wall-time cho callback và các đoạn
conversion/write/flush của observer**, kèm bộ đếm sức khỏe acquisition. Đây
là đề xuất chưa implement; không phải correction độ tin cậy đã xác nhận.

## 2. Gap nằm ở đâu?

Trong `samples.jsonl`, dòng 17628 là joint stamp 16,408 s, callback receipt
16,409 s. Dòng 17629 đã là contact stamp 19,725 s, receipt 19,729 s. Không
có record nào khác chen giữa hai dòng này; các file vẫn parse được đầy đủ.

`receipt_time_s` dùng ROS simulation clock. Chênh lệch **3,320 simulation
seconds** không được gọi là 3,320 giây wall-time bị block. File không có
monotonic timestamp cho từng callback để đo thời gian thật đó.

| Kênh observer | Stamp cuối trước gap (s) | Stamp đầu sau gap (s) | Gap (s) |
|---|---:|---:|---:|
| IMU | 16,400 | 19,640 | 3,240 |
| GT | 16,400 | 19,640 | 3,240 |
| Joint | 16,408 | 19,720 | 3,312 |
| Odom | 16,404 | 19,644 | 3,240 |
| Drive diagnostics | 16,392 | 19,632 | 3,240 |
| Governor state | 16,389 | 19,529 | 3,140 |
| Contact bánh trái | 16,398 | 19,725 | 3,327 |
| Contact bánh phải | 16,402 | 19,725 | 3,323 |
| Contact caster trái | 16,396 | 19,725 | 3,329 |
| Contact caster phải | 16,404 | 19,725 | 3,321 |

Khoảng trống contact riêng có thể do chỉ publish contact không rỗng; nó
không tự chứng minh lift-off hoặc loss. Ở đây, gap đồng thời của các kênh
IMU, joint, GT, diagnostics và state là bằng chứng chính về acquisition.

Trong tám attempt trước, gap GT/IMU trong route tối đa khoảng 20 ms; gap
joint tối đa khoảng 10 ms. Không thấy gap đa giây tương tự, kể cả ở hai
fast attempts trước. Vì vậy chưa có cơ sở quy lỗi cho mọi run 20 ms hoặc
đổi cadence governor để xử lý lỗi này.

## 3. Cảm biến và control có tiếp tục không?

Đọc trực tiếp CSV của evaluator trong khoảng receipt gap
`(16,409; 19,729)` s, không tạo grid mới:

| Trace evaluator | Số record trong gap | Gap tối đa | Feedback quan sát được |
|---|---:|---:|---|
| Governor update | 165 | 20 ms | IMU age ≈9 ms; joint age ≈1 ms; drive feedback age ≈17 ms |
| Control/native snapshot | 33 | 100 ms | GT age ≈9 ms; joint age ≈1 ms |
| Drive | 166 | 20 ms | Reference, actual wheel speed và torque vẫn có record |

Các **source stamps tăng qua đoạn observer thiếu**. Đây là dữ liệu mới được
evaluator nhận, không phải lặp lại sensor snapshot cũ. Bằng chứng loại trừ
giả thuyết publisher/bridge/control cùng dừng toàn bộ trong khoảng đó.
Vẫn không loại trừ lỗi delivery chỉ ảnh hưởng observer subscriber.

Không dùng các CSV này để tái dựng ground truth 50 Hz đã mất. Chúng có
cadence/fields khác; thay thế sẽ đổi sampling của metric đã khóa.

## 4. Dấu vết queue khi observer hoạt động lại

Source `governor_logger.py` hiện tại khớp SHA256 ghi ở metadata của attempt
9. Code dùng `qos_profile_sensor_data` cho sensor/diagnostics/contact; kiểm
tra local rclpy không tạo node cho thấy **KEEP_LAST, depth 5, BEST_EFFORT**.
State subscription dùng integer depth **10**. Không giả định tên RMW/DDS
vendor vì run không ghi đủ thông tin đó.

Tại receipt simulation time **19,729 s**, file ghi liên tiếp:

- IMU và GT: **19,640 / 19,660 / 19,680 / 19,700 / 19,720 s** — năm mẫu.
- Joint: **19,720 / 19,722 / 19,724 / 19,726 / 19,728 s** — năm mẫu.
- State: **19,529 đến 19,709 s**, bước 20 ms — mười mẫu. State rows không
  có receipt timestamp; chỉ xác nhận chúng nằm trong nhóm dòng sau resume.

Khớp giữa backlog năm/mười mẫu với depth tương ứng là bằng chứng mạnh về
**queue hữu hạn chỉ giữ phần gần nhất khi observer không tiêu thụ kịp**.
Nó chưa cho biết lúc đó executor đang block tại hàm nào hay thread delivery
có bị đình trệ không. Không có counter middleware để gán chính xác mọi mẫu
mất cho một cơ chế overflow cụ thể.

Trong route, file lưu 679 state rows so với 835 evaluator updates; GT/IMU
còn 674 stamp trong route. Metadata counts của attempt 9 khớp số dòng file,
không có malformed JSON và không tìm thấy các source stamps bị thiếu ở
vị trí khác trong file. Không phải lỗi loader lọc bỏ những dòng đã lưu.
Các kiểm tra này không chứng minh hệ điều hành không từng block writer.

## 5. Code path và giới hạn nhận dạng nguyên nhân

Logger dùng `rclpy.spin(node)` với executor mặc định. Các subscription cùng
default callback group; callback thực hiện đồng bộ:

`message_to_ordereddict → finite_json → json.dumps → stream.write`.

Timer steady-clock mỗi 1 giây gọi `flush` của hai stream và viết metadata
đồng bộ. Stream raw có buffer 1 MiB. Không có heartbeat wall-time, callback
duration, writer/flush duration hay queue-loss diagnostics. Không có lệnh
sleep hoặc gate theo phase cố ý dừng ghi tại 16,4 s. Source SHA khớp executed
source; những nhận xét này áp dụng cho code thực sự chạy.

Do đó synchronous serialization/write/flush và scheduling đều là giả thuyết
hợp lý, **chưa phân biệt được bằng dữ liệu đã lưu**. Thêm worker thread hay
tăng history ngay lúc này là thay đổi chưa có bằng chứng riêng đủ mạnh.

Exception logger trong `gazebo.log` xuất hiện sau launcher thông báo SIGINT
và gửi tín hiệu shutdown; không có runtime exception trước đó được log.
Không dùng cleanup traceback làm nguyên nhân hồi tố cho gap trong route.
`metadata.complete=true` chỉ nghĩa đã close logger, không bảo đảm coverage.

## 6. Ảnh hưởng đến kết quả giữ nguyên

- Arrival và dừng của attempt 9 vẫn **success**; không đổi thành lỗi nhiệm vụ.
- Native slip replay vẫn khớp RMS **0,030711177593437788**.
- GT/joint coverage toàn tuyến vẫn **80,1198%**, dưới gate **98%**.
- Whole-route GT slip và planned complete-population aggregate/CI vẫn
  unavailable; không phục hồi bằng interpolation, window mới hoặc subset.
- Slots 10–12 chưa chạy, release cũ không resume; không thêm simulation.
- Ngưỡng ứng dụng vẫn đề xuất, không quyết định H2 và không mở Optuna/ML.

**72 input hashes** của execution review được kiểm tra trước và sau audit;
không input nào đổi. Frozen protocol/source/config và native outcome giữ
nguyên. Các artifact mới chỉ phục vụ chẩn đoán acquisition.

## 7. Một bước tiếp theo có căn cứ

Chuẩn bị **observer health telemetry** tối thiểu: monotonic timestamp lúc
vào/ra callback và duration conversion/write/flush, cùng counter nhận/ghi
và lỗi. Ghi riêng health sidecar, không thêm phụ thuộc của controller vào
logger. Kiểm tra offline bằng stall giả lập để phân biệt write chậm với
khoảng không được schedule; chưa cần Gazebo.

Telemetry này chưa implement trong audit. Chưa có cơ sở tuyên bố sửa được
gap, tăng depth sẽ đủ, hoặc phải giảm tốc simulation. Bất kỳ batch simulation
mới nào vẫn cần protocol/budget riêng; không khôi phục budget đã hard-stop.

## 8. Artifacts và tái lập

- [Report JSON](governor_observer_gap_audit_2026-10-20/report.json): đủ chín
  attempt, các channel gap, count differences và nguyên trạng native outcome.
- [Raw boundary, byte offsets và backlog](governor_observer_gap_audit_2026-10-20/gap_boundary.json).
- [Evaluator continuity](governor_observer_gap_audit_2026-10-20/evaluator_continuity.json),
  kèm ba CSV trích nguyên field values trong cùng thư mục.
- [Executed logger source](governor_observer_gap_audit_2026-10-20/executed_governor_logger.py).
- [Input hashes](governor_observer_gap_audit_2026-10-20/inputs_sha256.json).
- [Local QoS inspection](governor_observer_gap_audit_2026-10-20/local_sensor_qos.json):
  import profile để đọc cấu hình, không tạo ROS node.
- [Script audit](governor_observer_gap_audit_2026-10-20/audit_observer_gap.py).

```bash
rtk bash -c '
cd ~/ninorobot
.venv/bin/python docs/governor_observer_gap_audit_2026-10-20/audit_observer_gap.py \
  --run rl_runs/governor_cadence_experiment_2026-10-20 \
  --output /tmp/nino_observer_gap_audit_new
'
```

Output phải là thư mục chưa tồn tại. Script không import ROS runtime,
không tạo node/process simulator, không sửa ledger hoặc tính lại metric.
