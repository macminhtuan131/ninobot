# Eval-only A seed11: hoàn tất 6/6, giữ baseline cổ điển

06/11/2026 · Protocol `nino_ready_A_eval_only_v1_2026_11_06`.

## Quyết định

**Không mở rộng checkpoint A cho clear known-stop theo mặc định.** Cổ điển
có velocity RMSE thấp hơn A và B0 ở cả hai lịch dừng, trên native và hai
GT-header grids. Đây là screening một checkpoint/seed, không phải kết luận
mọi TD3 vô ích hoặc chứng minh thuật toán đã hội tụ.

Đã triển khai runner eval-only và profile GUI riêng, chạy bằng nút GUI;
**6 fresh launches × 140 = 840 eval ticks; 0 train/optimizer/probe/retry/hardware.**
Mọi lượt đạt gate task/stop/measurement. V1/V2 và C partial vẫn đóng.

## Kết quả đo trong mô phỏng

Whole-14s velocity RMSE, đơn vị m/s; thấp hơn là tốt hơn.

| Source stop | Arm | Native primary | GT 20 ms | GT dịch +10 ms | Path RMSE mm |
|---|---|---:|---:|---:|---:|
| 6 s | B0 | 0,004771 | 0,006356 | 0,006361 | 0,014 |
| 6 s | A Gaussian seed11 | 0,006701 | 0,008158 | 0,008164 | 0,124 |
| 6 s | Classical scheduled | 0,003907 | 0,006025 | 0,006029 | 0,696 |
| 8 s | Classical scheduled | 0,003943 | 0,005692 | 0,005696 | 0,652 |
| 8 s | A Gaussian seed11 | 0,007445 | 0,008914 | 0,008920 | 0,014 |
| 8 s | B0 | 0,005149 | 0,006898 | 0,006903 | 0,026 |

Theo từng stop plan, `(A − baseline)/baseline`:

| Stop | A so B0, native | A so cổ điển, native | A so cổ điển, GT20 / GT+10 |
|---|---:|---:|---:|
| 6 s | +40,46% | +71,50% | +35,40% / +35,41% |
| 8 s | +44,59% | +88,83% | +56,61% / +56,61% |

Không gộp native/GT hoặc đổi primary sau kết quả. Cổ điển tốt hơn về
velocity RMSE nhưng path RMSE cao hơn trong các lượt này; tất cả còn trong
gate 40 mm. Chưa có yêu cầu ứng dụng chấp nhận nên không gọi là tối ưu mọi
tiêu chí. Một run/condition không cho CI, power hoặc equivalence đáng tin.

## Hành vi policy: bằng chứng và suy luận

**[N-sim]** Trong 30/50 tick có common window mở, A yêu cầu scalar trung bình
−0,99053/−0,99088, tương ứng common −0,004953/−0,004954 m/s. Toàn bộ tick
mở có request ≤−0,95. Cổ điển dùng +0,005 m/s, B0 bằng zero.

**[N-sim]** Body-minus-nominal error trung bình trong window:

| Stop | B0 | A | Cổ điển |
|---|---:|---:|---:|
| 6 s | −0,006582 | −0,011789 | −0,002264 |
| 8 s | −0,005135 | −0,010210 | −0,000473 |

**[S]** A bù âm trong khi trajectory đang thiếu tốc độ là cơ chế phù hợp
với sai số tăng. Không đủ để quy nguyên nhân riêng cho critic, reward,
coverage hay số update. Coverage A trong training còn lệch; C partial chưa
có comparison hợp lệ. Không tự tăng gain/current, reward penalty hoặc
training steps từ quan sát này. Phân tích actor/critic cũ là nguồn lịch sử,
không thay cho counterfactual của checkpoint A mới này.

## Integrity và lifecycle

- **199 file** trong manifest khớp SHA256; raw đã seal, review ở ngoài raw.
- **2.561 boundary checks**: cả primary/independent supported; joint age
  tối đa 1 ms tại các checks, không suy thành loss-free toàn luồng.
- **1.750 physics requests** đúng ACK/completion/số iterations; retries 0.
- Primary/independent mỗi bên 54.931 records; common 54.930 source stamps,
  payload mismatch 0. Counts không thay cho coverage từng metric.
- Sáu lifecycle và observer đóng ACK. Decision permission/source age đạt;
  không có proposal null được thay zero để qua validator.
- Actor/targets/optimizer/counters/sampler trước–sau bằng nhau; checkpoint
  A giữ SHA. Hai lần load A phục vụ deterministic evaluation, không resume.
- Settling đạt quiet+drive ACK: 5 rounds ở năm lượt, 10 rounds ở classical–6
  (0,5/1,0 simulation seconds). Không coi các launch là exact-state branching.
- 78 kiểm tra phần mềm/GUI trước release; 60 kiểm tra GUI sau sửa hiển thị
  đạt. Đây là software tests, không là lượt vượt vật cản.
- Release eval-only đã đóng sau attempt; GUI khóa chạy lại root đã tiêu thụ.

## Phạm vi và bước tiếp theo

Clear-box factory lab, nominal 0,2 m/s, common ±0,005 m/s, 10 Hz,
103D/1D/history5, preview lịch dừng chung. Không phải factory mixed map,
contact benefit, unseen test hoặc sim-to-real. Chưa có dữ liệu thật mới;
cutoff real giữ 02/11/2026, hardware residual authority vẫn zero.

**Việc kế tiếp:** [chốt lại câu hỏi và benchmark Sim](NINO_SIM_BENCHMARK_DECISION_NEXT_2026-11-06.md)
trước khi mở training. Giữ cổ điển làm reference; không tự mở rộng history,
PPO, C partial hoặc randomization để cố đổi ranking.

## Artifact và pins

- Root: `/home/tuanmac/nino_research/sim_ready_eval_only_v1`.
- Run: `20261106T131105761794Z_sim-ready-eval-only`.
- Manifest SHA256: `02832bf0e9d2bccf2e9361c56b61c9d634522b7321622764ce3842ea141ed9d9`.
- Runner fingerprint: `d75036f1a15431c16fc92eb82e34319652b17e05483a81ea86455c26f08eec3d`.
- A checkpoint SHA256: `40f676c7464a94440d57cda34c6eb277ba67d6fb7a87760f8bc363af253a6166`.
- [Protocol](NINO_SIM_READY_EVAL_ONLY_PROTOCOL_2026-11-06.md).
- QA logs/tests/GUI: client workspace `artifacts/sim_ready_eval_only_2026-11-06/`.
