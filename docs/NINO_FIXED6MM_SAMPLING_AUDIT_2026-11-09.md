# Audit offline stop8: lấy mẫu đổi dấu, chưa có lỗi công thức để sửa

Ngày09/11/2026. Tiếp [cell stop8 đã đóng](NINO_FIXED6MM_STOP8_RESULT_2026-11-09.md).

## Quyết định

**Giữ classical; đóng nhánh promote common± hiện tại cho envelope đã thử.**
Stop8 vẫn `unknown_stop8_support_or_sampling`; không đổi lịch sử thành pass.
Không tìm thấy lỗi công thức/source/reference giải thích đổi dấu ở cặp
E2-05 neutral / E2-06 common−. Chưa có căn cứ mở block1 hoặc train dài để
giải quyết bất đồng này. Đây không phải kết luận TD3 luôn vô ích.

Audit dùng bốn lượt đã có:05/06 là cặp chính,01/02 chỉ cung cấp bối cảnh
stop6; không pool hai estimand. **0physics mới,0optimizer,0hardware,
0allocation mới.** Ledger vẫn6/6 đóng,6slot block1 chưa cấp.

## Công thức và clock: đã kiểm gì?

560/560 native rows tái lập chính xác:

```text
native velocity_error = recorded body_speed − task.nominal_shaped_body[0]
truth source stamp = sensor_clock − source_lags.truth
task nominal = oracle nominal gắn với quyết định của transition đó
```

Sai khác lớn nhất của cả ba kiểm tra bằng0 trên dữ liệu đã ghi. Native
không chấm tracking theo accepted residual reference để tự tạo lợi ích.
GT tại source stamp suy từ lag khớp đúng body value; không thay receipt
time thành source time. Việc này kiểm dữ liệu Sim, không đo latency thật.

Ở stop8, nominal trong primary luôn0.2m/s. GT causal query tại **đúng
sensor_clock native**, giữ trọng số0.1s, tái lập native ISE ở cả hai arm:
30/30 query/arm đủ support, cùng truth source, không có error mismatch.
Vì vậy bất đồng stop8 không đến từ chọn sai nominal hoặc body channel.
Tuổi GT native: neutral11ms, common−9ms, đều là khoảng quan sát trong Sim.

| Cách tính | Neutral05 ISE | Common−06 ISE | Delta tương đối |
|---|---:|---:|---:|
| GT20ms primary,3s | 0.006480373 | 0.006117751 | −5.5957% |
| GT20ms+10ms primary,2.99s support | 0.006479128 | 0.006116642 | −5.5947% |
| Native100ms,30 điểm×0.1s | 0.006486392 | 0.006546151 | +0.9213% |
| GT query tại native clocks, **phụ trợ** | 0.006486392 | 0.006546151 | +0.9213% |

Đơn vị ISE làm²/s. Không phải slip, năng lượng, force hoặc tải hàng hóa.
Primary cũ được tái lập tới sai số số học<1e−12, không sửa estimator.

## Phase và sampling giải thích bất đồng thế nào?

Mỗi lượt dùng chính tc của nó. Tách **trọng số của estimator**, không nội
suy động lực học: mỗi hình chữ nhật sai số giữ nguyên, chỉ chia trọng số
nếu cắt qua biên phase/bin0.2s. Tất cả spike giữ nguyên. Manifold không
phải contact chịu tải; ranh giới phase hai lượt không hoàn toàn trùng nhau.

| Phase theo manifold từng lượt | ΔISE GT20ms | ΔISE native100ms |
|---|---:|---:|
| Trước drive manifold đầu | −0.001664454 | −0.001196748 |
| Giữa hai drive manifold | +0.000000369 | +0.000000306 |
| Sau cả hai drive manifold, trong3s | +0.001301463 | +0.001255761 |
| Trọng số native vượt biên3s | ≈0 | +0.000000440 |
| **Tổng common− − neutral** | **−0.000362621** | **+0.000059759** |

GT ghi mức giảm sai số trước drive lớn hơn native; phần tăng sau drive
gần bù phần giảm đó. Chỉ riêng bin0..0.2s: delta GT−0.001571738,
native−0.000769655m²/s. Chênh lấy mẫu tại transient đủ làm tổng đổi dấu.
Không suy toàn bộ phần giảm sớm là tác dụng action: một phần cửa sổ trước
intervention/response; các fresh launch cũng không là exact-state branching.

