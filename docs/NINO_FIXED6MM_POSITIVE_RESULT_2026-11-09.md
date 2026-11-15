# E2-03: đã chạy, đóng cell 3/3; quyền điều khiển dương còn unknown

Ngày 09/11/2026. Tiếp [cặp E2-01/02](NINO_FIXED6MM_FIRST_PAIR_RESULT_2026-11-09.md).
**Chỉ một fresh launch mới, không retry; không train hoặc hardware.**

## Quyết định

E2-03 common **+0.005m/s** sau first received C1 manifold đã chạy đủ140ticks/
14s task. Native replay, task, stop và closure đạt. Tuy nhiên reader so sánh
đã khóa từ chối một nhóm wheel samples cùng source stamp nhưng khác payload.
Verdict cell: **`unknown_conflicting_wheel_source_timestamp`**.

Đã review phép đo từng slot và đóng allocation **3/3**; tương ứng3/12 slot
trong protocol đề xuất. **9 slot còn lại chưa cấp.** Không chạy E2-04 hoặc
train để thay thế kết luận unknown. Lợi ích của TD3/governor sensor-only và
risk/slip vẫn chưa được chứng minh.

**Bước tiếp là offline:** chuẩn bị đúng một correction có phiên bản cho
reader/support của timestamp mơ hồ, dùng raw hiện có và synthetic fixtures;
không lấy thêm lượt vật lý, không sửa ngưỡng và không chọn tùy ý một mẫu.
Draft correction đã ghi rõ expected behavior, chưa áp/release. Nếu có thể
khôi phục kết luận thì xuất report phiên bản riêng, giữ report unknown này.

## Thực tế đã chạy và kiểm

| Đại lượng | E2-03 |
|---|---:|
| Condition | block0, stop6s, Ki0.10, common +0.005m/s |
| World | Box phẳng, cylinder cứng Ø6mm x0.65m; không DR |
| Task transitions | 140/140 |
| Task / stop | Đạt / đạt |
| Accepted nonzero residual | 18 ticks |
| Native full-route body vRMSE | 20.766mm/s |
| Path RMSE /max cross-track | 1.783 /2.515mm |
| Final progress | 1.06567m |
| Original file hashes | 39/39; cả cell117/117 |
| Oracle/history/projection/reward/task replay | 140/140 row mới; tổng420 |

Handoff đã giữ nguyên hai attempt cũ, consumed wall và78 file; chỉ cấp thêm
E2-03. Helper mới tách khỏi frozen runtime/controller, có lock, source/test
pins và crash state. **210 test đạt trước launch**, hai package build đạt.
Không thay gain/current/reward/history, identity hoặc protocol draft gốc.
Kiểm tra cuối: **215/215 software tests đạt**, source/install và hash hợp lệ;
không phát hiện Sim còn chạy sau closure.

## Timestamp nào mơ hồ, ảnh hưởng gì?

- E2-03 có **bốn wheel payload khác nhau tại stamp3.128s**, tương ứng task
  1.563s, **2.080s trước first manifold**. Stamp khác kế tiếp là3.136s.
- Cả primary và independent joint observer đều ghi bốn payload hashes khác
  nhau ở source3128000000ns. Source `_receive(wheel)` lưu header stamp của
  JointState. Vì vậy bằng chứng ủng hộ ambiguity đã có ở ROS message header;
  **chưa xác định nguyên nhân upstream**, không quy nó cho motor/firmware thật.
- Nhóm này ở ngoài last0.5s approach và cửa sổ authority sau trigger. Nhưng
  **reader đã pin kiểm cả wheel channel**, nên nó dừng trước khi trả paired
  wheel/body authority. Không sửa reader âm thầm sau khi thấy kết quả.
- Giữ cả bốn mẫu và receipt times. Không chọn first/last, đổi stamp theo
  receipt, nội suy hoặc thay bằng zero. Unknown là giới hạn của phép đánh
  giá đang khóa, không tự chứng minh robot không có quyền điều khiển.

Native/history replay và GT primary có thể đạt trong khi strict paired
wheel-time audit còn unknown: đó là các claim/gate khác nhau. Không cộng
chúng thành chứng cứ đã đạt toàn bộ H2.

## Chẩn đoán GT riêng, không dùng để vượt gate wheel

| Metric | Neutral E2-01 | Common− E2-02 | Common+ E2-03 |
|---|---:|---:|---:|
| GT20ms ISE, m²/s | 0.011560674 | 0.006472169 | 0.005181284 |
| GT20ms +10ms ISE, m²/s | 0.011556585 | 0.006495597 | 0.005179092 |
| Native100ms window ISE, m²/s | 0.011290733 | 0.005841356 | 0.005728748 |
| Native full-route vRMSE, mm/s | 29.099 | 20.993 | 20.766 |

Common+ giảm GT primary **55.18%/55.18%** so neutral, native window49.26%,
full-route vRMSE28.64%; quiet onset không tăng. Ranking mô tả trên cả ba
namespace là **common+ → common− → neutral**, ISE thấp hơn đứng trước.
**Không đủ để chọn winner hoặc promote:** wheel authority chưa xác minh,
một block/stop không là independent test hay exact-state branching. Hai
chiều cùng cải thiện cũng không tự chứng minh một quy luật speed tối ưu.

Body-speed caliper pairwise đều dưới1mm/s trên cả ba grid:

| Candidate−control | GT20ms /+10ms RMS, mm/s | Native100ms RMS, mm/s |
|---|---:|---:|
| E2-02−E2-01 | 0.813 /0.813 | 0.736 |
| E2-03−E2-01 | 0.603 /0.603 | 0.612 |
| E2-03−E2-02 | 0.414 /0.414 | 0.354 |

Caliper chỉ hạn chế confound theo body speed, không chứng minh caster/load
giống nhau. Coverage primary giữ100%/99.6667%, native báo riêng. ISE vận
tốc không phải slip, lực, impulse, rung hoặc damage.

## Việc kế tiếp và điểm dừng

1. Dùng raw của117 file và hai observer để mô tả mọi stamp conflict; việc
   đối chiếu nhóm3.128s đã xong, không cần thu lại để xác nhận nó tồn tại.
2. Chuẩn bị reader phiên bản riêng có trạng thái unsupported cho timestamp
   nhiều payload; query không được dùng mẫu tương lai hay chọn first/last.
   Test ambiguity đúng trong/ngoài cửa sổ, sát boundary và raw reversal.
   Giữ nguyên windows, caliper, coverage và source-gap limits. Nếu query cần
   ambiguity hoặc support không đủ, tiếp tục unknown.
3. Chỉ sau review correction offline mới tính lại cùng dữ liệu, lưu verdict
   mới riêng. Nếu không khôi phục được, đóng unknown; không refill/retry.
   Chưa cấp cell stop/block kế tiếp hoặc research12k/3×50k.

Studio hiển thị 3/12 consumed, allocation3/3 đóng, timestamp issue và next
offline task. Badge kiểm hash report/contract/closed ledger, giữ unknown;
historical E2-01/02 vẫn trỏ closure bất biến. GUI không mở allocation mới.

Audit:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_positive_2026-11-09/`.
Raw:
`~/nino_research/fixed6mm_postmanifold_neutral_20261108_v1/E2-03`.
