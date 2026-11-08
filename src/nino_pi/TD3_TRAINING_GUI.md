# Train TD3 trong Nino Studio

## Dung lượng và lưu dữ liệu — 08/11/2026

- Mặc định bật **Tiết kiệm ổ đĩa**: sau khi job common hoàn tất thành công
  và worker đã đóng, Studio xóa các thư mục `episodes/episode_N/` của train.
  Việc dọn chạy nền, giữ mọi checkpoint hoàn chỉnh (model, optimizer trong
  ZIP, replay và identity), TensorBoard, evaluation, hai trace cấp job,
  reset metadata và thống kê episode. Không đổi observation/reward/engine.
- Tab **Phiên đã chạy / checkpoints** có nút **Xóa raw episode train của
  phiên đang xem** để dọn một phiên common đã hoàn tất. Không tự dọn legacy,
  phiên lỗi/cancel, job chạy ngoài GUI hoặc dữ liệu robot thật.
- `storage_retention.json` ghi danh sách file đã xóa và hash từ manifest
  gốc. Manifest gốc giữ nguyên như hồ sơ lịch sử; sau dọn không còn đủ raw
  để kiểm lại toàn bộ phép đo episode. GUI hiện rõ giới hạn này. Dashboard
  và phân tích từ trace vẫn dùng được. Đây không phải loại bỏ episode xấu
  khỏi số liệu: mọi transition/outcome trong trace vẫn giữ nguyên.
- Chỉ dọn **sau** job; dung lượng cực đại trong khi train và kiểm tra disk
  đầu job vẫn như cũ. Không dựa vào tùy chọn này để giảm ngân sách disk.
- Công cụ CLI `python3 -m nino_pi.training_storage <job>` mặc định chỉ xem
  kế hoạch; thêm `--apply` mới xóa. Nó dùng cùng khóa simulator, kiểm hash
  checkpoint/trace và chỉ nhận job common mô phỏng đã hoàn tất.

> **Cập nhật07/11 — mặc định common103D/1D:** chọn contract/trainer ngay
> trong tab này. Common hiện chỉ chạy sàn sạch, Ki0,10, stop6/8s; evaluation
> gồm6lượt B0/classical/TD3. Research replay32.768, warmup10.000, budget tối
> đa20.000steps/job. Nút tham số common xem effective profile riêng; legacy
> vẫn mở editor draft cũ. Resume không đổi engine/profile hoặc tiếp A/C đã đóng.
> [Smoke đã chạy và pilot tiếp theo](../../docs/NINO_COMMON_STUDIO_PILOT_2026-11-07.md).
> Các chi tiết100D/2D, replay1M và eval2arm bên dưới chỉ áp dụng khi chọn Legacy.

## Mở giao diện

```bash
bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh --train
```

Hoặc mở Studio hiện có và chọn tab cấp cao **Train TD3 · Sim**.
Shortcut cũ `td3_training_gui` / `scripts/td3_training_gui.sh` cũng mở
cùng Studio, không tạo GUI training riêng. `--output` của shortcut cũ được giữ.
Không cần Pi; worker dùng `.venv` của repo, ROS Jazzy và Gazebo trên laptop.
GUI dùng Python hệ thống/PyQt5; ML chạy trong process riêng.

## Thao tác

1. Chọn thư mục lưu và map: **sàn sạch** hoặc **gờ 6 mm**. Đây là controlled
   factory fixtures, chưa phải full mixed factory map.
2. Bấm **Smoke test · 64 bước mới** để kiểm pipeline bằng một model mới,
   profile smoke h5. Smoke không sửa checkpoint đang chọn. Checkbox đánh
   giá bật thì thêm B0 và TD3, mỗi arm một lượt 14 giây mô phỏng.
3. Để train theo ngân sách của bạn: chọn profile, nhập **Timesteps học thêm**,
   seed, khoảng lưu checkpoint và wall-time tối đa; bấm **Train TD3 mới**.
   Form đề xuất research h5/20.000bước; đây không là ngân sách bảo đảm hội tụ.
   Số bước không phải số episode hoặc số giây chạy thực.
4. Theo dõi progress/global steps/log. Tab **Kết quả / metric** ghi số bước,
   optimizer updates, replay, checkpoint và metric B0/TD3 nếu đã đánh giá.
   Lỗi có traceback và exit code; không tự retry. Lỗi đánh giá vẫn giữ
   kết quả train và checkpoint hoàn chỉnh trước đó.
5. Bấm **Mở TensorBoard**. GUI khởi chạy server trên `127.0.0.1`, tự chọn
   port trống và mở trình duyệt; **Tắt TensorBoard** đóng server do GUI tạo.
   Log gồm reward, velocity error, cross-track, body speed, số bước và
   losses TD3 khi có optimizer updates. Mỗi job có run log riêng.
