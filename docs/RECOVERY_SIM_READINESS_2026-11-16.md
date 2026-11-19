# Recovery v3. Kiểm phần mềm và lượt Gazebo đầu tiên

> Cập nhật tiếp theo cùng ngày. [Smoke TD3 Gazebo đã đạt 384 bước](RECOVERY_SIM_PACING_AND_TD3_SMOKE_2026-11-16.md). Các kết quả lỗi trong tài liệu dưới đây là lịch sử và được giữ nguyên.

Ngày cập nhật 16/11/2026. Công việc bắt đầu 15/11. Mục tiêu là kiểm các nút chặn trước khi train Nino vượt gờ cứng, hõm và dốc nhẹ, bám đường và giữ tốc độ. Không có thao tác phần cứng hoặc train dài trong đợt này.

## Kết luận hiện tại

Đã chạy Gazebo thực sự. Trong protocol v2 riêng, B0 sàn sạch, gờ thấp và dốc 3° đạt arrival, quiet stop và raw QC. Pothole có raw hợp lệ nhưng không đến đích. Một smoke TD3 Gazebo đã được khởi chạy sau qualification của ba family đạt. Smoke dừng ở transition đầu vì drive source gap 52 ms vượt gate 40 ms, chưa có hàng replay hoặc optimizer update. Không lấy software smoke 384 bước làm số bước train Gazebo.

Đã sửa nguyên nhân timestamp trong một overlay `controller_manager` cô lập và sửa phép kiểm thư viện cho tiến trình con tạo session riêng. Mapping ELF đã được xác minh trong các lượt Gazebo v2. Protocol đầu đóng sau một correction và lỗi ownership. Protocol v2 được khai báo riêng sau probe cross-session, không gộp hoặc thay lượt lỗi cũ. V2 cũng đã đóng sau lỗi drive gap, không chạy bù. Chưa train dài.

## Những gì đã kiểm và sửa

| Phần | Bằng chứng và thay đổi | Giới hạn |
| --- | --- | --- |
| Khởi tạo estimator | Raw cũ cho thấy robot lăn khi khởi động, trước epoch task. Backend mới tích phân wheel và gyro đã nhận trước quyết định đầu tiên, từ pose spawn khai báo. Clean 02 đạt endpoint bound 0,272175 mm dưới gate 8 mm. | Truth chỉ dùng để chấm. Không sửa pose bằng truth hoặc hạ gate. Prefix trước mẫu wheel đầu tiên được ghi riêng. |
| Input startup lỗi | Phiên cũ readiness 02 có hai wheel payload khác nhau cùng stamp 0,004 s. Bootstrap từ chối. Readiness 03 không có lỗi này và replay hợp lệ. | Không loại mẫu để biến phiên lỗi thành đạt. |
| Trainer nhiều episode | Thêm `recovery_training.py` và `recovery_training_contract.py`. Một lifecycle sở hữu các launch, scheduler theo family, curriculum riêng, source admission trước reward/replay và deferred reset sau khi lưu terminal row. | Entry point này là smoke hữu hạn, không phải campaign train dài. |
| Replay và checkpoint | Test chạy TD3 thật với backend giả cho 384 transition qua ba segment 128 bước. Đối chiếu observation/action/next observation/reward/done/timeout. Bundle có hash, model, replay, identity, scheduler, curriculum và RNG. | Backend giả không có contact physics. Live resume vẫn bị từ chối rõ ràng; restore mới được kiểm bằng fixture. |
| Timestamp publisher | Clean 02 có hai wheel sample khác giá trị cùng stamp 19,444 s trong cả primary và recorder độc lập. Lỗi xảy ra trước reward của bước 147. | 146 bước không phải một lượt đến đích. Không qualify family hoặc checkpoint từ prefix này. |
| Clock dependency | Probe C++ dùng ROS clock đứng ở 1 s và mười `update(time)` tăng dần. Thư viện gốc lặp 1 s/period 0. Bản vá trả đúng 1,01..1,10 s/period 10 ms. Kiểm ELF thật qua `/proc/self/maps`. | Không chạy toàn bộ upstream test suite. Chưa chứng minh mọi controller async hoặc mọi simulator. |
| Kiểm thư viện được nạp | Lượt 03 tìm theo process group nên bỏ sót Gazebo do `gz_sim_clean` dùng `start_new_session=True`. Đã đổi sang ancestry của launcher và exact Gazebo partition, vẫn bắt buộc đúng path/hash. Probe cross-session và mapping trong các lượt root 04 đạt. | Lượt 03 giữ trạng thái failed. Root 04 là protocol/source riêng. |
| Lý do dừng job | Smoke lỗi vẫn ghi nhãn mặc định `transition_budget`, dù status/error và replay 0 đã đúng. Đã sửa reason theo exception/closure/QC/replay/identity; thêm test lỗi ngay bước đầu. | Không sửa artifact lỗi cũ. Thay đổi reporting sau runtime tạo source identity mới, chưa được qualify lại. |
| Test fixture cũ | Tách test lifecycle khỏi frozen stop-transfer prerequisite. Bổ sung `control_timing.reset` vào fixture reset odometry. | Không sửa hoặc bỏ gate production lịch sử. |

