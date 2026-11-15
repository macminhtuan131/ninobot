# Sửa lỗi train: Gazebo startup timeout sau 200 episode

Ngày 09/11/2026. Runtime repair cho **common103_v2 hiện có**, không phải
triển khai task gờ không biết/tới goal vừa chọn.

## Lỗi quan sát được

Lượt `20261109T040059394334Z_common_v2_multiseed_11_22_33_train`, seed11,
DR `box_c1_6mm_dr`,50.000 bước, thất bại khi SB3 tự reset sang episode200:
`TimeoutError: Factory startup deadline; retain launch.log`.
Seed22/33 chưa chạy; campaign giữ failed, không sửa thành completed.

- `environment_trace`:28.000 transitions, episode199 đã có terminal outcome.
- `training_trace`:27.999 transitions. Terminal step cuối bị chặn bởi reset
  lỗi trong `DummyVecEnv` trước callback/replay insertion.
- `coverage.json` chỉ27.989 do chu kỳ ghi; không dùng nó làm số bước cuối.
- Checkpoint đầy đủ có10k và20k; bản20k có20.000 replay entries và9.999
  critic updates tại ranh giới được lưu. Không có checkpoint27.999/28k;
  không thể dựng lại weights/optimizer sau20k chỉ từ trace.

Episode200 nhận ROS IMU16.209, wheel161.691, GT16.208 và drive16.022 mẫu;
GT/IMU tới khoảng324,16 simulation seconds. Không có contact packets trên
Gazebo Transport, trong khi episode199 có. Launch log báo controller/motor
ready; chỉ có segfault khi teardown sau timeout, chưa phải bằng chứng nó
gây timeout đầu tiên. Chưa thấy bằng chứng lỗi loss/NaN ở exception này.

**Chẩn đoán:** đường subscription Gazebo stats/contact bị im lặng phù hợp
với dữ liệu; ROS telemetry vẫn chạy. Snapshot cũ không lưu clock và command
subscriber count tại timeout nên chưa quy chính xác cho một nguyên nhân UDP,
resource leak hay discovery. Không tăng deadline để che lỗi.

Upstream có báo cáo subscription im lặng cho tới khi unsubscribe/subscribe
lại trong Harmonic/gz-transport13, nhưng đó chỉ là cơ chế tham khảo, không
chứng minh Nino gặp đúng bug. [Issue gốc #985](https://github.com/gazebosim/gz-transport/issues/985).
API unsubscribe cũng được đối chiếu với Python binding đã cài và
[tài liệu Transport13](https://gazebosim.org/api/transport/13/python.html).
Tra cứu09/11/2026.

## Đã sửa

1. **Startup backend riêng cho Studio:** ghi `startup_diagnostics.json`:
   counts, clock/iterations, command subscribers, zero request và các sự kiện.
   Khi ROS đã đủ nhưng stats vẫn im8s, đăng ký lại stats/contact **tối đa một
   lần khi command zero và chưa vào task**; nếu vẫn im15s thì fail rõ.
   Không retry world-control/physics request, không vá subscription trong
   task hoặc bỏ freshness/support gates. Cleanup unsubscribe rõ trước đóng.
   Frozen backends của các thí nghiệm cũ không bị sửa.
2. **Deferred reset:** single-env TD3 `train_freq=1step` lưu terminal
   observation/done vào replay trước khi bắt đầu world tiếp theo. Nếu startup
   tiếp theo lỗi, checkpoint interrupted giữ ranh giới model/replay hợp lệ.
   Không mở một world thừa sau transition cuối cùng của budget.
3. **Resume có provenance:** strict source check vẫn giữ. Chỉ cho phép
   migration cặp source hashes cụ thể đã khai báo cho startup/reset repair,
   giữ nguyên controller/ABI/action/reward/profile/motor. Bundle cũ giữ
   nguyên; bundle dẫn xuất có receipt riêng, không khai là bit-exact resume.
4. GUI ghi rõ common103_v2 vẫn dùng planned stop6/8, chưa phải unknown-step
   goal task. Test GUI campaign không còn phụ thuộc dung lượng ổ thật;
   runtime disk gate không bị hạ. Hiện fresh campaign50k×3 với checkpoint
   interval5k ước tính cần27,46GiB, trong khi còn khoảng25,6GiB: nếu chọn
   như vậy GUI phải từ chối, không tự xóa dữ liệu lỗi để đủ chỗ.

## Kiểm chứng và giới hạn

- **121 tests đạt**, gồm TD3/SB3 thật trên synthetic env bị lỗi reset:
  terminal transition vẫn có trong replay; model/counter/replay save-load
  khớp; reset thành công dùng đúng observation mới; không reset sau budget.
- **Hai Gazebo fresh launches, chỉ zero**: một lần chủ động chặn stats lúc
  startup, một lần bình thường. Case fault đăng ký lại đúng1lần và nhận được
  clock, case thường không rearm;4zero ticks/targets,0actor/optimizer/forward,
 0physics-request retries, cả hai close sạch.
- Test hai startup không chứng minh độ tin cậy200episode hay campaign50k.
  Cải thiện log lỗi trước cả khi tạo publisher được kiểm ở software path;
  không lấy nó làm một experiment contact mới.
- Build `nino_rl`/`nino_pi` đạt. Gain/current/reward/history/geometry không
  đổi; E2 ledger6/6 và task selection gờ không biết giữ nguyên.

## Checkpoint phục hồi đã chuẩn bị

```text
/home/tuanmac/nino_research/td3_recovery_20261109/checkpoint_20000/
```

`model.zip`,replay,optimizer/targets và metadata gốc khớp hash bản20k.
Đã load bằng TD3 CPU, kiểm20.000 global steps/replay entries,9.999 updates,
identity đúng và tất cả bốn networks finite; không chạy learning mới.

Request tiếp30.000 bước seed11 được chuẩn bị tại:

```text
/home/tuanmac/nino_research/td3_recovery_20261109/resume_seed11_30000.json
```

Để tiếp **đúng task common103_v2 cũ** trong Studio: chọn checkpoint thư mục
trên hoặc `model.zip`, bật Resume, giữ seed11/profile/map DR và nhập30.000
bước thêm, tắt multi-seed. GUI/worker sẽ kiểm migration và disk trước chạy.
Không dùng bundle này để tự chuyển sang task unknown-step goal; task đó còn
cần scorer/adapter/reward/termination mới theo
[hướng đã chọn](NINO_UNKNOWN_STEP_TASK_DIRECTION_2026-11-09.md).

**Chưa khởi động lại campaign hoặc request resume.** Giữ log/raw/checkpoint
cũ và không chạy seed22/33 thay người dùng. Phần chuẩn bị phục hồi không
được tính là đã học xong50k hoặc có kết quả evaluation thắng baseline.

Artifact:
`/home/tuanmac/Documents/Codex/2026-10-27/stm32-n-i-v-i-pi/artifacts/studio_training_startup_repair_2026-11-09/`.
