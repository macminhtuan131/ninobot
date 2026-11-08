# Chuẩn hóa TD3 Parameter System, Causal Data Pipeline & Real Data Studio — 08/11/2026

Tài liệu này ghi nhận đợt nâng cấp kiến trúc phần mềm ngày **08/11/2026** dựa trên báo cáo đặc tả kỹ thuật **"Chuẩn hóa TD3 và GUI thu thập dữ liệu"**, đồng thời bảo toàn tuyệt đối toàn bộ bằng chứng lịch sử đã niêm phong SHA256 (`source_fingerprint = f1a97c385059bcdc8da2de4c7992e2ff79ff0db12734d2049246bab072a18907`) và quy tắc bất biến `hardware_authority = 0`.

---

## 1. Đối chiếu đặc tả báo cáo và các nâng cấp đã thực hiện

| Hạng mục trong báo cáo | Triển khai trong codebase (08/11/2026) | Bảo vệ khoa học / giới hạn trung thực |
|---|---|---|
| **1. TD3 Parameter System & Thứ tự tune 4 bước** | Bổ sung `src/nino_rl/config/td3_experiment_matrix_v1.yaml` và `src/nino_rl/nino_rl/td3_experiment_matrix.py` (`evaluate_tuning_readiness`, `check_profile_within_bounds`). Tích hợp kiểm tra biên tham số và tab quản trị ngay trong `TD3ParameterPanel`. | Khóa cứng thứ tự `Contract → Dynamics/SysID → Reward/Termination → Hyperparameters`. Không cho phép tune hyperparameter che lấp sai lệch mô hình vật lý; giữ nguyên `td3_parameter_profiles.yaml` đã seal. |
| **2. Giao thức Observation / Action nhân quả (10 Hz)** | Bổ sung `src/nino_pi/nino_pi/causal_alignment.py` (`align_causal_frames`, `compute_normalization_stats`, `apply_frozen_normalization`). | Chỉ lấy mẫu có `bag_time_ns <= tick_time_ns` (không nhìn tương lai); kênh thiếu/trễ `>0.25 s` gắn cờ `*_present = False` và giữ `None` (tuyệt đối không điền `0.0`); chuẩn hóa chỉ tính từ `train` split. |
| **3. Reward đa mục tiêu & tách `terminated` / `truncated`** | Quy định rõ trong `reward_contract` của `td3_experiment_matrix_v1.yaml` (tracking `v, ω`, `||a||^2`, `||Δa||^2`, safety/projection penalty; tách `terminated` với `truncated` kèm `reason`). | Không thay đổi hàm reward của các run lịch sử đã đóng (20k/30k common TD3). |
| **4. Ma trận thực nghiệm E1–E3 & chọn checkpoint** | `select_best_checkpoint`, `summarize_experiment_arm`, `compare_experiment_arms` trong `td3_experiment_matrix.py`. | Cấm chọn checkpoint chỉ theo `training_reward`; bắt buộc `>= 3 seeds`, `>= 20 episodes/seed`, tính `mean / std / CI95` và kiểm tra hồi quy jerk, overshoot, safety so với Classical đã tune công bằng. |
| **5. Pipeline `MCAP → Dataset` & chia tập theo phiên** | Nâng cấp `src/nino_pi/nino_pi/dataset_exporter.py` xuất song song `messages.parquet` (raw long-form) + `causal_frames.parquet` + `causal_manifest.json` (kèm `causal_schema_sha256`). Bổ sung `assign_grouped_splits`. | Chia `train / validation / test` theo nguyên phiên (`session_id`), ghim kịch bản `heldout` vào `test` để chống rò rỉ khung hình liền kề; phiên teleop/observer luôn giữ `td3_replay_eligible = False`. |
| **6. Real Data Studio GUI** | Nâng cấp `src/nino_pi/nino_pi/studio_panel.py` và `src/nino_pi/nino_pi/td3_parameter_panel.py`. | Thêm thanh trạng thái State Machine rõ ràng, hướng dẫn theo từng kịch bản, tóm tắt cửa sổ `h1/h5/h8` và chuỗi lệnh. Giữ `PyQt5` đồng nhất toàn app và nút `Dừng ghi · KHÔNG dừng robot` tách rời hoàn toàn khỏi motor. |
| **7. Automated QC (`qc_report.json`)** | Nâng cấp `src/nino_pi/nino_pi/studio_quality.py` (tự thân với stdlib + `.bag_io` để chạy cả trên Pi observer bundle và laptop). | Bổ sung đo độ lệch/trôi đồng hồ sender–receiver (`clock_drift_span_ms`), đếm khoảng trống `> 2x` chu kỳ trung vị, kiểm tra nhất quán chuỗi lệnh (`upstream_nonzero` so với `/cmd_vel` và `CollisionMonitorState` STOP), kiểm `annotations.json` và cửa sổ nhân quả `h1/h5/h8`. Giữ trần `WARN/Q2` khi chưa có ground-truth thân xe độc lập. |
| **8. 7 Cổng an toàn triển khai (Deployment Safety Gates)** | `evaluate_deployment_gates` trong `td3_experiment_matrix.py` + bảng kiểm trực quan trong `TD3ParameterPanel`. | Mọi thiếu sót ở bất kỳ cổng nào đều trả về `BLOCKED`; kể cả khi đủ 7 cổng phần mềm, `hardware_authority` vẫn giữ `0` chờ phê duyệt vận hành trực tiếp của con người. |

---

## 2. Dòng lệnh kiểm tra nhanh

```bash
# Kiểm định schema ma trận thực nghiệm E1-E3 và 7 cổng an toàn
PYTHONPATH=src/nino_rl python3 -m nino_rl.td3_experiment_matrix validate

# Kiểm tra profile TD3 so với biên tham số khuyến nghị
PYTHONPATH=src/nino_rl python3 -m nino_rl.td3_experiment_matrix check-profile nino_td3_research_h5_v1
```
