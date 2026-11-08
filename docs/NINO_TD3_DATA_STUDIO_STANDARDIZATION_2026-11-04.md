> Cập nhật06/11: evaluation-only mới đã đóng, dùng ba checkpoint TD3 có sẵn; không train thêm. Xem [kết quả](../docs/NINO_SIM_RELIABLE_EVAL_ONLY_RESULT_2026-11-06.md) và [protocol](../docs/NINO_SIM_RELIABLE_EVAL_ONLY_PROTOCOL_2026-11-06.md). Chưa promote/hardware.

> Cập nhật06/11: pilot TD3 RELIABLE với lifecycle từng episode đã đóng; xem [kết quả](../docs/NINO_SIM_RELIABLE_TD3_RESULT_2026-11-06.md) và [protocol](../docs/NINO_SIM_RELIABLE_TD3_PROTOCOL_2026-11-06.md). Chưa promote hoặc mở training/hardware mới.

> **Cập nhật06/11 — candidate joint RELIABLE:** fixturepaired1000messages +1handshake/pause100ms đạtcompatibility, cảBE/RELIABLE1000/1000; candidateB0stop6/8 đạt2launches/280ticks. GUI hai nút cógate +QC/metric;khóa stageđãđóng. Chưa optimizerload/training hoặc rootcauseproof, partialTD3700ticks giữ. Tiếp learnerfresh103D/1D protocol riêng. [Kết quả](NINO_SIM_JOINT_RELIABILITY_RESULT_2026-11-06.md).

> **Cập nhật06/11 — joint diagnostic đã đóng2/2:**200zero ticks/612checks đủsupport; hai observer trùng15.220source stamps, payloadfield không lệch. Chưa tái hiện50ms, nguyênnhânunknown; khôngtraining/hardware hoặc reopenpartialTD3. GUI có profile và bảngage/parity/error. Tiếp tốiđa mộtcandidateQoSjointRELIABLE riêng, chưa áp/chạy. [Kết quả](NINO_SIM_JOINT_BOUNDARY_RESULT_2026-11-06.md).

> **Cập nhật06/11/2026 — TD3 common103D/1D đã train partial:**700ticks/636critic +318actor updates,5training episodes đạt task/stop. Episode6 thiếu joint support50ms tại half-tick zero; batch đóng, seed22/33 +10eval chưa chạy. GUI có profile riêng và partial/error review, khóa retry. Chưa có learned-benefit comparison hoặc hardware. Xem [kết quả](NINO_SIM_COMMON_TD3_RESULT_2026-11-06.md).

> **05/11 — wrapper103D/1D đã đạt Gazebo:**4/4launches,560ticks,replay560rows,actor/optimizer0. [Kết quả](NINO_SIM_EQUAL_GAZEBO_RESULT_2026-11-05.md). Bước tiếp: fresh TD3 common-only pilot theo draft mới; chưa train hoặc resume V3.

> **05/11 — contract cùng preview đã đạt offline:**103D/1D common-only, shared window và requested replay;840bước fixture tổng hợp,optimizer/Gazebo0. Không resume V3. [Kết quả](NINO_SIM_EQUAL_INFORMATION_RESULT_2026-11-05.md). Bước tiếp: kiểm wrapper mới trong Gazebo theo protocol riêng, chưa chạy.

> **05/11 — stop-time transfer đã xong:** 6/6 lượt,840ticks,actor/optimizer0. Common cổ điển có RMSE v thấp hơn cả3 B0 trên native và hai GT-header grids; giữ candidate, chưa promote. [Kết quả](NINO_SIM_STOP_TRANSFER_RESULT_2026-11-05.md). Tiếp: contract TD3/cổ điển cùng thông tin, chưa mở train mới.

> **05/11 — đối chứng common cổ điển đã xong:** 6/6 lượt,840 tick,optimizer0. Whole-task RMSE v thấp hơn B0/frozen common ở cả hai lượt; giữ candidate có planned stop, chưa promote. [Kết quả và bước tiếp](NINO_SIM_CLASSICAL_COMMON_RESULT_2026-11-05.md).

