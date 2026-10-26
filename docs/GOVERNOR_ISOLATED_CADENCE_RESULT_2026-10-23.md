# Cadence acquisition: kết quả thực thi và correction — 23/10/2026

> **Cập nhật mới hơn:** [kết quả v4 và correction v5](GOVERNOR_ISOLATED_CADENCE_V4_RESULT_2026-10-23.md).
> V4 cũng đã đóng ở 1/12 do schema native/control identity. V5 đã kiểm tra
> phần mềm, chưa release/chạy. Phần dưới giữ nguyên lịch sử v3/correction v4.

## 1. Hiện trạng và quyết định

**Đã chạy một attempt simulation mới. Batch dừng và đóng ở 1/12 vì lỗi
lifecycle, trước lượt governor 20 ms. H2 chưa được đánh giá; chưa có
so sánh cadence mới.** Không retry, replacement, smoke hay tự dùng 11 slot
còn lại. Robot thật, PPO, predictor và Optuna tiếp tục giữ lại.

Đã chẩn đoán lỗi, sửa phần mềm và freeze **v4** sau **140 test đạt**.
V4 **chưa có simulation attempt hoặc budget release**, integration thực tế
của correction vẫn chưa được xác nhận. Không gọi các test phần mềm là kết
quả crossing/controller.

| Revision | Việc xảy ra | Simulation attempts | Trạng thái |
|---|---|---:|---|
| V2 | Executor lỗi kiểu đường dẫn ngay khi kiểm tra release | 0 | Chưa claim ngân sách, chưa tạo ledger/attempt |
| V3 | Sửa `sha(Path(__file__))`, freeze mới; attempt 1 PI chạy tuyến thành công nhưng runner timeout end ACK | 1 | Batch đóng; slots 2–12 chưa chạy, không chạy bù |
| V4 | Sửa phân biệt immutable ACK và live heartbeat, fault-test offline | 0 | Software prepared; chưa release/chạy batch mới |

Yêu cầu trực tiếp “evaluate ... and continously do what suggested” được
hiểu là tiếp tục screen tối đa 12 attempts vừa được đề xuất trong câu trả
lời trước. Cách diễn giải và giới hạn được ghi trước launch trong release;
không ghi thành người dùng đã chấp nhận ngưỡng hiệu quả ứng dụng.

## 2. Trước launch: lỗi executor đã tái hiện và sửa

`require_release` gọi `sha(__file__)`; helper `sha` yêu cầu `Path`, nên
release hợp lệ làm phát sinh `AttributeError: 'str' object has no attribute
'read_bytes'`. Vì nằm trước budget claim và tạo output, chưa có simulation
hoặc attempt nào trong lần gọi đó.

- Thêm regression test cho matching release; test tái hiện lỗi trước sửa.
- Correction duy nhất lúc này: `sha(Path(__file__))`.
- 126 test đạt sau correction; freeze v3, hash protocol
  `f420308638ccddd77671011b90d24b10af393aac6415357e75d45f57fb425c5d`.
- Lịch, acquisition và mọi input vật lý/controller byte-identical với v2.
- [Bản ghi prelaunch](governor_isolated_cadence_v2_run_2026-10-23/prelaunch_failure.json)
  giữ riêng; không đổi frozen v2 để che lỗi.

## 3. Batch v3 đã chạy đúng một lượt

Lịch vẫn là 2 block × PI/100ms/20ms × 2 repeats, trần 12; attempt 1 PI,
seed 77600, repeat 1. Domain 132, localhost discovery, partition riêng;
cold start, hai acquisition process, không tác động hardware.

| Kết quả attempt 1 | Trạng thái |
|---|---|
| Native physical outcome | **Success**, arrival khoảng 16,600 s |
| Reset zero/standstill | Gate riêng đã đạt |
| Native replay | Khớp; RMS slip native 0,01207877139999635, 166 bước |
| Readiness đầu lượt | Hai logger đạt, PID khác nhau |
| End marker đã nhận | Cả hai file ACK khớp chính xác expected end/run ID |
| Runner end/lifecycle gate | **Không đạt**: `Stale logger status: primary` |
| Closure cuối | Cả hai closed, error=null, PID không đổi |
| Cửa sổ stopping 2 s theo runner | **Chưa xác nhận (`null`)** |
| Measurement view | Không được admit/tạo; không dùng primary thay joint/GT riêng |
| Performance comparison | **Không được phép** |
| Cleanup | Runner xác nhận; không còn process simulation thuộc batch khi kiểm tra |

Summary executor ghi `hard_stop_setup_pass` vì `setup_pass=false` tổng hợp
từ runner. Nguyên nhân thực ở cuối lượt là end ACK timeout, không phải bằng
chứng robot đã thất bại reset hoặc crossing. `hard_stop_reason` chi tiết còn
ghi stopping integration chưa xác nhận. Không sửa tên/status cũ để làm đẹp.

Collector có thể sinh một số metric từ primary khi view chưa tồn tại.
**Các số đó không được admit cho comparison**; không dùng coverage primary
hoặc native replay để thay authority joint/GT của contract này. Analyzer
chính thức đã xuất `measurement_invalid_no_performance_comparison`, giữ
đủ 12 slot và native outcome.

- [Ledger nguyên trạng](../rl_runs/governor_isolated_cadence_v3_2026-10-23/ledger.json).
- [Summary nguyên trạng](../rl_runs/governor_isolated_cadence_v3_2026-10-23/summary.json).
- [Analysis không admit](governor_isolated_cadence_v3_run_2026-10-23/analysis/report.json).
- [Release trước launch](governor_isolated_cadence_v3_run_2026-10-23/execution_release.json).