Native chọn30 điểm trong cửa sổ, điểm đầu ở+57/+53ms và mỗi điểm mang
trọng số0.1s. Khi biểu diễn thành hình chữ nhật, có57/53ms trọng số vượt
biên cuối. Delta phần vượt biên chỉ giải thích khoảng**0.104%** chênh
contrast native−GT; cắt phần đó trong tính phụ trợ vẫn giữ native delta
dương. Không được dùng phép cắt này thay primary đã khóa.

Đây là bằng chứng **sampling sensitivity của trajectory đã quan sát**,
không chứng minh GT20ms là đáp án vật lý tuyệt đối: GT nguồn≈50Hz vẫn có
bandwidth hữu hạn. Không có thêm seed/lặp, CI hay claim tổng quát hóa.

## Stop6 chỉ là bối cảnh

01/02 có withdrawal ởtc+1.852/1.848s và source stop ở+2.352/2.348s,
nằm trong primary. Stop8 withdrawal+3.857/3.853s, stop+4.357/4.353s,
đều ngoài primary. Trong stop6, phần giảm lớn tập trung sau drive; không
giống cơ chế giảm sớm/tăng muộn của cặp stop8.

Ở stop6 có7/30 điểm/arm mà GT@native phụ trợ khác native error: native
gắn nominal với quyết định đầu transition, trong khi query as-of tại
sensor_clock cuối transition gặp nominal của quyết định kế tiếp đang hạ
tốc. Truth body vẫn cùng source; native vẫn đúng công thức đã khóa. Ví dụ
điểm đầu lúc source stop: nominal gắn transition0.20, as-of0.19m/s.
Đây là **semantics reference khác tại phase chuyển tiếp**, không phải lý
do stop8 đổi dấu. Một nghiên cứu tương lai cần khai báo clock/reference
semantics prospective; không sửa lịch sử để tìm winner.

## Đã sửa gì trong project và Studio?

- Thêm công cụ attribution/equation offline riêng và test missing/ambiguous
  source, spike/boundary conservation. Không sửa controller, reader hoặc
  primary metric đang frozen.
- Studio hiển thị audit đã đóng, giữ classical,6/12consumed; thay bước
  “chờ audit” bằng định hướng contract mới. Loader kiểm hash/pins và từ
  chối claim benefit, allocation hoặc physics mới từ audit này.
- Giữ raw, ledger, release, checkpoint và báo cáo unknown cũ nguyên vẹn.

Kiểm tra hoàn tất: **63/63 tests đạt; build nino_rl/nino_pi đạt**. Hash của
234 file thuộc6slot,179 file trong4audit niêm phong,54 original được bảo vệ
và197 file E1 còn giữ đều khớp.66 file E1 đã dọn từ trước khớp đúng receipt
retention cũ, không có xóa mới. Ledger byte-identical, không phát hiện Sim
khác đang chạy; source/install/GUI đã đối chiếu, không job được khởi chạy.

## Các bước sau: có điểm dừng

1. **Dừng promote/tuning/training cho câu hỏi hiện tại.** Bằng chứng đã đủ
   để không tăng sample chỉ nhằm vượt gate; không mở lại logging audit.
2. Trước nghiên cứu mới, chốt ứng dụng muốn cải thiện tracking, rung hay
   slip và trade-off thời gian. Chọn reference/metric theo claim: encoder
   odom không đủ để kết luận slip thật; velocity ISE không thay rung.
3. Nếu ứng dụng còn cần adaptation, viết **một contract prospective riêng**
   có baseline classical mạnh, cửa sổ/clock/support và cơ chế tác động còn
   kịp. Preview theo tuyến đã biết có thể là phương án nghiên cứu; chưa
   được triển khai hoặc chứng minh. Chỉ xét TD3 khi action coverage và
   đánh giá phù hợp câu hỏi mới, không dùng return để thay physical outcome.

Không có batch mới trong kế hoạch thực thi lượt này. Điều khiến đổi quyết
định: một nhu cầu ứng dụng cụ thể và contract mới có cơ chế/đối chứng bảo vệ
được; hoặc bằng chứng tái lập một lỗi công thức chưa được audit này phát
hiện. Kết quả GT thuận lợi hiện tại riêng lẻ không đủ.

Artifact:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/fixed6mm_stop8_sampling_audit_2026-11-09/`.
Gồm contract pins,`evaluation.json`,`samples.csv`,query masks/timestamps,
`equation_and_timing_summary.json`,`sampling_phases.png`,tests/build và
verification/manifest. Không có nguồn ngoài hoặc đo phần cứng mới.
