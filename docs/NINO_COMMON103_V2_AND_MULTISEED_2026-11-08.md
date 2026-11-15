# common103_v2 — triển khai thử nghiệm, chưa đủ bằng chứng để train dài

> E1 sau correction đã hoàn tất: 280 train steps, 2 full episodes, 6 development evaluations. [Kết quả](NINO_COMMON103_V2_INTEGRATION_RESULT_2026-11-08.md). Chưa có performance/generalization gate để chạy dài; phần smoke64 bên dưới là lịch sử trước E1.

Rà soát lại ngày 08/11/2026. Phần kết luận trước đây đã được sửa; bản trước
sửa nằm trong artifact `project_reassessment_2026-11-08/before/` của workspace.

## Đã có trong code

- Engine v2 độc lập; history 5 mẫu ở 10 Hz, observation 103D, action common
  residual 1D. Không phải predictor hoặc contact governor đã chứng minh.
- Reward v2 bỏ request cost khi cửa sổ đóng, lưu previous effective scalar.
  Đây là thay đổi objective có chủ ý, không phải chứng minh critic đã tốt hơn.
- Replay research 100.000; cap mỗi job 100.000 bước. Replay SB3 là buffer vòng:
  buffer 32.768 của v1 ghi đè transition cũ khi đầy, không phải lỗi tràn bộ nhớ.
  Tăng capacity là lựa chọn nghiên cứu, chưa chứng minh tăng hiệu quả học.
- Có `clear_box`, gờ cứng 6 mm `box_c1_6mm`, DR có biên
  `box_c1_6mm_dr`. Các biên DR là giả thiết Sim, chưa hiệu chuẩn hardware.
- Classical scheduled vẫn Ki0.10 và common bù +0,005 m/s. Cùng biên projector
  không bảo đảm đây là baseline đủ mạnh trên gờ; chưa so với Ki0.15 hoặc
  classical/reactive đã tune trên benchmark mới.

## Bằng chứng thực sự đã có

Smoke gốc `common_studio_v2_smoke_20261108/20261108T150300694579Z_common_v2_seed11_smoke`:
64 transition, 48 critic updates, 24 actor updates; 34 tick đóng cửa sổ không
thu request penalty. **0 episode hoàn chỉnh, không chạy evaluation**, đoạn
cuối bị cắt. Vì vậy chưa xác nhận task completion, stop, DR robustness hoặc
TD3 hơn baseline. Smoke này có trước correction bên dưới; không gọi nó là
kiểm runtime cho code sau correction. Bundle gốc được giữ nguyên.

## Các correction sau rà soát

1. Metric jerk tính đạo hàm bậc hai của accepted velocity reference, đơn vị
   m/s³; acceleration riêng m/s². Đây không phải body jerk hoặc tải hư hại.
2. Saturation dùng tốc độ target từng bánh × radius so với wheel speed cap;
   không dùng hằng số 12 rad/s² của giới hạn acceleration làm speed cap.
3. Missing target, clock gap và stop không quan sát đủ là error/unknown;
   task failure không bị chia nhỏ thành tỷ lệ tick để trông ít nghiêm trọng.
4. Campaign tính cả ba seed, trace giữ lại, raw peak trong seed, checkpoint,
   evaluation và reserve. Dọn sau seed không giảm peak của chính seed đó.
5. Retention dùng API công khai có khóa, ghi inventory/receipt trước unlink,
   kiểm stat và đóng các seed còn lại nếu cleanup lỗi. Không dùng `_plan`
   rồi unlink trực tiếp và bỏ qua lỗi.
6. Smoke từ GUI luôn single seed, kể cả checkbox campaign đang bật. GUI
   hiển thị tổng bước/disk/wall cap campaign và nhận diện worker/event v2.

## Giới hạn evaluation và lựa chọn checkpoint

Evaluation hiện tại là B0/classical/TD3 × hai lịch dừng 6/8 s trên **cùng
map danh nghĩa**. Với DR, evaluation vẫn dùng gờ danh nghĩa, không lấy mẫu
DR. Hai lịch dừng cũng được dùng khi train. Gọi đây là **development
evaluation**, không phải test bank độc lập hoặc bằng chứng DR generalization.

Campaign chỉ đề cử checkpoint cuối của learner seed có metric development
tốt nhất. Chưa đánh giá các checkpoint periodic; chưa có validation/test
split riêng. Kết quả tổng hợp giữ mọi seed và ghi
`EXPLORATORY_ONLY_INDEPENDENT_TEST_REQUIRED`, `benefit_verified=false`.
Chọn seed tốt nhất trên cùng dữ liệu rồi báo thắng là selection bias.

## Cách dùng kế hoạch dài

`common103_v2_multiseed_50k_box_c1_6mm_dr.json` là **request template**, không
phải bằng chứng đã cấp/chạy 150.000 bước, thời gian hoàn tất hoặc đã qua
gate vật lý. Không tự khởi chạy trong lượt review này. Trước campaign cần:

1. Kiểm runtime code sau correction bằng một protocol integration có cap.
2. Chốt benchmark gờ, đối chứng classical đủ mạnh và control authority còn
   tác động kịp; không thêm DR/history/reward/action scale đồng thời để tune.
3. Khóa validation/test bank và cách chọn checkpoint, ràng buộc task/stop,
   missing/failure, minimum useful effect và ngân sách disk/thời gian.
4. Sau pilot học có optimizer thực, mới quyết định ngân sách dài/đa seed.

Nguồn thuật toán: [SB3 ReplayBuffer](https://github.com/DLR-RM/stable-baselines3/blob/master/stable_baselines3/common/buffers.py)
và [hướng dẫn evaluation](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html).
Code thư viện cài local được đối chiếu khi review; không nâng phiên bản thư viện.

Xem [đánh giá và outline tiếp theo](NINO_PROJECT_REASSESSMENT_2026-11-08.md).
