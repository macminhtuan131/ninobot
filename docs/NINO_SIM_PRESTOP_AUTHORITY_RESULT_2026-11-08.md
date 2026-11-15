# Kết quả Thực nghiệm Gazebo: Quyền tác động Pha dừng (`Pre-Stop Tail Authority`) & Chốt Baseline Cổ điển Sàn sạch

- **Ngày thực thi:** `2026-11-08`
- **Protocol runtime:** [`prestop_authority_runner.py`](file:///home/tuanmac/ninorobot/src/nino_rl/nino_rl/prestop_authority_runner.py) (`nino_prestop_tail_authority_runtime_v1_2026_11_08`)
- **Draft gốc:** [`prestop_tail_authority_draft_v1.json`](file:///home/tuanmac/ninorobot/src/nino_rl/config/prestop_tail_authority_draft_v1.json) (`nino_prestop_tail_authority_draft_v1_2026_11_08`)
- **Artifact Gazebo gốc (bất biến):** `/home/tuanmac/nino_research/sim_prestop_tail_authority_v1/20261108T142512790927Z_sim-prestop-tail-authority` (`raw_manifest_sha256 = ce4bdafb2e1edb03d60e0cdfbf224f38a96d81dcd62ffdb4b643d551516dabc1`)
- **Báo cáo đối sánh hậu kiểm (0 lượt Gazebo bổ sung):** `/home/tuanmac/nino_research/sim_prestop_tail_authority_v1/posthoc_evaluation_result.json`
- **Ngân sách tiêu thụ:** `12/12` lượt khởi chạy Gazebo (`1,680/1,680` decision ticks), `0` bước huấn luyện TD3, `0` cập nhật optimizer, `0` tác động phần cứng (`hardware_actions = 0`).

---

## 1. Mục tiêu và Thiết kế Thử nghiệm

Kiểm chứng xem một lượng bù vận tốc chung có biên hẹp ($\pm 0.005\text{ m/s}$) trong cửa sổ `0.5 s` ngay trước thời điểm nguồn dừng (`[stop - 0.5 s, stop)`) trên kịch bản sàn sạch `clear_box` (với wheel PI giữ nguyên `Ki = 0.10`) có tạo ra đáp ứng vật lý rõ rệt trên bánh xe/thân robot và giảm tích phân bình phương sai số vận tốc `ISE_v` trên cửa sổ chính `[stop - 0.5 s, stop + 2.5 s)` hay không:

- **`Tail0` (`tail_scalar = 0`):** Đóng cửa sổ tại `stop - 0.5 s` (`0.0 m/s`), khớp **từng bit** với `Classical_scheduled` đóng băng trên toàn bộ `140` ticks cho cả `stop = 6.0 s` và `stop = 8.0 s` (`classical_parity_exact = true`).
- **`Tail-` (`tail_scalar = -1`):** Giảm trước tham chiếu `-0.005 m/s` trong `[stop - 0.5 s, stop)` (tương đương phanh sớm nhẹ trước khi nguồn về `0`).
- **`Tail+` (`tail_scalar = +1`):** Đẩy thêm `+0.005 m/s` trong `[stop - 0.5 s, stop)`.

---

## 2. Kết quả Đo lường trên 12 Lượt Gazebo (`P01..P12`)

Cả `12/12` lượt đạt task/stop và chẩn đoán thời gian đã khai báo; đây không phải toàn bộ gate go/no-go (`functional_proposal_pass = true`, `timestamp_diagnostic.valid = true`, `task_success = true`, `stop_completed = true`).

### 2.1. Tổng hợp theo Từng Lượt (`140` ticks / lượt)

| Cell | Block | Stop (s) | Nhánh | `ISE_v` Native ($\text{mm}^2/\text{s}$) | `ISE_v` GT20ms ($\text{mm}^2/\text{s}$) | `ISE_v` GT+10ms ($\text{mm}^2/\text{s}$) | Window `vRMSE` (mm/s) | Full-14s `vRMSE` (mm/s) | Quiet Onset (s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `P01` | 0 | 6.0 | `Tail0` (`0`) | `67.37` | `162.69` | `162.69` | `4.739` | `3.786` | `2.00` |
| `P03` | 0 | 6.0 | **`Tail-` (`-1`)** | **`54.26`** | **`82.40`** | **`82.36`** | **`4.253`** | **`3.656`** | **`1.90`** |
| `P02` | 0 | 6.0 | `Tail+` (`+1`) | `213.37` | `417.37` | `417.33` | `8.433` | `5.035` | `2.00` |
| `P12` | 1 | 6.0 | `Tail0` (`0`) | `72.32` | `185.32` | `185.30` | `4.910` | `3.831` | `2.00` |
| `P10` | 1 | 6.0 | **`Tail-` (`-1`)** | **`57.10`** | **`87.59`** | **`87.56`** | **`4.363`** | **`3.747`** | **`1.90`** |
| `P11` | 1 | 6.0 | `Tail+` (`+1`) | `209.05` | `402.16` | `402.11` | `8.348` | `5.012` | `2.00` |
| `P05` | 0 | 8.0 | `Tail0` (`0`) | `95.52` | `194.20` | `194.20` | `5.643` | `4.134` | `2.00` |
| `P04` | 0 | 8.0 | **`Tail-` (`-1`)** | **`38.90`** | **`83.34`** | **`83.34`** | **`3.601`** | **`3.455`** | **`1.90`** |
| `P06` | 0 | 8.0 | `Tail+` (`+1`) | `248.47` | `431.86` | `431.86` | `9.101` | `5.238` | `2.00` |
| `P08` | 1 | 8.0 | `Tail0` (`0`) | `75.53` | `182.33` | `182.33` | `5.018` | `3.897` | `2.00` |
| `P09` | 1 | 8.0 | **`Tail-` (`-1`)** | **`40.98`** | **`79.26`** | **`79.26`** | **`3.696`** | **`3.557`** | **`1.90`** |
| `P07` | 1 | 8.0 | `Tail+` (`+1`) | `231.42` | `429.84` | `429.76` | `8.783` | `5.195` | `2.00` |

### 2.2. Đối sánh Cặp Nội khối (`Tail-` và `Tail+` so với `Tail0`)

| Cặp so sánh | $\Delta\%\text{ ISE}_v$ Native | $\Delta\%\text{ ISE}_v$ GT20ms | $\Delta\%\text{ ISE}_v$ GT+10ms | Chuỗi tương phản thân (`ticks`) | $\Delta\%\text{ Full vRMSE}$ | $\Delta\text{ Quiet Onset}$ (s) | Approach RMS Diff (mm/s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`Tail-` · B0 · 6s** (`P03/P01`) | **`-19.46%`** | **`-49.36%`** | **`-49.38%`** | `25` ticks âm liên tiếp | **`-3.43%`** | **`-0.10`** | `1.048` (> `1.000`) |
| **`Tail-` · B1 · 6s** (`P10/P12`) | **`-21.06%`** | **`-52.74%`** | **`-52.75%`** | `26` ticks âm liên tiếp | **`-2.20%`** | **`-0.10`** | `0.543` (Đạt) |
| **`Tail-` · B0 · 8s** (`P04/P05`) | **`-59.27%`** | **`-57.09%`** | **`-57.09%`** | `25` ticks âm liên tiếp | **`-16.43%`** | **`-0.10`** | `1.244` (> `1.000`) |
| **`Tail-` · B1 · 8s** (`P09/P08`) | **`-45.74%`** | **`-56.53%`** | **`-56.53%`** | `25` ticks âm liên tiếp | **`-8.75%`** | **`-0.10`** | `0.468` (Đạt) |
| `Tail+` · TB 6s | `+202.89%` | `+136.78%` | `+136.76%` | `25–26` ticks dương | `+30.8%..+33.0%` | `0.00` | `0.665..1.017` |
| `Tail+` · TB 8s | `+183.26%` | `+129.06%` | `+129.04%` | `25–26` ticks dương | `+26.7%..+33.3%` | `0.00` | `0.491..1.199` |

---

## 3. Phán quyết Khoa học & Minh bạch Hậu kiểm

1. **Phán quyết theo protocol:** `unknown_preintervention_approach_caliper_exceeded`.
   - **Lý do chính xác:** Ở `Block 1` (`P10/P12` và `P09/P08`), độ lệch chuẩn vận tốc thân trước can thiệp (`[stop - 1.5 s, stop - 0.5 s)`) chỉ là `0.543 mm/s` và `0.468 mm/s` (nằm gọn trong caliper `1.000 mm/s`). Tuy nhiên ở `Block 0` (`P03/P01` và `P04/P05`), dao động tự nhiên giữa hai lần khởi chạy Gazebo độc lập đạt `1.048 mm/s` và `1.244 mm/s` (vượt ngưỡng cứng `1.000 mm/s` một lượng `0.05–0.24 mm/s`). Theo đúng quy tắc khắt khe của [`prestop_tail_authority_draft_v1.json`](file:///home/tuanmac/ninorobot/src/nino_rl/config/prestop_tail_authority_draft_v1.json), bộ so sánh không gán nhãn nhân quả tuyệt đối khi hai nhánh khởi chạy tươi lệch nhau quá `1.0 mm/s` trước thời điểm tác động.
   - **Ghi chú minh bạch hậu kiểm:** Trong lần chạy đầu tiên, bộ hậu xử lý dừng ở hàm `compare()` sau khi đã hoàn tất và lưu nguyên vẹn `12/12` lượt Gazebo do so sánh `==` dấu phẩy động trên `accepted_v_m_s` (có chứa thành phần chiếu góc lái vòng kín `v_source * cos(yaw_error)` lệch tối đa `3.65e-5 m/s` = `0.037 mm/s` tại tick `24`), trong khi lệnh yêu cầu `requested` và chiếu cửa sổ `windowed_common_m_s` trước cửa sổ dừng khớp **tuyệt đối `0.0`** trên mọi tick. Thư mục gốc được giữ bất biến 100% (`manifest.json` không chạm), và hàm [`finalize_posthoc_comparison`](file:///home/tuanmac/ninorobot/src/nino_rl/nino_rl/prestop_authority_runner.py#L1049-L1097) xác minh toàn bộ mã băm SHA-256 trước khi xuất `posthoc_evaluation_result.json` với `0` lượt Gazebo bổ sung.

2. **Mô tả các trajectory đã ghi; không thay thế verdict unknown:**
   - Tín hiệu đáp ứng của `Tail-` (`-0.005 m/s` trong `0.5 s` cuối trước khi dừng) đạt biên độ thân **`8.39 – 9.91 mm/s`** suốt **`25–26` ticks liên tiếp** (lớn hơn khác biệt trước can thiệp đã ghi; chưa nhận dạng được nhiễu độc lập), kéo giảm `ISE_v` cửa sổ dừng **`-19.5%` đến `-59.3%`** trên Native và **`-49.4%` đến `-57.1%`** trên GT20ms/GT+10ms ở **cả 4 cặp**, đồng thời rút ngắn thời gian xác lập đứng yên thêm `0.10 s` (`1.90 s` so với `2.00 s`) và hạ `Full-14s vRMSE` xuống **`3.455 – 3.747 mm/s`** ngay cả khi giữ `Ki = 0.10`.
   - Ngược lại, `Tail+` (`+0.005 m/s`) làm vọt lố vận tốc khi dừng và đẩy `ISE_v` tăng gấp `2.3× – 3.1×`.

---

## 4. Kết luận sau rà soát độc lập

- **Giữ verdict `unknown_preintervention_approach_caliper_exceeded`.** Hai block có khác biệt trước can thiệp vượt caliper; không nới ngưỡng sau kết quả hoặc coi tỷ lệ tín hiệu/khác biệt ban đầu là bằng chứng nhân quả thay thế. Các số đo ở bảng trên là mô tả, không phải xác nhận candidate đã qua gate.
- `Tail-` có tín hiệu mô tả đáng khảo sát; không promote và không ghép nó với `Ki=0.15` như một controller đã kiểm. Screen tail giữ `Ki=0.10`; thử Ki là thí nghiệm khác.
- Sai số khoảng 3,5 mm/s không chứng minh “noise floor” của Gazebo, không chứng minh classical đã tối ưu triệt để. Chưa có phép phân rã nhiễu/độ phân giải/model discrepancy để kết luận đó.
- `ISE_v` có đơn vị **m²/s**, không phải joule hoặc năng lượng tiếp xúc. Quiet-onset chênh 0,1 s là một native tick, cần giữ giới hạn độ phân giải khi diễn giải.
- Giữ classical làm baseline sàn sạch với phạm vi đã thử. `Ki=0.15` là candidate có bằng chứng mô tả tốt hơn tại hai lịch dừng, cần chốt contract riêng trước so sánh mới; không sửa baseline đóng băng của v1.
- Gờ cứng 6 mm/DR là **ứng viên benchmark mới**, chưa chứng minh baseline cổ điển thất bại hoặc TD3 cần thiết. Chưa có đối chứng obstacle với classical đã tune và chưa có chứng cứ đủ cho campaign 3×50k từ screen sàn sạch này.

Xem [đánh giá dự án và các bước tiếp](NINO_PROJECT_REASSESSMENT_2026-11-08.md). Raw manifest, state failed của batch gốc và báo cáo posthoc được giữ nguyên; chỉ phần diễn giải tài liệu này được sửa.