204 test liên quan đạt sau sửa cuối, với ROS Jazzy và `.venv`, gồm control, recovery, terrain, observation/action, lifecycle, replay, startup và runtime overlay. Trong đó có 26 test trainer, gồm test mới lỗi trước transition đầu. Đây không phải tuyên bố mọi test lịch sử trong toàn repository đều đạt.

## Overlay có thể tái tạo

Nguồn được ghim ở ros2_control commit `cdbc1127521074c2c5d19b4af2b73591e69d762b`, package 4.48.0. Bản vá chỉ đổi nguồn thời gian trong `ControllerManager::update`. ELF cục bộ có SHA256 `c421614a19bfb3bbb288cfa4ce83e518b948c62da1f957b7ce42bf924e0a5eab`.

- [Patch](../src/nino_rl/runtime/controller_manager_4.48.0_sim_time.patch) giữ thay đổi C++.
- [Build recipe](../src/nino_rl/scripts/build_recovery_clock_overlay.py) tải archive có hash, kiểm version, build package riêng và tạo manifest. Không ghi đè thư viện `/opt/ros`.
- [Runtime contract](../src/nino_rl/nino_rl/recovery_sim_runtime.py) kiểm manifest, patch/builder hash, ELF, launch ancestry và Gazebo partition.
- `.sim_dependencies/recovery_clock/` chứa ELF/manifest cục bộ và được bỏ qua bởi Git. Thiếu hoặc đổi dependency sẽ chặn live backend. Máy khác phải build và qualify lại.

Lệnh build hoặc kiểm overlay đã có, tại repository và trong terminal đã source ROS Jazzy.

```bash
rtk env PYTHONPATH=src/nino_rl:src/nino_control:$PYTHONPATH .venv/bin/python src/nino_rl/scripts/build_recovery_clock_overlay.py
```

