# Cell stop8 đã đóng: actuator có tác động, lợi ích quality còn sampling-sensitive

Ngày09/11/2026. Tiếp [correction query-support v2](NINO_FIXED6MM_TIMESTAMP_REANALYSIS_2026-11-09.md).
**Ba fresh launch mới E2-04/05/06, không retry/smoke thêm;0optimizer/hardware.**

## Quyết định

Đóng allocation **6/6**, gồm3 lượt stop6 đã giữ nguyên và3 lượt stop8 mới.
**6 slot block1 còn lại chưa cấp.** Verdict:
`unknown_stop8_support_or_sampling`, cụ thể là **sampling/ranking conflict**,
không phải thiếu support hoặc lỗi logger/reader.

Giữ classical cho envelope này; chưa promote common+ hoặc common−, chưa
train thêm TD3/predictor, chưa mở block1 để tăng sample sau kết quả. Actuator
response không còn là unknown trong hai cell mô tả, nhưng lợi ích hệ thống
chưa vượt gate metric đã khóa.

**Việc tiếp theo:** một audit offline có giới hạn từ E2-05/E2-06 để giải thích
native100ms so GT20ms đổi dấu: đối chiếu error/reference/source stamps và
đóng góp theo phase. Artifact chuẩn bị nêu rõ không đổi primary, coverage,
spike hoặc chọn grid thuận lợi. Nếu là sampling sensitivity thực, giữ
classical và dừng nhánh promote hiện tại; nếu phát hiện lỗi công thức, cần
contract prospective riêng, không sửa lịch sử unknown thành pass.

## Đã làm gì và giới hạn ngân sách

- Handoff chỉ cho prefix3→6, giữ nguyên3 attempt/wall và117 file cũ; nguồn
  controller, baseline Ki0.10, gain/reward/history/limits và reader v2 không đổi.
-268 software tests đạt trước launch, hai package build đạt. Kiểm riêng
  quiet onset phải tính từ stop8, không dùng nhầm stop6.
- E2-04 common+ được audit/review trước E2-05 neutral. Cặp +/0 qua caliper/
  authority nhưng quality thua neutral; theo contract đã pin, vẫn chạy E2-06
  âm để hoàn tất đối chứng hai chiều, không tune sau khi thấy kết quả.
- Mỗi slot140/140ticks, task/marker và sustained stop đạt;39/39file/slot,
  native oracle/history/projection/reward/task replay140/140. Tổng mới420
  task transitions; tổng study840, **không phải RL training transitions**.
- Kiểm tra cuối **275/275 tests đạt**, source/install/GUI evidence khớp;
 234/234 file gốc được bảo toàn, không phát hiện Sim còn chạy sau closure.
- Primary `tc..tc+3s` thực sự kết thúc trước source stop8 ở cả ba lượt.
  Không dùng B0 stop6 hoặc E1 làm control stop8, không gộp hai window.

Scope: box phẳng, cylinder cứng Ø6mm x0.65m, block0, cruise0.2m/s, oracle
sau first received C1 manifold. Không là factory mixed map, dây mềm, slip/
force/risk hay robot thật. Manifold không chứng minh loaded contact.

## Kết quả chất lượng: không được chọn namespace có lợi

| Metric | Common+ E2-04 | Neutral E2-05 | Common− E2-06 |
|---|---:|---:|---:|
| GT20ms ISE, m²/s | 0.007892347 | 0.006480373 | 0.006117751 |
| GT20ms +10ms ISE, m²/s | 0.007891514 | 0.006479128 | 0.006116642 |
| Native100ms window ISE, m²/s | 0.007941985 | 0.006486392 | 0.006546151 |
| Full-native vRMSE, mm/s | 24.457 | 22.071 | 22.203 |
| Path RMSE, mm | 2.802 | 4.748 | 2.859 |
| Max cross-track, mm | 7.283 | 7.090 | 4.877 |
| Final progress, m | 1.47343 | 1.45792 | 1.43737 |
| Accepted nonzero residual ticks | 38 | 0 | 38 |

So neutral:

- **Common+:** GT primary tăng21.79%/21.80%; native tăng22.44%; full-route
  vRMSE tăng10.81%, vượt giới hạn regression2%. Không là candidate tốt.
- **Common−:** GT primary giảm5.596%/5.595%, nhưng **native tăng0.921%**;
  full-route vRMSE tăng0.598% (vẫn dưới2%). Đổi dấu giữa namespaces làm
  không qua gate nhất quán; không lấy riêng mức giảm GT>5% để promote.
- Quiet onset cả ba≈2s sau stop8, không regression; task/path/marker đạt.

Ranking GT20ms và+10ms: **common− → neutral → common+**. Ranking native:
**neutral → common− → common+**. Không thay metric/window, làm trơn rồi chọn
winner, loại spike hoặc gọi CI nhỏ mẫu chứng minh tương đương. Một lượt/arm,
không có CI/generalization claim. ISE velocity không phải slip/rung/energy.

## Quyền điều khiển và comparability

| Cặp | Caliper RMS GT /+10ms /native, mm/s | Query authority đủ support | Observed source span đúng dấu |
|---|---:|---:|---:|
| + so neutral | 0.840 /0.847 /0.638 | 55/55 | 0.580s |
| − so neutral | 0.457 /0.437 /0.360 | 57/57 | 0.840s |
| − so + | 0.804 /0.784 /0.727 | Báo caliper | Không dùng làm contrast authority chính |

Đều dưới caliper1mm/s; precontact accepted linear reference giống nhau trong
cửa sổ audit. Cả driver/reference, targets, actual hai bánh và body đúng dấu
ít nhất1mm/s, giữ observed span≥0.2s trước drive manifold sớm hơn của từng
cặp. Không padding20ms, không query mơ hồ hoặc bịa độ phân giải GT.

Đây là H2 response có điều kiện trong cell mô tả; caliper body speed không
khóa caster/load/trạng thái ẩn. Fresh launches không exact-state branching;
không kết luận toàn bộ outcome khác biệt đều do action. Chưa đủ H3 benefit.

## So với stop6 và hướng đi

Stop6 trước đó cả hai chiều giảm primary mạnh; stop8 dương thua rõ, âm đổi
dấu GT/native. Kết quả tốt ở stop6 **chưa chuyển được thành lợi ích ổn định
khi lịch dừng đổi**. Stop6 primary chứa withdrawal/planned-stop phase,
stop8 không chứa; đây là khác biệt cần audit, chưa chứng minh là nguyên nhân
duy nhất vì các lượt không cùng trạng thái vật lý.

Không tăng learning rate/history/reward/action scale hoặc cấp thêm training
để xử lý một gate metric còn bất đồng. Một phase/native-GT audit từ raw đã
có có thể phân biệt công thức sai với sampling sensitivity; không cần lấy
thêm Sim/hardware chỉ để thấy lại bất đồng đã ghi.

## Studio và dữ liệu bàn giao

Studio hiển thị6/12consumed,6/6allocation đóng, support/authority đạt nhưng
quality UNKNOWN; tách data integrity khỏi controller benefit. Report,
contract, query ledger, reader pins và closed ledger được kiểm hash trước
hiển thị. Các kết quả stop6/strict unknown v1/query-support v2 giữ riêng.

Audit:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_stop8_2026-11-09/`.
Raw:`~/nino_research/fixed6mm_postmanifold_neutral_20261108_v1/E2-04`,05,06.
Xem`cell_evaluation.json`,`cell_query_support.json`,`allocation_closure.json`
và`sampling_diagnostic_preparation.json`. Chưa có block1 hoặc learning release.
