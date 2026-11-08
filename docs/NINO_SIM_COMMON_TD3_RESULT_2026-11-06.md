# Kết quả partial: fresh TD3 common-only103D/1D

06/11/2026 · protocol/execution05/11 · **Đợt đóng do thiếu feedback ở biên**.
Không retry, không bắt đầu seed22/33, không chạy evaluation hoặc hardware.

## Quyết định

Trainer mới đã tạo và thực sự học bằng TD3 qua wrapper103D/1D trong Gazebo.
Tuy nhiên **pilot chưa hoàn thành**: thiếu joint support tại tick warmup của
launch thứ6. Giữ raw/model/replay, dừng ngân sách còn lại. Chưa có đối chứng
frozen-policy để kết luận learned benefit, hội tụ hoặc generalization.

Tiếp theo phân biệt source/DDS/consumer; không sửa reward/gain/current,
không hạ gate40ms, không train dài để vượt qua lần lỗi đo này.

## Đã triển khai

- Module `residual_common_td3.py`, YAML/script riêng, không sửa scientific
  parent103D/1D hoặc các runner V3/Studio. Scalar/common±0,005m/s, shared
  preview/window, yaw follower và reward vật lý giữ nguyên.
- Learner identity mới pin parent/ABI/config; fresh head zero +target sync,
  seed riêng; không load V3/Studio/inspection checkpoint vào trainer mới.
- Lịch6/8s được đổi đồng thời ở backend source, task/scorer và adapter preview
  trước reset. Model/targets/critics/optimizer/replay riêng từng seed.
- Kiểm mỗi transition trước khi trả về SB3: action/history/clock, gate,
  nominal/reward parity và feasibility; preserve request trước projection.
- GUI profile **TD3 common103D/1D ·3seed×1024 +10eval**, nút chạy thực sự dùng
  QProcess/worker. TRAIN TD3 tự do100D/2D là nhánh lịch sử riêng.
- GUI hiện partial/error, bảng5training episodes và review/hash; không gắn
  failed batch thành “đạt” hoặc coi checkpoint partial được promote.

## Budget và số thực thi

| Đại lượng | Kế hoạch tối đa | Thực tế |
|---|---:|---:|
| Training seeds | 11/22/33 | chỉ11 bắt đầu, chưa seed nào đủ budget |
| Train transitions | 3.072 | **700** |
| Critic gradient updates | 960/seed đủ1.024 | **636** |
| Actor optimizer updates | theo policy_delay2 | **318** |
| Replay rows | theo train transitions | **700**, obs103/request1D/nextobs103 |
| Full training episodes | 7/seed +44tick cắt phải | **5**, cả5task/stop đạt |
| Fresh Gazebo launches | 34(train24+eval10) | **6** |
| Evaluation launches/transitions | 10/1.400 | **0/0** |
| Hardware/real data mới | 0 | **0** |

Phần bước đầu của episode6 tiến physics50ms nhưng không tạo được complete
100ms transition; **không thêm nó vào700replay rows** hoặc gọi là terminal
thất bại của policy. Request/source khi đó vẫn zero, chưa tới forward.

1.461world multi_step requests đều ACK/completion đúng, retry0; tổng73.050
physics steps **trong các requests đã ghi**, bao gồm settling và half-tick
chưa hoàn chỉnh. Số này không bao gồm free-running startup hoặc pause-only
calls. Có12parameter readbacks,3.500causal estimator updates.

## Failure được xác minh

- Episode6 reset và0,5s continuous quiet settling đạt, resetinfo đã lưu.
- Request đầu tiên50physics steps: sim**2,651→2,701s**, đúng ACK/iterations.
- Wheel cuối stamp**2,651s**, age**50ms**; IMU/GT tới2,700s, drive2,688s.
- `_wait_feedback` đợi5wall seconds nhưng không có joint mới đủ gate40ms.
- Raw không cho biết chắc source broadcaster không publish, DDS mất mẫu
  hay consumer không nhận; không quy CPU/GC/ROS executor là nguyên nhân duy nhất.
- Inter-sample joint gap lớn nhất trong raw4ms **không chứng minh tail đủ**:
  không có mẫu mới cuối stream để thể hiện khoảng50ms qua `diff(stamps)`.

700complete transitions trước đó có boundary support lớn nhất**19ms**,
không privileged input vào guidance/actor;3500estimator updates đã kiểm
source stamp/receipt/support. Raw drive có gap tới175ms trên toàn launch,
không gọi capture loss-free hoặc dùng tuổi mẫu tại decision để xóa raw gap.

## Training episode diagnostics — không phải evaluation

| Episode(0-based) | Source stop(s) | Native nominal vRMSE(m/s) | PathRMSE(mm) | Task/stop |
|---|---:|---:|---:|---|
| 0 | 6 | 0,0052172 | 0,03052 | đạt/đạt |
| 1 | 8 | 0,0053178 | 0,53471 | đạt/đạt |
| 2 | 6 | 0,0058737 | 0,02123 | đạt/đạt |
| 3 | 8 | 0,0071815 | 0,63067 | đạt/đạt |
| 4 | 6 | 0,0063305 | 0,02605 | đạt/đạt |

Policy đang thay đổi và có exploration; không so bảng này với evaluation
qualification cũ để suy TD3 tốt/xấu hơn B0/classical. 190active-window rows;
request histogram theo bins[-1;−0,6;−0,2;0,2;0,6;1] là[116;16;48;4;6].
Đây chỉ là coverage đã quan sát, không counterfactual action ranking.

## Artifacts và verification

Root: `/home/tuanmac/nino_research/sim_common_td3_v1`.
Artifact: `20261105T123511017013Z_sim-common-td3`.
Giữ `seed_11/partial_model_failed.zip`, `partial_replay_failed.pkl`, full
trace/raw/resets/world logs, protocol và manifest.700replay rows khớp cả
observation/action/reward/done/timeout; đủ5terminal task, không vá missing.

Fingerprint learner source/config/script:
`bba204f885daf0d93c74b870842e757c89684188d83d4545c3ece70e11f326da`.
ABI103D/1D:
`b8c71ccb876cb6f2f5ab66d08d74d9b3d8cfdbfac22ccfc3b326da16b5a2e6e0`.

77artifact hashes +113source files trước chạy được kiểm. Scientific code/
config/scripts giữ nguyên sau sealed failure; GUI/metadata/report được cập
nhật để hiển thị partial.48software/GUI tests đạt; không phải48rollouts.
Chi tiết build/install/GUI/hash ở
`NINO_SIM_COMMON_TD3_VERIFICATION_2026-11-06.json` sau verification cuối.

## Một việc tiếp theo

Theo [draft diagnostic](NINO_SIM_JOINT_BOUNDARY_DIAGNOSTIC_NEXT_2026-11-06.md),
chuẩn bị observer joint độc lập và kiểm endpoint support trên zero-only
protocol mới. Draft chưa chạy/release; đợt TD3 này đóng. Chỉ đổi khuyến nghị
khi có bằng chứng phân biệt source/delivery/consumer và một correction đã
qua readiness riêng. Không mở lại2seed/10eval hoặc resume partial âm thầm.