Nguồn đối chiếu là [ros2_control issue 3683](https://github.com/ros-controls/ros2_control/issues/3683), [PR 3684](https://github.com/ros-controls/ros2_control/pull/3684) và [source đúng commit](https://github.com/ros-controls/ros2_control/blob/cdbc1127521074c2c5d19b4af2b73591e69d762b/controller_manager/src/controller_manager.cpp). Tra cứu 15–16/11/2026. Issue bên ngoài gợi ý cơ chế; raw Nino và probe ELF mới là bằng chứng cho chẩn đoán cục bộ.

## Trạng thái các gate

| Gate | Trạng thái |
| --- | --- |
| Software và replay fixture | Đạt phạm vi kiểm thử trên. |
| Startup wheel/gyro và gate 8 mm | Đã đạt một lần trong Gazebo clean 02. |
| Overlay mapping trong Gazebo sau sửa ancestry | Đạt trong root 04. |
| Baseline clean hoàn chỉnh, source QC hợp lệ | Đạt một lượt, 271 bước. |
| Gờ thấp và dốc 3° | Mỗi family đạt một B0, 271 bước. |
| Hõm | 400 bước, raw QC đạt, task timeout và motion quality không đạt. Blocked. |
| TD3 Gazebo 384 bước | Đã thử, failed trước hàng replay đầu. 0 critic/actor update. Không đạt integration gate. |
| Lợi ích TD3, generalization, sim-to-real | Chưa kết luận. |
| GUI engine recovery v3 | Chưa đăng ký. GUI Goal100 vẫn thuộc task lịch sử. |

## Thứ tự tiếp theo

1. Ưu tiên fixture cô lập clock/scheduling của PI ngoài Gazebo. Diagnostic nguồn tự báo chỉ 3 control callback trong 52 ms, max raw control dt 40 ms, thay vì cadence cấu hình 2 ms. Đây không chỉ là suy luận từ thiếu một message recorder. Backend đang advance physics theo hai chunk 50 ms rồi chờ endpoint; PI dùng timer ROS bất đồng bộ. Cần phân biệt clock delivery, timer scheduling và cách phối hợp physics/PI trước khi sửa. Không giảm gate 40 ms hoặc đổi learning rate để che lỗi.
2. Kiểm pothole từ raw theo phase trước khi thêm sensing hoặc train bù. Longitudinal estimator error tăng khoảng 0,5305 m; khoảng 71,79% phần tăng xảy ra sau geometric clearance. Chưa cô lập nguyên nhân ở riêng hõm. Đối chứng mesh nền tương ứng nhưng bỏ depression có giá trị hơn một lượt TD3 dài trên geometry chưa rõ.
3. Sau đúng một correction có căn cứ cho timing, dùng protocol mới để qualify backend cuối rồi thử lại smoke giới hạn. Root lỗi cũ vẫn đóng. Chỉ nhận family đủ evidence; pothole và mixed chưa mở. Gate 8 mm, gap 40 ms và goal 5 cm giữ nguyên.
4. Sau smoke đạt mới nối engine recovery riêng vào Studio. Trước train dài cần sampler thay vị trí vật cản có khoảng hồi phục, bank held-out và kế hoạch so B0/classical. Không dùng một layout development để tuyên bố vượt vật cản chưa biết. Chưa tăng dốc 4°/5°, đổi đồng thời reward/history/action scale hoặc cấp ngân sách train dài.

Điều kiện B0 trong smoke này là gate tích hợp nhỏ. Nó không phải lập luận rằng mọi nghiên cứu RL chỉ được phép học khi classical đã giải quyết mọi tình huống. Một nghiên cứu pothole khó hơn cần câu hỏi, envelope và phép kiểm quyền điều khiển riêng.

## Kết quả Gazebo của protocol v2

Mỗi hàng là một lượt development, không có CI hoặc kết luận độ lặp. Tốc độ cruise cấu hình 0,2 m/s trên tuyến 4 m. Speed RMSE dùng sai phân pose nguồn theo cửa sổ task, không là đỉnh rung.

| Family | Raw QC | Đích/dừng/task | Goal distance cuối | Moving speed RMSE |
| --- | --- | --- | ---: | ---: |
| Sàn sạch | Đạt | Đạt, quiet 2 s | 0,02320 m | 0,00560 m/s |
| Gờ thấp | Đạt | Đạt, quiet 2 s | 0,02336 m | 0,00837 m/s |
| Dốc 3° | Đạt | Đạt, quiet 2 s | 0,04208 m | 0,01170 m/s |
| Hõm | Đạt | Không đạt, timeout 40 s | 0,51412 m | 0,06509 m/s |

Pothole goal latch xảy ra ở task 24,5 s. Estimator báo X=3,97425 m nhưng physical X=3,44304 m, còn cách goal 0,55825 m. Cuối phiên sai số XY giữa hai nguồn khoảng 0,532 m. Scalar residual bị rút khi baseline zero nên không thể mở lại latch sau đó. Tránh drift trước latch là giả thuyết khác, chưa kiểm. Không gọi đây là slip thật của robot phần cứng hoặc kết luận cần mua cảm biến ngay.

Hình ở artifact `pothole04_stop_diagnostic.png` và dữ liệu ở `pothole04_stop_diagnostic.json`, `pothole04_error_by_phase.json`. Các mốc estimator/physical dùng cho phase audit khớp source stamp.

Smoke yêu cầu clean/gờ/dốc theo thứ tự, nhưng thực tế chỉ launch clean một lần và dừng trước transition đầu. Chưa chạy ba episode Gazebo như fixture. Diagnostic checkpoint tại step 0 có `qualified=false`, `resumable=false`; inspector kiểm hash và từ chối resume đúng. Các raw và manifest lỗi giữ nguyên.

Các baseline root 04 có source identity đóng băng riêng. Sửa nhãn dừng sau runtime không đổi physics/reward/action, nhưng full-source contract hiện vẫn từ chối tự kế thừa qualification sau bất kỳ source change. Không sửa pins cũ hoặc gọi evidence lịch sử là current-source qualification.

## Artifact và khả năng kiểm lại

Artifact đợt này ở `/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/recovery_gazebo_release_2026-11-15/`. Có hai protocol trước chạy, source archives, hash, decision trail, raw audit, review, C++ probe, cross-session probe và pytest XML. Các root 02, 03, 04 và smoke đều đóng. `runtime_summary.json` chứa kết quả B0; `live_smoke_drive_gap_audit.json` chứa gap và control counters. Không có tiến trình train chạy nền sau khi kết thúc đợt.

Reviewer là agent ở context độc lập, cùng họ GPT khả dụng. Review trước runtime đã bỏ sót giả thiết same-process-group; lỗi đó được ghi rõ và được bổ sung fixture cùng probe ELF thật. Không có review chéo họ model hoặc chứng nhận an toàn.

`Attack the Premise` dẫn tới kiểm chuyển động lúc settling thay vì cộng offset. `Fix Root Causes` giữ sửa timestamp ở producer. `Model the Domain` gom state episode và budget vào một owner. `Explain the Number` tách prefix 146 bước, fixture 384 bước và full-task qualification. `Sequence Work into Verifiable Units` giữ clean trước terrain trước learner. `Prove It Works` yêu cầu raw, ELF và replay thực, đồng thời giữ các kết quả chưa đạt.