> **05/11 — frozen-axis ablation đã xong:** 6/6 lượt, 840 evaluation ticks, không optimizer. Bỏ residual vi sai giảm lệch đường, nhưng common-only vẫn tệ hơn B0 về RMSE vận tốc toàn lượt do pha hạ tốc. Giữ B0; [kết quả, GUI và đối chứng cổ điển kế tiếp](NINO_SIM_AXIS_ABLATION_RESULT_2026-11-05.md).

> **05/11 — TD3 V3 đã train và đánh giá:** guided baseline + zero-init + nominal reward; 512 train/496 updates, 8 eval. Tất cả marker/stop đạt, clear TD3 tracking tệ hơn B0; có một B0 gờ vượt gate được giữ. Chưa promote; [kết quả và hướng tiếp](NINO_SIM_GUIDED_TD3_V3_RESULT_2026-11-05.md).

> **05/11 — screen guided clear/gờ 6 mm đã xong:** 4/4 marker + stop, 560 transition, residual zero. Gờ RMSE path 3,09–4,28 mm; chưa train TD3 mới. GUI hiển thị từng lượt; [kết quả và contract V3 kế tiếp](NINO_SIM_GUIDED_CONTACT_RESULT_2026-11-05.md).

> **05/11 — V3 đã kiểm:** estimator wheel+IMU → follower → residual zero → PI đã chạy trong Gazebo. 8/8 marker + stop; RMSE path guided 13,09–13,84 mm, constant 93,06–93,65 mm. Không train thêm TD3. [Kết quả và bước tiếp](NINO_SIM_GUIDED_BASELINE_V3_RESULT_2026-11-05.md).


> **04/11 — ưu tiên nhánh sim theo yêu cầu mới:** B0 → TD3 h5 pilot có giới hạn → đánh giá, không cần đợi thu real data. Xem [protocol nhánh sim](NINO_SIM_BRANCH_PROTOCOL_2026-11-04.md). Các gate robot thật và calibration phía dưới là nhánh song song.

# Chuẩn hóa TD3 và Nino Real Data Studio — 04/11/2026

## Quyết định sau khi đối chiếu báo cáo với source

Ưu tiên dữ liệu có provenance và baseline/model đáng tin trước khi tune
hyperparameter hoặc tăng training. Báo cáo là đặc tả đề xuất, không phải kết
quả phần cứng, mức QC được chấp nhận hoặc cấp ngân sách thí nghiệm mới.

| Đề xuất | Đã áp dụng / giới hạn thực tế |
|---|---|
| Parameter System | Catalog YAML có phiên bản/hash, schema validator, GUI editor/draft, effective config + ABI; smoke giảm bậc và factory dùng cùng profile |
| Actor/critic LR | Hai trường rõ ràng; adapter SB3 hiện dùng chung schedule nên từ chối hai giá trị khác nhau, không giả vờ tune độc lập |
| History 8, 10 Hz | Thêm profile nghiên cứu h1/h5/h8; h5 hiện hành vẫn 100D, h8 160D/span 0,7 s. Chưa có kết quả train/ablation h8 |
| Observation mask / frozen train stats | Chưa triển khai ABI mới. Giữ physical normalization và reject/refill khi thiếu; validator từ chối lựa chọn chưa hỗ trợ |
| Action residual v/omega | Giữ common/differential wheel-linear residual đang triển khai rồi đổi sang body reference; không âm thầm đổi ngữ nghĩa replay/checkpoint. Projection/zero baseline/limits giữ nguyên |
| Hardware action scales | Chưa có envelope đã đo; giữ null trong profile và residual authority 0 |
| PySide6 desktop | Giữ PyQt5 của ứng dụng hiện có, tái sử dụng collector/audit. Không tạo một GUI/toolkit song song |
| GUI read-only | Studio là trang mặc định, không publisher điều khiển/driver launch/enable/AUTO. Commissioning cũ và authority motor nằm ở trang riêng, không phải recorder Studio |
| MCAP + JSON + Parquet | MCAP là lựa chọn mặc định mới; SQLite được chọn rõ ràng, lịch sử không chuyển đổi. Export bảng message Parquet có hash; chưa tạo feature/history hoặc replay TD3 |
| QC pass/warn/fail | Check riêng PASS/WARN/FAIL, mức raw tối đa Q2; tổng WARN khi coverage/execution/body/history còn unknown. Không áp 95% từ ví dụ |
| Session index | SQLite local sau fetch, hiển thị scenario/QC/path; index là derived, không sửa raw hoặc tự promote bằng chứng |

