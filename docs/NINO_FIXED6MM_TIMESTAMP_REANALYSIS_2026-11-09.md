# E2: correction reader offline đã kiểm, cell đầu có authority hai chiều

Ngày09/11/2026. **0 lượt Sim mới,0physics steps mới,0optimizer/hardware;
allocation vẫn3/3 đã đóng.** Tái sử dụng nguyên117 file của E2-01/02/03.

## Quyết định

Đã áp **một correction offline có phiên bản** cho query-support. Kết quả:
`first_cell_action_ranking_supported_no_benefit`.

Trong cell block0/stop6, cả common−0.005 và common+0.005 có tương phản
reference/driver/target→hai bánh→body đúng dấu, đủ persistence trước first
drive-wheel manifold. Qua gate feasibility/action ranking **của cell mô tả
này**, chưa chứng minh benefit tổng quát, thuật toán TD3, governor sensor-only,
slip/rung/contact risk hoặc robot thật.

**Việc tiếp theo:** chuẩn bị riêng cell stop8 theo đúng thứ tự E2-04(+),
E2-05(0), E2-06(−), cùng frozen baseline và mọi gate. Chỉ là đề cử; **9 slot
còn lại chưa cấp**, không tự chạy E2-04. Không đổi learning rate/history/
reward/gain/current và chưa mở training12k hoặc3×50k.

## Vì sao bản cũ unknown nhưng bản này có thể đánh giá?

Bản [E2-03 gốc](NINO_FIXED6MM_POSITIVE_RESULT_2026-11-09.md) dùng strict
reader từ chối cả channel nếu một timestamp có nhiều payload khác nhau.
Nhóm bốn mẫu tại3.128s nằm2.080s trước first manifold, ngoài mọi query
approach/authority đang hỏi. Báo cáo unknown, source, release và ledger cũ
được giữ nguyên; **không sửa lại lịch sử thành pass**.

Reader mới `causal_source_support.py`:

- Giữ đủ mọi payload trong mỗi timestamp. Group có khác biệt **không có giá
  trị sử dụng**, không lấy first/last/mean/zero hoặc quay về mẫu cũ.
- Query ở group mơ hồ hoặc trước stamp khác kế tiếp là unsupported. Chỉ
  stamp khác, không mơ hồ và còn trong age bound gốc mới phục hồi support.
- Không sort để sửa reversal, đổi clock theo receipt, nội suy hay chấp
  nhận mẫu tương lai. Dùng integer ns của ROS/Gazebo để tránh float boundary;
  không bịa độ phân giải và không chấp nhận ngay cả future1ns.
- Group conflict vẫn nằm trong ambiguity ledger, kể cả ngoài cửa sổ query.
  Mọi query cần ambiguity hoặc không đủ support vẫn dẫn tới unknown.

Các ngưỡng/windows/caliper/coverage/gap/persistence, primary/reward/controller
không đổi. Đây là sửa phạm vi support của phép đánh giá offline, **không sửa
upstream publisher hoặc làm các message mơ hồ trở thành đúng**. Nguyên nhân
upstream của header lặp vẫn chưa xác định.

## Kiểm chứng trước khi tính lại

16 fixture đạt trước khi khóa contract: conflict ngoài/trong cửa sổ, sát
boundary, identical duplicates, reversal, nonfinite/shape lỗi, stale/future,
unsupported không thành zero, observed persistence không cộng padding.
231 regression tests đạt, hai package build đạt. Contract pin reader,
review source, test XML và script trước tính lại positive authority.
Kiểm tra cuối **238/238 tests đạt**; source/install khớp, raw117file và các
report/ledger/checkpoint được bảo toàn, không phát hiện Sim còn chạy.

Gate đối chứng bằng dữ liệu đã kiểm:

1. Recompute `assess` cả ba slot trùng nguyên contact/GT primary/coverage cũ.
2. Body approach và authority E2-01/02 tái tạo trong1e−12, cùng query/mask/
   interval và persistence; không chạy lại vật lý.
3. Performance/constraint của ba arm trùng nguyên diagnostic cũ. Chỉ khả
   năng kiểm paired wheel-time được bổ sung; không thay metric thuận lợi.

## Kết quả query-support và authority

| Cặp candidate−neutral | Query authority đủ support | Đoạn query đúng dấu liên tục, phase từ tc | Observed source span |
|---|---:|---:|---:|
| Common− E2-02 | 58/58 | +0.428..+1.188s | 0.760s |
| Common+ E2-03 | 55/55 | +0.457..+1.077s | 0.620s |

Positive trigger +0.057s, deadline drive manifold sớm hơn của cặp +1.153s.
Đoạn đúng dấu dương wholly trước deadline; body delta ít nhất+0.001m/s,
cả actual wheels/targets cùng chiều, persistence vượt0.2s. Không cộng một
cell20ms vào source span. **0 query authority dùng group mơ hồ.** Một group
conflict duy nhất vẫn được giữ đủ bốn payload trong report mới.

Body RMS approach pairwise GT20ms/+10ms/native vẫn0.813/0.813/0.736;
0.603/0.603/0.612;0.414/0.414/0.354mm/s, đều dưới1mm/s.

## Primary không đổi, diễn giải vẫn có giới hạn

| Arm | GT20ms ISE, m²/s | GT+10ms ISE, m²/s | Native window ISE, m²/s |
|---|---:|---:|---:|
| Neutral | 0.011560674 | 0.011556585 | 0.011290733 |
| Common− | 0.006472169 | 0.006495597 | 0.005841356 |
| Common+ | 0.005181284 | 0.005179092 | 0.005728748 |

So neutral, common− giảm44.02%/43.79% và common+55.18%/55.18% trên hai GT
grid. Ranking mô tả cả ba namespace: common+ → common− → neutral. Full
native vRMSE giảm27.86%/28.64%; quiet onset đều2s sau source stop, task/
path/marker đạt. Không là stopping-distance estimate.

Một block/stop, fresh launch không exact-state branching; caliper speed
không kiểm hết caster/load/trạng thái ẩn. Hai chiều cùng cải thiện chưa là
quy luật tốc độ tối ưu. Oracle không nằm trong100D deployable history nhưng
vẫn là privileged trigger của thí nghiệm. ISE velocity không phải slip,
energy, force, rung hoặc hàng hóa hư hại. Chưa có CI/independent validation
hoặc đủ hai block/hai stop để promote controller.

## Studio và điểm dừng

Studio hiển thị riêng **unknown strict v1 lịch sử** và **query-supported v2
hiện tại**, kèm persistence0.760/0.620s và3/12 consumed. Loader kiểm hash
report/contract/source/test/query-support/ambiguity/ledger, không tự mở slot.

Correction budget1/1 đã dùng; không thêm correction để chọn kết quả đẹp.
Nếu cell tiếp cần unsupported sample hoặc fail gate, giữ unknown/no-go tại
budget đã khóa, không refill/đổi objective. Hiện chỉ đề cử chuẩn bị stop8;
không có Sim/train/hardware mới từ correction này.
Cell stop8 có draft `stop8_cell_preparation.json` trong audit:0allocated,
release=false, handoff chưa xây. Stop8 đưa planned stop ra ngoài primary
`tc..tc+3s`, giúp kiểm ranking có phụ thuộc lịch dừng của cell stop6 hay không.

Audit mới:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_timestamp_review_2026-11-09/`.
Xem `evaluation.json`, `query_support.json`, `source_ambiguities.json` và
`correction_contract.json`; report unknown cũ nằm nguyên ở artifact positive.
