# Recovery v3 đã chạy smoke TD3 trong Gazebo

Ngày 16/11/2026. Yêu cầu là tiếp tục sửa đến khi mô phỏng thực sự chạy được. Đợt này đã hoàn thành smoke TD3 Gazebo 384 bước trên sàn sạch và gờ cứng thấp. Chưa chạy train dài hoặc phần cứng.

## Kết quả đã kiểm

| Phép kiểm | Kết quả |
| --- | --- |
| Transition Gazebo trả về và lưu replay | 384 / 384 |
| Replay tải lại từ checkpoint và đối chiếu với trace | 384 hàng khớp observation, action, next observation, reward, done và timeout |
| Critic update | 368 |
| Actor update | 184 |
| Segment | 3 segment × 128 bước, thứ tự clean, short_obstacle, clean |
| Kết thúc segment | Cả ba bị cắt theo ngân sách smoke. Không phải ba lượt đến đích |
| Raw source QC | Đạt cho cả ba segment |
| Source identity và đóng tiến trình | Đạt |
| Model tải lại và inference deterministic | Đạt, trọng số hữu hạn, action một chiều hữu hạn trong giới hạn |
| Kiểm thử phần mềm liên quan | 214 tests đạt |

Root thành công là `/home/tuanmac/nino_research/recovery_v3_paced_smoke_20261116_02`.

Checkpoint cuối là `/home/tuanmac/nino_research/recovery_v3_paced_smoke_20261116_02/checkpoints/step_000384_77cc18df`. Bundle chứa model, replay, identity, RNG, state scheduler, QC và hash. Inspector chấp nhận bundle ở biên episode. Entry point live resume vẫn chưa được mở, và ngân sách smoke 384 bước này đã dùng hết. Không gọi đây là checkpoint đã được phép tiếp tục một campaign dài.

Các số update được đọc từ model tải lại, không suy ra từ số bước yêu cầu. Mức thay đổi tham số actor chỉ chứng minh optimizer đã cập nhật, không chứng minh controller tốt hơn.

## Hai lỗi đã sửa

### Physics tiến nhanh hơn vòng PI ROS xử lý

Lượt trước có khoảng drive source 52 ms nhưng producer chỉ báo ba PI update, max raw dt 40 ms. Chỉ chờ feedback ở cuối hai chunk physics 50 ms không ngăn ROS timer bỏ nhịp.

Phép kiểm mới chạy chính `EffortDrive` với clock tổng hợp trên domain localhost riêng. Arm burst có max PI dt 66 ms. Arm paced giữ 2 ms trong 47 cửa sổ được kiểm. Đây là phép phân biệt cơ chế scheduling, không có contact physics.

World recovery mới dùng native `real_time_factor=0.2`, giữ physics 1 ms, PI cấu hình 500 Hz và policy 100 ms. Không thêm sleep sau khi physics đã chạy. Raw native world-control cho thấy mỗi chunk 50 ms thực sự được pace, median khoảng 0,298 giây thực ở smoke này. Toàn bộ khoảng đo là từ 0,2511 đến 1,4610 giây thực, gồm cả chunk chậm nhất. Không dùng số này làm cam kết deadline phần cứng.

Giữ nguyên source gate 40 ms. Thêm kiểm producer PI tối đa 4 ms, từ chối dt không hợp lệ, fallback hoặc feedback tương lai trước khi environment trả transition cho learner. Cả 1.920 cửa sổ PI của ba segment smoke có min/max raw dt đúng 2 ms, tổng 19.200 PI update. Tuổi wheel feedback lớn nhất mà PI báo là 2 ms. Không bỏ spike hoặc nội suy dữ liệu.

Đây là conformance quan sát trong lượt hữu hạn. Chưa đo ACK tiêu thụ effort ở native controller, chưa chứng minh hard realtime hoặc zero-delay actuation. Chuỗi ROS effort tới native write vẫn có độ trễ vận chuyển.

### Replay verifier bọc dư action một lớp

Smoke paced đầu giữ được một hàng replay hợp lệ về nguồn, rồi dừng ở so sánh shape. Adapter hiện hữu phát `requested_scalar_action` dưới dạng vector một phần tử `[a]`. Verifier lại so với `[[a]]`. Fixture cũ ghi scalar nên bỏ sót lỗi tích hợp này.

Sửa một phép so sánh trong `recovery_training.py`, giữ nguyên action ABI. Fixture giả dùng đúng schema. Thêm test đi qua `RecoveryEnv` thật và backend wheel lý tưởng tới SB3, thay vì tự tạo trace. Test tái hiện đúng lỗi trước sửa và chạy đủ 384 hàng sau sửa. Không đổi projection, reward, learning rate, history hoặc action scale.

Lượt lỗi `/home/tuanmac/nino_research/recovery_v3_paced_smoke_20261116_01` giữ nguyên. Nó có 1 hàng lưu, 0 hàng được verifier chấp nhận, 0 critic update và 0 actor update. Diagnostic checkpoint không được qualify.

## Qualification của source cuối

