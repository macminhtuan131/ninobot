# Dọn dữ liệu episode mô phỏng — 08/11/2026

## Đã thực hiện

Theo yêu cầu giữ checkpoint cần thiết và xóa episode tốn dung lượng, đã dọn
hai job common103 hoàn tất. Không mở lượt train/evaluation/Gazebo mới.

| Job trong `~/nino_research/td3_studio/` | Episode train đã dọn raw | Dung lượng file đã xóa | Checkpoint giữ lại |
|---|---:|---:|---|
| `20261107T054154365880Z_common_train` | 143 | 4,440 GiB | 20k final |
| `20261107T080414816378Z_common_train` | 72 | 2,317 GiB | 25k periodic, 30k final |

Tổng **7.254.631.395 byte ≈ 6,76 GiB**. Con số của job đầu gồm ba bundle
periodic 5k/10k/15k đã được thay bằng các mốc cần cho review hiện tại.
Hai job từ khoảng 8,2 GiB còn khoảng 1,36 GiB. Dung lượng trống tăng từ
khoảng 1,40 lên 8,17 GiB tại thời điểm dọn; có thể thay đổi theo hoạt động máy.

Đã giữ nguyên:

- Ba checkpoint 20k/25k/30k: `model.zip`, `replay_buffer.pkl`, identity,
  metadata và manifest bundle. Không chỉ giữ actor weights.
- TensorBoard, evaluation đầy đủ, kết quả, cấu hình, provenance và manifest gốc.
- `environment_trace.jsonl`, `training_trace.jsonl`, reset metadata cấp job
  và `episodes/lifecycle.json`. Giữ đủ transition/outcome để xem lịch sử,
  kể cả episode thất bại hoặc đoạn cuối bị cắt giữa chừng.
- Dữ liệu robot thật và các thí nghiệm khác.

## Kiểm chứng sau dọn

- **587 file giữ lại** khớp SHA256 trong manifest gốc; toàn bộ 4.745 file
  đã xóa được ghi trong biên bản riêng. Không sửa manifest gốc.
- Ba bundle checkpoint đạt kiểm file/hash và tương thích runtime ML hiện tại.
  Không thực hiện resume/optimizer step để kiểm tra.
- Dashboard đọc đủ 20.000 + 10.000 transition; vẫn thấy 143 + 72 episode,
  trong đó 142 + 71 episode hoàn chỉnh và hai đoạn cuối bị cắt.
- Hai job vẫn có 6 kết quả evaluation/job. Các nguồn engine đã đóng băng
  và kết luận scientific assessment không thay đổi.
- **40 software tests đạt** cho retention, training panel, dashboard và tích
  hợp Studio; build `nino_pi` đạt. Đây không phải lượt thử robot/simulation.

Mỗi job có `storage_retention.json` ghi chính xác file đã xóa, kích thước,
hash được ghi trước đây trong manifest và checkpoint giữ lại. Không gọi
hash từ hồ sơ cũ là hash vừa tính lại của các file đã xóa.

**Giới hạn:** archive không còn đủ raw train episode để kiểm lại toàn bộ
manifest/measurement audit gốc. Không thể khôi phục raw đã xóa từ checkpoint.
Dashboard ghi rõ việc dọn có chủ đích; kết quả được giữ không trở thành một
phép audit raw mới. Các thống kê vẫn bao gồm toàn bộ episode, không chọn bỏ
episode có kết quả xấu.

## Chính sách cho các job sau

Tab **Train TD3 · Sim** mặc định bật **Tiết kiệm ổ đĩa**:

1. Train và evaluation hoàn tất như trước, ghi manifest, đóng worker.
2. Worker dọn nền lấy cùng khóa simulator, kiểm hash các đầu vào giữ lại.
3. Chỉ xóa `episodes/episode_N/` thuộc job common đã hoàn tất thành công.
4. Giữ mọi checkpoint theo khoảng lưu người dùng chọn, replay, TensorBoard,
   evaluation, trace và thống kê. Không tự cắt checkpoint của job tương lai.
5. Ghi biên bản dọn; báo lỗi nếu bị chặn. Phiên lỗi/cancel, legacy, worker
   ngoài GUI và dữ liệu thật không tự dọn.

Trong tab **Phiên đã chạy / checkpoints**, nút **Xóa raw episode train của
phiên đang xem** cho phép dọn một job common đã hoàn tất. Công cụ CLI
`nino_pi.training_storage` mặc định chỉ lập kế hoạch; cần `--apply` mới xóa.

Chính sách này **dọn sau job**, chưa giảm dung lượng cực đại khi train đang
chạy. Kiểm ngân sách disk đầu job giữ nguyên. Chưa thay observation, reward,
hyperparameter, contract, ngân sách hoặc quyết định release thí nghiệm.

## Hồ sơ

Artifact ở workspace người dùng:
`artifacts/sim_storage_cleanup_2026-11-08/` gồm kế hoạch, bản sao biên bản,
`cleanup_summary.json`, `verification.json`, test XML, build log và kiểm GUI.

Hướng dẫn vận hành: [TD3_TRAINING_GUI.md](../src/nino_pi/TD3_TRAINING_GUI.md).