## Trạng thái dự án sau sửa

**Phần mềm:** có đường causal History/projection dùng chung, governor, TD3/PPO
fixture, portable actor, factory backend và GUI. Cập nhật này chuẩn hóa parameter
management và thêm acquisition observer thực sự gọi collector/rosbag2, không
chỉ đổi mockup. Các phần mới đã được kiểm bằng software/ROS synthetic fixtures.

**Mô phỏng:** factory smoke trước đã hoàn tất optimizer/replay/actor parity,
nhưng lượt mới nhất chỉ tiến khoảng 0,4 m và chưa qua C1. Giữ nguyên bằng
chứng/thất bại đó; không coi smoke thành contact benefit hoặc task success.
Cập nhật parameter loader làm source fingerprint đổi: các artifact cũ là lịch
sử, GUI không còn dùng chúng làm validation hiện hành. Không sửa hash của
artifact cũ và không tự chạy lại Gazebo/training nghiên cứu trong cập nhật này.

**Robot thật:** không SSH, không flash, không thu thêm hoặc phát lệnh motor
trong lượt sửa này. Inventory/sign/mounting và các pilot 02/11 giữ nguyên
trạng thái. Chưa có body-speed/slip reference độc lập đủ kiểm, model motor
đã hiệu chuẩn hoặc learned residual được phép chạy thật. MCAP/Studio mới
chưa được kiểm trên chính Pi; kiểm localhost không thay thế phép xác nhận đó.

## Các module chính

- `nino_rl/td3_config.py` + `config/td3_parameter_profiles.yaml`: validate,
  hash, config preparation và gate chống profile/hash/effective-kwargs lệch.
- `residual_workflow.py`, `residual_factory_workflow.py`: bỏ bộ TD3 smoke
  ghi rải rác, dùng catalog chung. Không đổi số bước của các job cố định.
- `studio_contract.py`: scenario, required/optional topics, metadata có
  protocol ID; chỉ mapping các interface đã đọc trong source hiện hành.
- `studio_telemetry.py`: subscriber observer, rate/receipt age; không thay
  raw recorder counts bằng observer counts.
- `studio_remote.py`: preflight, lifecycle, annotation, heartbeat/EOF/stop,
  gọi collector riêng process, chờ đóng rồi QC; không gọi motor/driver.
- `studio_transport.py`: cài bundle content-addressed không ghi đè namespace
  khác, SSH cố định domain 0/env hiện có, tải phiên đã đóng và kiểm lại hash.
- `bag_io.py`, `studio_quality.py`: đọc lại SQLite/MCAP CDR, metadata/count,
  source/receipt clock/gap, required/finite values, raw status/safety context.
- `dataset_exporter.py`: long-form Parquet, checksum/export identity, không
  nội suy hoặc điền missing thành zero, không biến teleop thành RL replay.
- `studio_runner.py`, `studio_panel.py`, `td3_parameter_panel.py`: Qt QProcess
  không khóa main thread; next action, telemetry, QC và profile preparation.

Hướng dẫn thao tác/file layout/QC chi tiết:
[REAL_DATA_STUDIO.md](../src/nino_pi/REAL_DATA_STUDIO.md).

## Điều còn thiếu có chủ đích

1. **Real runtime validation:** driver/Agent đã chạy, đúng graph/types/QoS;
   kiểm Studio preflight và phiên chỉ đọc phù hợp trên Pi. Không bắt thu lại
   IMU sign nếu không có câu hỏi mới.
2. **Claim command→wheel→body:** cần xem dữ liệu/video cũ có đủ chưa. Khi cần
   motion mới phải dùng protocol riêng; Studio không tạo trajectory hoặc slot.
   Final ROS command không phải actuator target/ACK.
3. **Causal feature export từ bag thật:** raw đã xuất được nhưng mapping
   baseline/previous accepted action/source ages còn cần review. Chưa có feature
   readiness thì không tạo `features.parquet` giả hoặc replay TD3.
4. **SysID / heldout:** dữ liệu có excitation, timestamp/geometry uncertainty
   và nhiều session độc lập; công cụ hiện có không nhận một phiên đứng yên
   làm calibration. Giữ real SysID, real evaluation và sim transitions riêng.
