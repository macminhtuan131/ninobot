# Coverage V2 — kết quả triển khai và preflight

> **Cập nhật sau preflight:** V2 đã release/chạy và đóng; tổng1.864valid train
> transitions,0eval. Source/manifest của preflight vẫn giữ nguyên. Xem
> [kết quả study](NINO_SIM_COVERAGE_V2_RESULT_2026-11-06.md).
> Nội dung dưới là kết quả readiness phần mềm trước physics.

06/11/2026 · **Software readiness đạt; physics chưa release.**

## Đã làm

1. Tạo runner/config/protocol/script/root V2 riêng; giữ fingerprint worker V1
   `1cd68b11dea8aee0302094294d89636276df23d6dfc2dc314af1c4a6433d89be`.
   Artifact thất bại V1 và 63 slot đóng được giữ nguyên.
2. Nối adapter metadata vào đường `train_learner` thực sự dùng. Metadata từ
   source plan tới validator trước khi transition vào replay. Controller,
   history, projection, reward, feasibility và physics contract không đổi.
3. Kiểm cả hai arm đủ 1.024 bước **synthetic**: 8 reset stop6/8, 7 terminal
   và 44 bước cuối censored; 960 critic/480 actor updates mỗi arm. Save/load
   và audit replay toàn bộ. Fault condition/clock giữ zero replay/update.
4. Thêm profile GUI V2: preflight, study có release gate, tiến độ/lỗi/kết quả;
   V1 còn trong lịch sử. Outline hiện rõ bước đã đạt và bước chưa mở.

## Bằng chứng kiểm tra

| Kiểm tra | Kết quả | Giới hạn |
|---|---|---|
| Nút GUI → QProcess → preflight worker → manifest | Đạt | Không Gazebo/SSH/robot |
| Preflight software suite | **80/80**, không skip | Bao gồm regression lịch sử, V2 và train-path synthetic |
| GUI regression | **54/54** | Không phải 54 lượt robot/simulation |
| Build | `nino_rl`, `nino_pi` đạt | Không chứng minh controller benefit |
| Preflight artifact | 7 file khớp hash | Không có sensor stream mới |
| Fixed critic packets | 20 từ B0 đã có | Diagnostic, không là counterfactual outcome |
| Nút study sau preflight | Khóa đúng | `released=false` |

Plant integration cân bằng hai bánh và có interface guidance/support synthetic;
terminal summary/diagnostic được thay bằng giả định có nhãn trong test. Validator
transition và feasibility thật không bị thay. Vì vậy kết quả chứng minh wiring,
reset và replay, **chưa chứng minh measurement/physics trong Gazebo**.

## Provenance

- Root: `/home/tuanmac/nino_research/sim_coverage_study_v2`.
- Preflight: `20261106T110945763777Z_sim-coverage-v2-preflight`.
- Implementation fingerprint:
  `57dc776c83cf8ef3de6830423f27577b80299b089a628a3c9404d54d9f7894fe`.
- Preflight manifest SHA256:
  `0c8f324a5c60e5c23489279975941212cb4e2a4ce13cd206771e76b01a7b4280`.
- GUI/test/build log và ảnh tại workspace artifact
  `artifacts/sim_coverage_v2_2026-11-06/` (ngoài root source repo).
- Release overlay đã điền hai pin trên, review rule nghiên cứu giữ nguyên;
  **released=false**, hardware=false. Đây chưa là cấp ngân sách physics.

Không cộng số optimizer updates của fixture thành training nghiên cứu. V2 có
**0 scientific training transitions, 0 physics ticks, 0 eval mới, 0 hardware**.
Real data cutoff vẫn 02/11. Kết quả eval cũ vẫn cho classical tốt hơn 6/6 điều
kiện TD3 trên native và hai grids; chưa có bằng chứng TD3 cải thiện hệ thống.

## Việc tiếp theo

Chốt release riêng theo [protocol V2](NINO_SIM_COVERAGE_V2_PROTOCOL_2026-11-06.md)
trước physics: tối đa 6.144 train +2.240 eval, 64 launches, 0 retry/extra smoke.
First episode là integration check **trong** budget. Failure đóng phần còn lại.
Không mở lại V1, tăng training horizon, sửa gain/reward/QoS hoặc cần thêm real
data để xử lý lỗi trace đã sửa. Primary/grids/constraints và rule unknown/no-go
giữ nguyên; chưa deployment hoặc generalization.