6. Để học tiếp: **Chọn checkpoint…** chọn `model.zip`, hoặc chọn bundle tại
   **Phiên đã chạy / checkpoints → Dùng checkpoint…**. GUI đọc metadata,
   chọn đúng map/profile/seed và khóa các trường đó. Nhập số bước **thêm**,
   rồi bấm **Tiếp tục TD3 · học thêm**. Ví dụ global64 +32 → global96.
7. **Dừng + giữ checkpoint** yêu cầu dừng ở ranh giới transition đã ghi.
   Chờ worker đóng simulator và lưu bundle; không đóng cưỡng bức process.
   Nếu lỗi giữa transition, dùng checkpoint hoàn chỉnh trước đó, không coi
   file `.pending` là checkpoint hợp lệ.

## Profile và resume

- `nino_td3_smoke_h5_v1`: MLP32×32, warmup16, batch32, replay2048.
- `nino_td3_research_h5_v1`: MLP256×256, warmup10000, batch256, replay1M.
  GUI chặn Train và giải thích nếu số bước fresh không vượt warmup, vì chưa
  có bước cập nhật. Resume tính cả global steps cũ; số updates thực tế vẫn
  được ghi trong kết quả. Profile nghiên cứu không tự tạo bằng chứng hội tụ.
- Cùng observation h5/100D, residual common/differential wheel-linear,
  projection và guided task/reward V3. Chưa có lựa chọn h1/h8 hoặc đổi
  action schema trong console này. **Khác contract common103D/1D của A seed11**;
  tích hợp GUI không làm hai checkpoint tương thích.
- Nút **Xem tham số / lưu draft để tune trong Studio** mở editor đã có trong
  cùng cửa sổ, chọn cùng profile. Draft chưa tự áp vào job; không đổi tham số
  của checkpoint đang resume. [Cách chọn/tune tham số](../../docs/NINO_STUDIO_TRAINING_INTEGRATION_2026-11-07.md).
- Resume nhận **Studio checkpoint bundle** hoặc checkpoint train guided V3
  lịch sử không đổi. Bare actor/weights ZIP, PPO, V1/V2 hoặc sai
  task/baseline/ABI/profile/scenario/seed bị từ chối.
- Worker kiểm model **và replay**, hashes, runtime, task identity và counters
  trước khi học. Load giữ actor, target networks, critics, optimizer và replay;
  không zero-init lại model đã học.
- Resume bắt đầu episode Gazebo mới; không khôi phục physics/caster/RNG để
  chạy bit-exact trajectory. Checkpoint lưu tại rollout boundary có thể nằm
  trước optimizer call kế tiếp; `optimizer_updates` ghi trạng thái thật.

## Artifact mỗi job

```text
~/nino_research/td3_studio/<timestamp>_<smoke|train>/
  request.json, job.json, manifest.json, engine_sources.json
  training_config.json, training_trace.jsonl, start_state.json
  training_result.json, result.json                 # khi tương ứng hoàn tất
  error.txt                                       # khi lỗi/hủy
  tensorboard/events.out.tfevents.*, progress.csv
  checkpoints/step_<global>_<periodic|final|interrupted>/
    model.zip, replay_buffer.pkl, checkpoint.json
    task_checkpoint.json, resume_identity.json, manifest.json
  backend/                                        # raw + launch/physics logs
  evaluation/{B0,TD3}/                             # nếu bật đánh giá
```

Full stdout GUI ở thư mục cha `ui_logs/`, tách khỏi manifest job đã đóng.
Raw trace giữ trên đĩa; audit replay giữ tối đa256 rows cuối trong RAM và
kiểm đúng ring-buffer index. Không giữ tất cả trace trong RAM khi train dài.

## Phạm vi kết luận

Smoke/checkpoint/evaluation chạy được là bằng chứng tích hợp phần mềm.
Một lượt B0/TD3 trên map đã xem không xác nhận learned benefit, generalization
hoặc sim-to-real. Đoạn train cuối có thể dừng giữa episode và được ghi là
right-censored. Các batch khoa học cũ vẫn khóa; console tạo job mới với số
bước người vận hành nhập, không ghi đè hoặc mở lại slot cũ. Không phát lệnh
robot thật; studio và các job sim cũ dùng cùng resource lock.

Đối chiếu API với source SB3 cài trong `.venv` và tài liệu chính thức:
[TensorBoard](https://stable-baselines3.readthedocs.io/en/master/guide/tensorboard.html),
[save/load](https://stable-baselines3.readthedocs.io/en/master/guide/examples.html).
Tra cứu05/11/2026; thực thi dùng phiên bản local được ghi trong manifest.
