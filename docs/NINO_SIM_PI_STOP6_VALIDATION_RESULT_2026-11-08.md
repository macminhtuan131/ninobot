# Kết quả Sim — Kiểm chứng PI `Ki = 0,15` tại lịch dừng `6 s` (`clear_box`)

Ngày 08/11/2026. **Đã thực thi xong ngân sách cố định `4` lượt Gazebo (`560` native ticks), `0` bước train, `0` tác động phần cứng.**

- **Protocol:** `nino_pi_stop_validation_v1_2026_11_07` (`src/nino_rl/config/sim_pi_stop_validation_protocol_v1.json`)
- **Runner:** `src/nino_rl/nino_rl/pi_stop_validation_runner.py`
- **Release record (đã đóng sau chạy):** `src/nino_rl/config/pi_stop_validation_release_v1.json` (`released: false`, `allocated_physics_slots: 4`, `closed_status: "completed"`)
- **Artifact niêm phong:** `/home/tuanmac/nino_research/sim_pi_stop_validation_v1/20261108T130921052503Z_sim-pi-stop-validation`

## 1. Ma trận thực thi và tính toàn vẹn

Bốn lượt khởi chạy Gazebo độc lập (reset `drive_ack_and_physical_quiet_v1`, `gain = 1.0`, `arm = B0`, `source_stop_s = 6.0`, `140` ticks / lượt = `14,0 s`):

| Cell | Block | `Ki` | Steps | Native `vRMSE` (mm/s) | `GT20ms` `vRMSE` (mm/s) | `GT+10ms` `vRMSE` (mm/s) | Path RMSE (mm) | Quiet liên tục (s) | Task / Stop pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| `0` | `0` | `0.10` | `140` | `4.672` | `5.967` | `5.971` | `0.093` | `6.00` | Đạt |
| `1` | `0` | `0.15` | `140` | **`3.672`** | **`5.181`** | **`5.185`** | `0.123` | `6.00` | Đạt |
| `2` | `1` | `0.15` | `140` | **`4.185`** | **`6.238`** | **`6.242`** | `0.111` | `6.00` | Đạt |
| `3` | `1` | `0.10` | `140` | `4.722` | `6.253` | `6.257` | `0.101` | `6.00` | Đạt |

## 2. Đối chiếu cặp nội khối (`Ki = 0,15` so với `Ki = 0,10`)

- **Block 0 (`cell 1` vs `cell 0`):**
  - Native `vRMSE`: giảm **`-21,41%`** (`-1,000 mm/s`)
  - `GT20ms`: giảm **`-13,17%`** (`-0,786 mm/s`)
  - `GT+10ms`: giảm **`-13,17%`** (`-0,786 mm/s`)
  - `grid_sensitive = false`
- **Block 1 (`cell 2` vs `cell 3`):**
  - Native `vRMSE`: giảm **`-11,36%`** (`-0,536 mm/s`)
  - `GT20ms`: giảm **`-0,24%`** (`-0,015 mm/s`)
  - `GT+10ms`: giảm **`-0,24%`** (`-0,015 mm/s`)
  - `grid_sensitive = false`

## 3. Kết luận theo ngưỡng tiền khai báo

- **Verdict tự động của runner:** `descriptive_PI_stop6_validation_pass_baseline_review_required`.
- Cả ở `stop = 8 s` (screen trước đó: `-21,7% / -19,5%`) lẫn `stop = 6 s` (validation này: `-21,4% / -11,4%`), tăng tích phân bánh xe lên `Ki = 0,15` đều giảm mạnh sai số vận tốc native trên sàn sạch (`clear_box`), đồng chiều trên cả 2 lưới GT, sai số ngang `< 0,13 mm` (`<< 40 mm`), dừng yên liên tục `6,0 s` (`>= 2,0 s`), không phát sinh quá điều chỉnh dừng.
- **Giới hạn và quyết định:** Đây là screen mô tả nhỏ: ở block 1, GT RMSE chỉ giảm khoảng 0,24%, nên không gọi mức cải thiện là lớn và ổn định trên mọi grid. Giữ `Ki=0.15` là candidate cho baseline có phiên bản riêng; chưa chứng minh tối ưu toàn cục hoặc hiệu quả trên vật cản. Không ghép với Tail- thành một controller đã kiểm.
- **Ý nghĩa cho TD3:** Chưa cần train dài thêm chỉ để xử lý cùng sai số sàn sạch. Có thể khảo sát gờ cứng 6 mm bằng baseline/authority screen riêng; không suy từ kết quả sàn sạch rằng TD3 sẽ có lợi trên gờ hoặc phải cấp ngay 3×50k bước.