## 4. Lỗi lifecycle đã khoanh vùng

Hai logger ghi immutable `*_end.json` tại lúc nhận terminal marker. Sau đó,
evaluator lưu native outcome và summary trước khi runner bắt đầu đợi ACK.
`wait_pair(marker=...)` đọc file ACK cố định rồi gọi `check_status`, vốn áp
giới hạn heartbeat hiện tại 2 s lên timestamp của ACK đó.

Trong artifact của lượt này:

| Nguồn | ACK khớp expected end | Summary file được ghi sau ACK | Closure cuối |
|---|---|---:|---|
| Primary | Có | khoảng **2,232 s** | Closed, error=null |
| Joint/GT | Có | khoảng **2,230 s** | Closed, error=null |

Các khoảng trên lấy từ file mtimes trên cùng máy; không phải instrumentation
đo chính xác lúc runner bắt đầu wait. Summary được lưu trước evaluator exit,
nên chúng cho thấy ACK đã già hơn giới hạn 2 s ngay trước runner wait.
Đọc lại cùng ACK bất biến trong deadline 10 s không thể làm nó mới hơn.

Đây là lỗi ngữ nghĩa kiểm tra receipt/liveness. Không có lịch sử mọi
heartbeat tại thời điểm lỗi để chứng minh rằng một validator đã sửa chắc
chắn sẽ cho lượt này đạt. Không suy tiếp rằng coverage/stopping/measurement
đã hợp lệ sau khi bỏ qua lỗi. Batch và kết luận invalid vẫn giữ nguyên.

[Diagnosis có cấu trúc](governor_isolated_cadence_v3_run_2026-10-23/lifecycle_diagnosis.json)
ghi PID, counts, ACK identity và các giới hạn suy luận.

## 5. Correction v4 đã tích hợp và fault-test

Thêm `check_delivery` vào acquisition lifecycle; `wait_pair` khi đợi marker
đọc **cả receipt lẫn status hiện tại**:

1. Receipt phải khớp session/protocol/source/role và marker chính xác;
   kiểm tra receipt tại timestamp được ghi của nó.
2. Status hiện tại phải cùng PID/output/identity/source với receipt,
   ready/open/error-free và heartbeat không quá **2 s**.
3. Receipt không được mới hơn status; status phải chứa marker đó trong
   lifecycle, hai stream vẫn có counts/stamps không lùi so với receipt.
4. Pair vẫn phải gồm hai process khác nhau; reset/end exactness, deadline
   **10 s**, không bước world trong wait, closure/provenance cuối vẫn giữ.
5. Readiness đầu lượt vẫn dùng source age **100 ms**. Marker ACK tiếp tục
   chứng minh delivery, không trở thành một sampling gate mới khi clock pause.

Không tăng timeout, bỏ kiểm tra stale process, điền gap, giảm coverage,
sửa score hoặc thay controller. Correction làm rõ **đối tượng nào phải
fresh**; nó được version riêng, không áp ngược để cứu batch v3.

Phương án ban đầu qua 17 fault-test offline. Sau tích hợp, suite hiện có
**140 test đạt**, bao gồm delayed ACK/fresh heartbeat, stale/future/closed/
error process, sai PID/output/session/source, foreign/missing marker,
receipt ở tương lai, thiếu/lùi stream, cùng native replay, epochs, coverage,
cadence, stopping và fault fixtures cũ. Không có smoke simulation thêm.

## 6. Contract hiện tại và bước tiếp theo

- Contract: **`isolated_joint_gt_cadence_v4_2026_10_23`**.
- [Protocol v4](governor_isolated_cadence_contract_v4_2026-10-23/protocol.json).
- SHA-256: `36845e6aa41c1b984b325ebe891b05c2a9d9059be24d15f751a0b7d7ed586ac9`.
- Source hiện tại đã validate với v4. Frozen v2/v3 và result vẫn giữ;
  không mong source hiện tại tiếp tục khớp runtime hashes của revision cũ.
- Các input robot/controller/world và schedule vẫn giống v3. Sampling,
  native scoring 100 ms, coverage ≥98% từng window và stop 2 s giữ nguyên.
- Chưa release budget hoặc launch v4. Không còn slot được tiếp tục từ v3.

**Việc cần tiếp theo là live integration của v4 trong một ngân sách mới có
giới hạn**, không audit lại slip của attempt PI này. Trước đó phần sửa
software đã làm xong. Không cần mọi dữ liệu thật để xác nhận lifecycle sim;
nhưng không thể dùng software test thay integration.

Khi có phép đo hợp lệ, vẫn trả lời theo thứ tự: earlier command → actual
wheel/body response trước contact sau → crossing/tracking/time. Hiện cả ba
contrast đều chưa có dữ liệu mới; ngưỡng 10% / +0,5s vẫn chỉ là đề xuất.

## 7. Kiểm tra lại không chạy simulation

```bash
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
export PYTHONPATH="$PWD/src/nino_rl:$PWD/src/nino_control:$PWD/src/nino_rl/scripts${PYTHONPATH:+:$PYTHONPATH}"
python src/nino_rl/scripts/prepare_isolated_cadence_contract.py --validate docs/governor_isolated_cadence_contract_v4_2026-10-23
python -m pytest -q src/nino_rl/test/test_acquisition_contract.py
```

Native outcomes, failures, slots và source snapshots v3 được giữ nguyên;
[manifest run đã đóng](governor_isolated_cadence_v3_run_2026-10-23/closed_run_sha256.json)
cho phép kiểm tra không bị sửa sau diagnosis.