B0 đã chạy lại sau sửa verifier, vì contract hiện ghim toàn bộ source, gồm cả trainer. Không sửa source pins cũ để dùng lại qualification.

Root hiện hành là `/home/tuanmac/nino_research/recovery_v3_paced_20261116_02`. Mỗi hàng sau là một layout development ở stage 0, cruise 0,2 m/s, route 4 m.

| Family | Task | Thời gian mô phỏng | Sai số đích cuối | Cross-track RMSE | Moving speed RMSE |
| --- | --- | ---: | ---: | ---: | ---: |
| Sàn sạch | Đạt đích và quiet stop 2 s | 27,1 s | 0,02010 m | 0,002455 m | 0,005390 m/s |
| Gờ cứng thấp | Đạt đích, một clearance và recovery, quiet stop 2 s | 27,1 s | 0,02339 m | 0,006647 m | 0,007770 m/s |

Raw QC, producer timing và hash đạt. Đây là kiểm tích hợp hữu hạn. Không có CI hoặc kết luận độ lặp từ một layout.

## Dốc và hõm vẫn là việc riêng

Trong root paced 01 trước sửa verifier, dốc 3° có source/timing hợp lệ và đã vượt qua, hồi phục, nhưng kết thúc cách đích 0,05801 m. Gate đích vẫn là 0,05 m nên lượt này timeout 40 s và không qualify cho smoke. Không chạy lại dốc để tìm một kết quả thuận lợi.

Ở thời điểm goal-stop latch, estimator báo XY khoảng `[3,97166; -0,00430]`, còn physical XY khoảng `[3,94753; 0,02454]`. Sai số XY khoảng 0,03761 m. Đây là bằng chứng mismatch navigation/odometry tại thời điểm dừng, chưa xác định riêng cơ chế gây drift. Không phải lỗi optimizer TD3. Hình học dốc, tải caster và sai số tích phân cần được phân biệt bằng dữ liệu nguồn.

Hõm và mixed chưa mở lại. Kết quả hõm cũ và lỗi goal latch được giữ trong [báo cáo trước](RECOVERY_SIM_READINESS_2026-11-16.md). Không coi smoke hai family hiện tại là bằng chứng giải quyết hõm hoặc toàn bộ đề tài.

## Việc tiếp theo

1. Phân tích drift theo phase cho dốc và đối chứng mesh nền của hõm. Chỉ sửa một nguyên nhân có bằng chứng, giữ gate đích và bám đường. Không thêm GT vào actor hoặc follower.
2. Nối engine recovery v3 vào Studio bằng identity riêng. GUI Goal100 lịch sử chưa phải engine này.
3. Trước campaign dài, chốt sampler vị trí vật cản chưa biết, layout validation/test và protocol so classical với TD3. Chỉ mở family có câu hỏi và gate phù hợp. Không cần đổi đồng thời learning rate, reward, history và action scale.

Đã có bằng chứng hệ thống sim và learner chạy cùng nhau. Chưa có bằng chứng TD3 thắng classical, tổng quát hóa vị trí vật cản, xử lý dây mềm hoặc chuyển sang robot thật.

## Artifact và review

Artifact chính ở `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_drive_timing_2026-11-16/`.

- `protocol.json`, `protocol_v2.json` và `decisions.tsv` giữ câu hỏi, thứ tự chạy, lỗi và thay đổi phạm vi smoke sau qualification.
- `source_after_action_fix.zip` và bảng SHA256 giữ snapshot source cuối.
- `clock_fixture/` giữ hai arm clock, diagnostic và log producer.
- `pytest_action_shape_before.xml` giữ test đỏ. `pytest_after_action_fix.xml` giữ 214 tests xanh.
- `baseline_summary.json` giữ cả dốc không đạt. `baseline_v2_summary.json` giữ qualification source cuối.
- `smoke_runtime_summary.json` kiểm 130 file manifest, raw source, PI timing và native chunk của smoke.
- `verify_live_checkpoint.py` và `checkpoint_verification.json` tải lại model/replay, kiểm 384 hàng và inference.
- `REVIEW.md`, `ACTION_TRACE_REVIEW.md` và `FINAL_REVIEW.md` ghi phạm vi và giới hạn review độc lập.
- `cleanup.json` ghi không còn tiến trình của chín Gazebo partition thuộc đợt này, sim lock đã rảnh. Không có thao tác phần cứng.

Các reviewer thuộc cùng họ GPT khả dụng. Chưa có review chéo họ model. Giới hạn native effort ACK, dốc, hõm và lợi ích thuật toán còn mở.

`Fix Root Causes` dẫn tới sửa pacing physics thay vì hạ source gate. `Model the Domain` gom pacing vào một config có identity và giữ action theo đúng shape hiện hữu. `Sequence Work into Verifiable Units` giữ qualification trước learner. `Explain the Number` tách prefix lỗi, segment bị cắt và số optimizer update thật. `Prove It Works` yêu cầu tải lại checkpoint, đối chiếu replay và chạy inference từ artifact cuối.