5. **Baseline/calibrated simulator:** giải thích chatter/body discrepancy của
   factory trước khi bỏ ngân sách train dài; chốt objective/constraints và
   minimum effect trước evaluation.
6. **Learning/deployment:** h1/h5/h8 và DR là experiment proposals. Chưa có
   learned benefit, compute/deadline Pi hay action envelope thì không mở real
   authority. Governor phải qua H2/H3 cho contact claim, không cộng logger
   progress thành governor progress.

## Outline tiếp theo và điểm dừng

| Thứ tự | Việc / artifact | Qua / dừng / unknown |
|---|---|---|
| 1 | Studio read-only trên Pi; closed raw + QC + import | Plugin/sensor thiếu thì giữ lỗi, chọn storage rõ hoặc sửa mapping; không tự chạy xe |
| 2 | Review command/wheel/body từ phiên phù hợp + reference | Chưa nhất quán hoặc thiếu sync/reference thì unknown; không mở repeatability tự động |
| 3 | SysID theo session + baseline/model holdout | Không đủ excitation/clock/model fit thì dừng claim và đề xuất protocol đo riêng |
| 4 | Benchmark B0/B1/Governor; chốt objective/budget | Classical đủ mục tiêu hoặc actuator không có useful authority thì đơn giản hóa/chuyển hướng |
| 5 | TD3 h1/h5/h8 và DR theo thiết kế giữ các yếu tố khác | So matched baseline, heldout, failures, nhiều learner seeds; không dựa return đẹp |
| 6 | Portable checkpoint đúng ABI → real shadow → bounded deployment | Shadow chỉ ingestion/inference; chưa release limits/latency/stop thì authority vẫn 0 |

GUI **Xây project → Việc cần làm** đã cập nhật các bước và dữ liệu cần theo
trình tự này. Các thao tác thu/motion và artifact lịch sử không bị reset.

## Kiểm chứng và nguồn

Artifact kiểm thử mới nằm ở workspace triển khai:
`artifacts/data_studio_standardization_2026-11-04/`.
JSON kiểm chứng kèm theo ghi source hashes, JUnit, environment, screenshot,
build và giới hạn. Các test dùng data tổng hợp, không là lượt robot.

Kết quả: nhóm GUI/collector 59 đạt, nhóm TD3/export/reference 45 đạt; kiểm
chuyên biệt cuối có 22 parameter/export, 20 Qt và 3 lifecycle đạt. Các nhóm
có test trùng nhau, không cộng thành mẫu độc lập. Hai interpreter có skip
dependency tùy chọn tương ứng; Parquet đã kiểm trong venv, Qt trong system
Python. Đã thực hiện test optimizer fixture 32 transition/16 gradient updates,
replay và portable actor export; chưa có claim lợi ích. Bốn package build đạt
và GUI từ bản install mở được; observer bundle source/install khớp SHA256.
Lần build hai package đầu thiếu dependency trong prefix mới và một assertion
GUI cũ còn đòi bước đầu là motion đã được sửa; log thất bại vẫn giữ riêng.

Xem [JSON kiểm chứng](NINO_TD3_DATA_STUDIO_VERIFICATION_2026-11-04.json).

Đối chiếu [SB3 TD3 documentation](https://stable-baselines3.readthedocs.io/en/master/modules/td3.html)
ngày 04/11/2026 và source SB3 **2.9.0** cài local: `learning_rate` dùng chung
schedule và `TD3.train()` cập nhật cả optimizer actor/critic. Vì vậy không
nhận hai LR độc lập chỉ bằng cách thêm hai key YAML.

rosbag2 Python reader/writer và MCAP được kiểm trực tiếp qua package Jazzy
local (registered readers/writers + actual synthetic CDR recordings).
Hai trang docs.ros.org bị access denied/internal error và trang README MCAP
GitHub không fetch được trong lần tra cứu này; không suy nội dung chưa đọc
thành kết quả. Report bên ngoài không cung cấp link tài liệu đầy đủ nên các
giá trị minh họa chỉ được ghi là profile đề xuất.

**Việc nên làm ngay:** mở Studio và kiểm observer trên Pi đang chạy driver;
chỉ thu một phiên chỉ đọc nếu nó giải quyết một câu hỏi còn thiếu. Artifact
cần nhận là closed raw/QC/import có provenance, chưa phải lần chứng minh TD3.
