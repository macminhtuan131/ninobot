# E2-01/02: cặp đầu đã đóng, đủ đề cử điều kiện tiếp theo

Ngày 09/11/2026. **Hai lượt Gazebo, tổng 280 task transitions; không train
TD3, không thao tác hardware.** Đây là screen quyền điều khiển dùng oracle,
không phải governor sensor-only hoặc kết quả learned policy.

## Quyết định

Giữ baseline Ki0.10 và mọi giới hạn/history/reward hiện tại. Trong một
development cell block0/stop6, common −0.005m/s sau first C1 manifold tạo
tương phản bánh/thân đúng dấu trước drive contact, giảm primary tracking
error và qua các ràng buộc đã khóa. Verdict:
`first_pair_eligible_for_next_declared_condition_not_benefit`.

**Đề cử E2-03 common +0.005m/s cùng cell** để kiểm chiều action, trong matrix
12 slot đã đề xuất; chưa cấp hoặc chạy. Không cần đổi learning rate, history,
gain, current hay reward từ cặp này. Allocation hiện hết **2/2**; còn **10
slot proposed chưa cấp**, không refill hoặc chạy lại neutral.

## Phạm vi và provenance

- E2-01 neutral được giữ nguyên; handoff kiểm 39 file và kế thừa slot/wall
  đã dùng. Helper continuation không chạy vật lý, không reset ledger.
- Chỉ thêm một allocation E2-02, một fresh launch, 140 ticks/14s task;
  common −0.005m/s được chấp nhận 18 ticks, task và stop đạt.
- Sàn box phẳng, cylinder cứng Ø6mm tại x0.65m, cruise0.2m/s, stop6s;
  không DR, không dây mềm/rãnh/hõm hoặc unseen test bank.
- So sánh khóa trong `pair_contract.json` trước launch. Mỗi run căn theo
  first C1 source manifold riêng; **không snapshot/restore cùng trạng thái**.
  Caliper chỉ hạn chế confound theo body speed, không chứng minh caster/load
  và mọi trạng thái ẩn bằng nhau.
- 39/39 file mỗi slot khớp hash; 140/140 row mỗi slot replay
  oracle/history/projection/reward/task khớp. Recorder/lifecycle đóng, không
  retry. Giữ nguyên raw, spike và native/GT namespaces riêng.

## Kết quả theo contract đã khóa

| Đại lượng | E2-01 neutral | E2-02 common −0.005 | Diễn giải |
|---|---:|---:|---|
| GT-header20ms ISE, m²/s | 0.011560674 | 0.006472169 | −44.02% mô tả |
| GT-header20ms +10ms ISE, m²/s | 0.011556585 | 0.006495597 | −43.79% mô tả |
| Native100ms window ISE, m²/s | 0.011290733 | 0.005841356 | −48.26%, báo riêng |
| Full-route native vRMSE, mm/s | 29.099 | 20.993 | −27.86%; không vượt giới hạn regression2% |
| Physical path RMSE, mm | 4.960 | 1.258 | Chỉ mô tả |
| Max cross-track, mm | 7.114 | 1.768 | Đều dưới40mm |
| Final progress, m | 1.04269 | 1.04441 | Đều qua marker0.95m |
| Quiet onset sau source stop, s | 2.0 | 2.0 | Không tăng; không phải stopping distance |

Primary giữ `tc..tc+3s`, causal as-of, không nội suy tương lai. Coverage GT
100% và99.6667% trên grid dịch (2.99/3s); không nâng giả thành100%.
ISE vận tốc **không phải slip, năng lượng, rung hay tải gây hại**. Một cell,
không CI hoặc kết luận thống kê tổng quát.

### Caliper và quyền điều khiển

Last0.5s trước tc: RMS chênh body speed candidate−neutral **0.813 /0.813
/0.736mm/s** trên GT20ms /grid+10ms /native100ms; cả ba dưới caliper1mm/s.
Accepted linear reference trước contact giống nhau trong cửa sổ này.

E2-02 first source manifold5.221s, decision5.269s: **48ms Sim**, không phải
latency hardware. Các phase căn tc:

- Candidate trigger: +0.048s.
- Deadline là first drive manifold sớm hơn của hai run: +1.196s.
- 58/58 query trong cửa sổ có support; chuỗi accepted reference/driver,
  target, **cả hai actual wheel** và body cùng giảm. Body chênh ít nhất
  −0.001m/s trong đoạn query +0.428..+1.188s, với **0.760s source span
  quan sát ở cả hai run**, trước deadline; không cộng đệm một cell20ms.

Qua gate quyền điều khiển **của cặp mô tả này**, có điều kiện trên caliper.
Không chứng minh loaded contact/force, mọi tác động đều do action, early
impact được ngăn, hoặc lợi ích của detector/predictor chưa xây. Oracle nằm
ngoài 100D deployable history.

## Phần mềm và GUI

Đã sửa ba regression GUI cũ: kỳ vọng document chuyển theo review hiện tại,
summary giữ tiến độ E1 và prestop, neutral ledger trỏ bản closure bất biến
thay vì root ledger đang tiếp tục. Thêm helper handoff có khóa/receipt,
kiểm baseline và pin test/source trước continuation. 177 test đạt trước
launch. Test cuối **187/187 đạt**, gồm kiểm future/stale sample, source
reversal và persistence sát biên200ms; không ghi đè XML đã pin trong release.
Hai package build thành công. Bước build cuối chuyển nhầm sang symlink
install khiến preflight từ chối đường dẫn package; đã khôi phục install
thường theo contract, giữ nguyên source/controller và dữ liệu đã chạy.

Studio hiển thị 2/12 consumed, caliper/metric/authority và giới hạn một cell;
kiểm hash report, comparison contract và ledger closed/reviewed trước hiển thị.
Không mở quyền motion hoặc training mới từ badge kết quả.

## Việc tiếp theo, có điểm dừng

1. Chuẩn bị continuation riêng cho **E2-03**, kế thừa cả hai slot đã review;
   chỉ common +0.005, giữ baseline và quy tắc caliper/coverage/timing. Không
   chạy E2-01/02 lại. Chưa release trong lượt hiện tại.
2. Sau E2-03: nếu approach/support/grid không hợp lệ, đóng unknown, không
   thêm seed/refill. Nếu hợp lệ, đánh giá action ranking hai chiều và
   ràng buộc task/tracking/stop; profile + không bắt buộc phải thắng neutral.
   Kết quả phải được review trước khi xét các cell stop/block còn lại.
3. Chỉ sau bounded screen đủ điều kiện mới xem xét learner pilot riêng và
   bank validation/test. Cặp này không mở research12k hoặc3×50k và không
   đổi kết luận classical vẫn ưu tiên cho clear-floor planned-stop cũ.

Raw: `~/nino_research/fixed6mm_postmanifold_neutral_20261108_v1/E2-01`
và `E2-02`. Audit/release/handoff/contract/replay/closure:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_continuation_2026-11-09/`.
