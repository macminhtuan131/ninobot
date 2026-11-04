> **Hiện hành 04/11 — Studio v7:** mặc định là recorder chỉ đọc, MCAP/SQLite, telemetry, annotation, QC, export và profile TD3 có phiên bản. Xem [REAL_DATA_STUDIO.md](REAL_DATA_STUDIO.md). Commissioning/authority và các kết quả phía dưới giữ phạm vi lịch sử; Studio không tự chạy xe.

# GUI v6: thu dữ liệu thật theo sáu bước — 04/11/2026

Mở **Nino · Thu dữ liệu & Xây project** trên laptop, vào tab **Thu dữ liệu thật**.
Nếu GUI đang mở từ bản cũ, đóng rồi mở lại. Launcher cũng có thể chạy bằng:

```bash
bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh
```

Thêm `--demo` để đi thử quy trình; demo không SSH/ROS/motor và luôn Q0.
GUI vừa mở chưa kết nối. Điền IP hiện tại của Pi, kiểm SSH key trong
**Thiết lập SSH**. Chỉ bấm nút chính ở dưới theo chỉ dẫn; không cần ba terminal.

## Các bước và nút cần bấm

| Bước | Bạn làm gì | Nút chính và kết quả cần đợi |
|---|---|---|
| **1. Chọn phiên** | Chọn **Tiến–dừng có video** hoặc **Đứng yên** | **Tiếp tục → Chuẩn bị Pi** chỉ chuyển trang |
| **2. Chuẩn bị Pi** | Kiểm IP/SSH; giữ Pi và logic STM32 có nguồn | Lần lượt **Chuẩn bị bộ thu trên Pi → Kết nối Agent/cảm biến → Kiểm mẫu dữ liệu và thiết bị**. Nếu driver đã chạy, có nút kiểm trực tiếp sau deploy |
| **3. Điều kiện & video** | Điền pose/caster, sàn/tải/pin; với chuyển động: video/mốc đồng bộ và bốn ô xác nhận | Màn hình liệt kê trường còn thiếu. Bấm **Khởi động đường lệnh ZERO**, đợi sẵn sàng, rồi **Tiếp tục → Thu và thử** |
| **4. Thu và thử** | Bấm bắt đầu ghi, đợi mẫu đầu; kiểm lại vùng thử, RC AUTO và sẵn sàng quan sát | **Bắt đầu thu 60 giây** chưa làm xe tiến. Đánh dấu ô xác nhận mới, rồi bấm riêng **YÊU CẦU TIẾN 0,05 m/s · 2 s**. Sau đó chờ recorder đóng |
| **5. Kiểm & quan sát** | Chờ recorder đóng thật; xem QC, chọn xe tiến/tự dừng, không tiến, bất thường hoặc chưa quan sát | **Kiểm integrity/metadata/hash → Lưu quan sát thực tế**. Giữ cả kết quả không tiến/unknown |
| **6. Nhận dữ liệu** | Tải raw và review về laptop | **Tải gói dữ liệu về laptop → Mở thư mục dữ liệu**. Copy video camera riêng, gắn đúng session/mốc đồng bộ |

Thanh bên cho biết bước đã làm; có thể xem lại trang trước mà không chạy tác vụ.
Nút chính luôn ở dưới, nội dung dài cuộn riêng. **Chi tiết/log khi có lỗi**
chứa trạng thái từng process; tự mở khi lỗi. Đường dẫn phiên trên Pi và thư mục
đã tải trên laptop được hiển thị trực tiếp.

### Profile hiện có và giới hạn lượt

- Diagnostic: **0,05 m/s; ramp 0,10 m/s²; source tiến 2 s; zero/disable; bag 60 s**.
- Đứng yên: chỉ recorder 60 s, không stack lệnh/enable/tiến; cần pose/caster và sàn/tải.
- Độ lặp/SysID/vật cản/RL có kế hoạch riêng; wizard không tự mở protocol chuyển động đó.
- Runtime diagnostic hiện có tối đa **một lượt**, giữ ledger trên Pi. Lượt đã dùng/đóng thì báo chặn; đóng/mở GUI hoặc deploy lại không reset.

Một lần bấm tiến là yêu cầu chạy profile, chưa bảo đảm bánh/thân xe di chuyển.
Nếu encoder quay mà video không thấy thân tiến thì giữ hai bằng chứng riêng.
Không đổi gain/current, tốc độ, Collision Monitor hoặc bỏ qua STOP để làm xe chạy.

