# E2-01 neutral — Gazebo đã chạy và đóng 1/1

Ngày08/11/2026. Tiếp [runtime E2](NINO_FIXED6MM_AUTHORITY_RUNTIME_2026-11-08.md).
**Một fresh launch, không retry; không actor/optimizer/hardware.**

## Kết quả thực tế

| Đại lượng | Quan sát |
|---|---:|
| Slot / condition | E2-01, block0, stop6s, Ki0.10, common0 |
| World | Box phẳng, cylinder cứng Ø6mm tại x0.65m; không DR |
| Task transitions / thời gian task | **140/140 /14 simulation seconds**, setup riêng |
| Wall time slot, gồm setup/close | **51.764s** của riêng lượt này |
| Task / sustained stop | **Đạt /đạt**, continuous quiet cuối6s |
| Native body velocity RMSE | **29.099mm/s** |
| Physical path RMSE /max cross-track | **4.960 /7.114mm** |
| Final progress | **1.04269m** |
| Residual thực sự khác0 | **0/140 tick** |
| Oracle window mở | **18 tick**; arm zero vẫn không có residual |
| Original file hashes | **39/39** khớp |
| Oracle/history/projection/reward/task replay | **140/140 row** khớp |

**Verdict: `neutral_slot_pass_no_benefit`.** Đây là qualification phép đo/
tích hợp trên một trajectory neutral. Chưa có candidate/control contrast,
approach caliper giữa hai run, useful body authority, benefit của governor/
TD3, hoặc generalization. Không lấy RMSE này so winner với các fresh launch E1.

## Timing và contact: điều gì đã xác minh?

- First C1 manifold của hai caster cùng source stamp ở task **3.648s**.
  Callback caster phải được nhận trước và được oracle chọn; không áp thứ tự
  caster trái→phải từ lịch sử như quy luật bắt buộc.
- Decision trigger ở task **3.700s**, sau first source manifold **52ms Sim**.
  Ghi riêng receipt monotonic và source/decision Sim clock; wall receipt gap
  bao gồm lockstep pause/compute, không phải latency hardware.
- First drive-wheel manifold ở task **4.844s**: còn **1.144s source time**
  sau decision trigger. Đây là khoảng phase, chưa chứng minh body đổi kịp hoặc
  contact quality tốt hơn. Arm này không phát residual khác0 để kiểm điều đó.
- Oracle được replay từ **đúng prefix raw callbacks đã nhận trước từng
  cutoff**; không đọc future callback hoặc backdate trigger từ event đến muộn.
- Manifold không là loaded contact. Backend không có wrench/depth để suy
  lực, impulse, slip, tải hư hại hoặc cáp mềm.

Primary window giữ `tc..tc+3s`, tc là first source manifold của lượt này:

| Reporting riêng | ISE velocity, m²/s | Coverage thời lượng |
|---|---:|---:|
| GT-header20ms causal | 0.011560674 | 100% |
| GT-header20ms dịch+10ms causal | 0.011556585 | 99.6667% (2.99/3s) |
| Native100ms,30 mẫu | 0.011290733 | Báo riêng, không gộp vào GT metric |

Không xóa spike, đổi grid/cửa sổ hoặc dùng chênh metric sampling để chọn
winner. Native replay xác minh history/reference/reward/task từ source packets;
không replay vật lý counterfactual hoặc khôi phục exact caster state.

## Acquisition, closure và nguồn code

426 boundary checks của setup/control đều có support trên primary và
independent joint paths; maximum joint source age1ms trong lượt này. Đây
không phải426 lượt vượt gờ. Independent observer thoát0 với shutdown ACK,
không có motor-command publisher; lifecycle kết thúc `closed`, errors rỗng.

Trước launch đã sửa coordinator để nhận **prefix1**, thay vì yêu cầu cấp đủ12.
Qualification mới và30 test E2 đã đạt trước chạy; draft và planner gốc không
đổi. Release mẫu trong source vẫnfalse/0. Release riêng ràng buộc đúng
E2-01, một allocation,140 task ticks,300s wall cap,0 retry/learning/hardware.

Sau audit, đã gọi review đúng hash summary. Ledger hiện **`allocation_exhausted`**:
đã dùng1/1 được cấp, tương ứng1/12 slot của protocol đề xuất. **11 slot còn
lại chưa được cấp.** Giữ release gốc như provenance và closure receipt riêng;
không sửa hash release đã dùng hoặc ghi đè summary/raw sau review.

GUI outline hiển thị neutral đã đóng, metric có units và giới hạn claim;
kiểm hash report/ledger cùng qualification/source trước khi hiển thị đã xác minh.

## Việc tiếp theo

Chuẩn bị **continuation có receipt/handoff**, kế thừa E2-01 đã dùng và được
review; không reset ledger, refill hoặc chạy lại B0. Chỉ sau kiểm continuation
mới cấp riêng E2-02 common−0.005m/s. Mục tiêu tiếp là đối chiếu command→target
→actual hai bánh→body và caliper trước contact; không chạy nốt batch tự động.

Nếu approach/clock/coverage không hợp lệ, kết luận unknown và giữ dữ liệu.
Nếu can thiệp không tạo contrast hữu ích trước drive contact, không tăng
ngân sách train để che kết quả. Chưa mở research12k/3×50k, Ki0.15, DR hoặc real.

Artifact raw:
`~/nino_research/fixed6mm_postmanifold_neutral_20261108_v1/E2-01`.

Audit:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_neutral_2026-11-08/`.
