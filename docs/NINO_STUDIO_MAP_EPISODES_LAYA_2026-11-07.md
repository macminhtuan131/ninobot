# Studio: bản đồ sim và thống kê episode/checkpoint

## Giao diện

Trong **Train TD3 · Sim**, bên dưới tiến độ live có bốn tab:

1. **Robot / world live:** tường, sàn, objects từ collision geometry của đúng
   SDF đang dùng; pose/hướng GT sim, vệt GT và estimator của episode hiện tại,
   đường tham chiếu. Có zoom, kéo map, toàn map và theo robot. Hiện tuổi trace
   theo wall clock; không nội suy thêm pose để làm chuyển động trông liên tục.
2. **Sau mỗi episode:** số bước/global cuối, source stop, return, velocity
   RMS và path RMS native, task/stop, termination và Laya advisory.
3. **Sau mỗi checkpoint:** global step, critic counter, replay size, periodic/
   final, metric window và Laya advisory, đường dẫn bundle đã publish.
4. **Evaluation riêng:** các arm và kết quả evaluation đã hoàn tất của job.

Với common trainer, khi chuyển sang evaluation, map theo trace của arm đang
chạy và hiện nhãn EVAL/arm; bảng episode train vẫn giữ riêng.

Lượt hiện tại `20261107T080414816378Z_common_train` dùng `clear_box`: bốn
tường và một sàn, không có cáp/hõm trong scene đang train. File mixed và gờ
6 mm được chuẩn bị trong cùng thư mục không có nghĩa chúng đang được chạy.
Không vẽ vật thể từ một scenario khác vào map hiện tại.

## Nguồn và semantics

- Reader chỉ mở artifact; không tạo ROS subscriber, đọc quyền motor hoặc
  điều khiển Gazebo. Engine, checkpoint, replay, reward, ABI và ngân sách
  train đang chạy được giữ nguyên.
- `worlds.json` chọn đúng scenario, kiểm SDF hash trước khi parse. Composed
  model/link/collision poses được dùng cho footprint nhìn từ trên xuống.
  Box/cylinder/sphere được hỗ trợ; mesh/include/relative frame chưa giải được
  phải báo thiếu. Marker robot là ký hiệu pose, không phải collision footprint
  đã đo. Đây là scene khai báo; vật thể động cần telemetry riêng.
- `environment_trace.jsonl` là nguồn chính; legacy có thể dùng
  `training_trace.jsonl`. Đọc tăng dần trong QThread, tối đa 16 MiB/lần,
  chỉ parse dòng đủ newline. Backlog được ghi rõ. Không giữ observation/
  replay trong GUI; chỉ scalar aggregates và vệt của một episode.
- Metric episode là RMS trên mẫu native có mặt, từng trường có sample count.
  Thiếu metric → unknown. Mean window là trung bình RMS từng episode, không
  đổi thành pooled RMS. Return là tổng reward có dữ liệu, không là chứng cứ
  policy tốt hơn baseline.
- Chỉ terminal episode mới có task success/stop. Episode cắt giữa chừng khi
  job đóng là `right_censored`; không tính thành thành công hay thất bại.
- Global offset continuation lấy từ parent checkpoint. Không ghép các episode
  từ parent vào thống kê job này. JSONL lỗi làm offset suy từ số dòng unknown.
- Chỉ thư mục checkpoint không `.pending` và có manifest mới được đưa vào
  bảng; đây là nhận diện bundle đã publish, chưa phải hash/replay QC cuối.
- Window checkpoint lấy tối đa 20 episode hoàn chỉnh kết thúc **trước hoặc
  tại global step lưu**. Không lấy episode sau checkpoint. Nó mô tả quá trình
  train tới checkpoint; chưa là frozen-policy evaluation của checkpoint đó.

## Laya

`training_laya_worker.py` dùng lại `report()` và `classify()` trong monitor
Laya hiện có, qua adapter chỉ ánh xạ các metric Nino thực sự có. Chạy process
riêng, CPU một luồng, nice 10, HuggingFace/Transformers offline; không tải model
khi train. Numeric tables tiếp tục hoạt động khi classifier thiếu model/lỗi.

Khi mở lại job có lịch sử, bảng số liệu được backfill toàn bộ; Laya chỉ nhận
xét window mới nhất và các checkpoint. Sau đó mỗi episode/checkpoint mới
có request riêng, tránh inference lặp lại khi GUI poll. Checkpoint advisory
nhận đúng các episode trước checkpoint. Nhận xét và confidence hiển thị
riêng, chưa hiệu chuẩn cho Nino. Không có quyền tự đổi gain/reward/stage,
promote checkpoint hoặc cấp thêm train budget.

Phép kiểm thực tế trên trace live đã chạy được Laya từ cache. Classifier trả
`goal_accuracy`, confidence `0.339`, trong khi failure-count group là
`no_clear_issue`. GUI ghi **KHÁC counts**. Chưa có endpoint metric trong
adapter này để xác nhận nhãn goal; không biến nhãn đó thành kết luận có lỗi
goal. Giá trị confidence này không là xác suất an toàn hoặc xác suất task fail.

## Kiểm chứng

Artifact tại workspace client:
`artifacts/training_map_episode_dashboard_2026-11-07/` gồm ảnh map/episode/
checkpoint, kiểm reader, Laya, GUI, tests và build log.

Kiểm trên worker PID 489244 hiện có: đọc 7.555 transition, 54 episode gồm
episode đang chạy, một checkpoint 25.000 và năm collision shapes. Ảnh chỉ
là snapshot khi kiểm, không đại diện kết quả cuối. Đóng GUI test giữ worker
train sống; GUI không tạo process train hay thao tác hardware.

Tests kiểm transforms SDF và cylinder nằm ngang, collision/visual dedup,
world hash, episode reset, resume offset, RMS, partial line, censoring,
checkpoint publication/window, Laya attribution và vòng đời Qt; các tests
Studio trước đó vẫn được giữ. Không chạy thêm Gazebo/train để kiểm GUI.
Kết quả cuối: **38 tests đạt**, package `nino_pi` build thành công.

Kiểm bản install phát hiện helper cũ chỉ tìm source đúng ở layout `src`.
Đã sửa lookup theo ancestor workspace và vẫn ưu tiên `NINO_REPO` khi đặt rõ;
thiếu source chỉ tắt advisory và báo lỗi, không lặp traceback trong GUI.

Bản install sau correction đã mở cửa sổ **Nino Studio · Map / Episode /
Laya · Live**. Snapshot mới: 8.680 transition, 62 episode gồm lịch sử của
job này, một checkpoint 25.000; Laya có nhận xét riêng cho episode window
và checkpoint window. Cả năm file engine ghi trong metadata checkpoint vẫn
khớp hash; worker PID 489244 tiếp tục chạy. Ảnh đã được xem để kiểm màu chữ,
world/pose và các cột thống kê.