### Recorder, trạng thái mới và kết thúc

Mẫu/count lấy từ snapshot của recorder; không chỉ nhìn topic/node xuất hiện.
GUI yêu cầu cập nhật trạng thái recorder được nhận trong 2 s và còn ít nhất
33 s thu trước khi mở nút tiến. Đây là gate thao tác, không phải đo latency
sensor/actuator; trial trên Pi vẫn kiểm telemetry/owner/STOP của chính nó.
Hết cửa sổ thì chờ đóng và review, không phát tiến muộn hoặc tự kéo dài phiên.

Khi đã bắt đầu ghi, profile và metadata điều kiện bị khóa để tránh mô tả
khác điều kiện lúc bắt đầu. Quan sát sau lượt vẫn điền được ở bước 5.
Trial kết thúc khác recorder kết thúc. Chỉ event đóng process thật mới mở QC.
Q2 raw không tự chứng minh body motion/slip/physical stop hoặc độ lặp;
checkbox và demo không nâng dataset lên Q3/Q4.

**Hủy tác vụ / Hủy phiên thu** yêu cầu đóng trial → recorder → stack → sensor
do GUI khởi động; giữ Pi có nguồn để đóng file. Khi cần dừng khẩn cấp dùng
nút vật lý. SSH mất không bảo đảm zero/disable đã tới STM32. Không auto retry,
reconnect/resume forward; giữ raw, lỗi và closure unknown để đánh giá.

## Kiểm TD3 bằng nút bấm

Vào **Xây project / sơ đồ → Công cụ kiểm phần mềm**:

1. **Kiểm History/giới hạn/environment**.
2. **TD3 · kiểm optimizer 128 bước**.
3. **Kiểm replay/checkpoint/actor TD3**.

Nếu đã có artifact hợp lệ, có thể kiểm ngay bước 3. Nút chạy trên laptop,
không nối Pi. Báo cáo kiểm đủ 128 transition, checkpoint/optimizer reload,
terminal/timeouts, actor NumPy và rollout có/không authority/Governor.
Đổi checkpoint hoặc mã auditor thì kết quả kiểm cũ không còn đạt cho bản mới.
Chọn dòng kết quả để đọc thông số; lỗi/hủy giữ artifact, không tự train lại.

Đây là smoke trên fixture giảm bậc chưa hiệu chuẩn, không phải train để deploy.
[Kết quả và phạm vi kiểm ngày 04/11](../../docs/NINO_REAL_COLLECTION_WIZARD_AND_TD3_SMOKE_2026-11-04.md).

### TD3 trên factory Gazebo

Nút **FACTORY · TD3 + Nino + wheel PI · 128 bước** là job riêng, không cần
chạy hoặc tiếp tục checkpoint fixture. Nó dùng `factory_floor_mixed.sdf`, mô
hình Nino có caster, 48 bước kiểm tích hợp rồi 128 bước học TD3 mới. Giữ log,
checkpoint, replay, raw IMU/encoder/drive/GT và contact chỉ làm nhãn/audit.
Chọn dòng FACTORY trong bảng kết quả để đọc thông số của lượt đã chạy.

Job này chạy trên laptop với ROS/Gazebo cục bộ, không SSH hoặc phát lệnh tới Pi.
Phải có workspace ROS đã build, hoặc đặt `NINO_SIM_INSTALL` tới bản install
đã kiểm. Nó không mở train nghiên cứu dài, không kiểm tất cả route/vật cản
và không chứng minh lợi ích trên robot thật. [Báo cáo factory smoke](../../docs/NINO_FACTORY_TD3_SMOKE_2026-11-04.md).

## Vận hành và provenance

Collector hiện dùng **firmware RC AUTO đang có**. Tab Authority nâng cao là
nhánh firmware khác; không dùng nó để giả trạng thái RC hoặc bypass arbiter.
Không flash hoặc thu một phiên thật nào trong lần sửa GUI này.

- Journal laptop: `~/.local/state/nino/collection_gui/`.
- Runtime/log Pi: `~/nino_runtime/collection_guided_20261103_v2/gui_jobs/`.
- Raw tải về: `~/nino_real_data_imports/…`; video trên điện thoại không tự có trong bag.
- Bundle runtime giữ nguyên; hash khác cùng namespace bị từ chối, không xóa thư mục để thử lại.
- Sensor wrappers kiểm hash, không launch trùng cổng; driver có sẵn được giữ khi GUI đóng.
