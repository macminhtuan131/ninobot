> **Cập nhật mới07/11 — pilot20k đã hoàn tất:** 20.000transitions,10.000critic/5.000actor updates;6/6eval đạt task/stop. Tốt hơn B0 trong screen, chưa chứng minh hơn classical. Đề xuất continuation10k, chưa chạy thêm. [Đánh giá và bước tiếp](NINO_COMMON_TD3_20K_ASSESSMENT_2026-11-07.md). Các trạng thái “đang chạy/chờ dung lượng” dưới đây là lịch sử.

> **Cập nhật07/11 — pilot research20k đã khởi chạy:** đã dọn cache tải gói pip để đủ dung lượng; fresh common103D/1D seed11 đang chạy. [Trạng thái và log](NINO_COMMON_STUDIO_TRAINING_RUN_2026-11-07.md). Các đoạn nói thiếu dung lượng dưới đây là trước khi dọn cache.

# TD3 common103D/1D trong Studio — pilot và kết quả tích hợp

Ngày 07/11/2026. Phạm vi: Sim trên laptop, không SSH/robot thật.

## Đã thực hiện

- Tab **Train TD3 · Sim** trong Studio mặc định chọn **common103D/1D**;
  legacy100D/2D vẫn có lựa chọn riêng. Một GUI, một runner; không dùng
  checkpoint chéo contract hoặc tiếp các root A/C đã đóng.
- Trainer mới tái sử dụng controller/score/history/projection đã frozen,
  giữ wheel PI **Ki=0,10**. Episode mới dùng drive ACK + physical quiet,
  recorder riêng và source-support gate 40 ms. Không đợi validation Ki0,15.
- Observation: history5 × 20 feature + 3 feature về **kế hoạch dừng đã biết**.
  Action: scalar common ±0,005 m/s qua window/projection; differential=0.
  Đây chưa phải governor nhận biết vật cản chưa biết sau contact.
- Replay lưu **requested scalar**, observation/next observation103D,
  reward/terminal/timeout; lệnh qua window/projection giữ riêng trong trace.
- Checkpoint atomic gồm actor/critics/targets/optimizers/replay, effective
  profile, source/runtime hashes. Resume tạo episode mới; không restore
  physics/caster/RNG chính xác. Profile smoke không đổi thành research khi resume.

Các module mới: `common_studio_contract.py`, `common_training_studio.py`,
`training_studio_api.py`; không sửa scientific controller hoặc protocol cũ.
Request v1 vẫn vào legacy; request v2 chỉ rõ `engine`.

## Bằng chứng mới

**22 software tests** đạt: gồm legacy regression và common path chạy SB3
thật trên plant tổng hợp; replay, updates, hai lịch dừng, checkpoint parity,
resume, failure/cancel/disk gate, 6 condition evaluator và actor purity.
Evaluator summary/timing trong fixture được mock, không phải kết quả Gazebo.
**42 GUI tests** đạt ở lượt regression cuối; build `nino_pi` và `nino_rl` thành công.

Một smoke Gazebo đã chạy, không retry:

| Đại lượng | Kết quả |
|---|---:|
| Map | `clear_box`, controlled factory fixture sàn sạch |
| Fresh learner | seed11, smoke MLP32×32, warmup16 |
| Training transitions / replay | 64 / 64 |
| Critic / actor optimizer updates | 48 / 24 |
| Replay audit trước và sau load | 64/64 |
| Gazebo launches | 1 |
| Window mở / action dương / âm trong window | 30 / 15 / 15 |
| Terminal hoàn chỉnh / eval ticks | 0 / 0 |
| Lifecycle | đóng thành công, không lỗi closure |
| Manifest | 50 file khớp SHA256 |

Artifact:
`~/nino_research/common_studio_smoke_20261107_v1/20261107T040758557366Z_common_smoke`.
Manifest SHA256:
`1d07d6e3bc0b3d5cb9d2c5097182aa43408750891119ad450aa9679050fcc1b8`.

Smoke cắt giữa episode, **không chứng minh crossing, stop outcome, convergence
hoặc hơn baseline**. Đây là learner mới, không cộng với A1024 hoặc C840 thành
một quá trình học. Checkpoint A và fingerprint validation PI cũ được kiểm
giữ nguyên. QA scripts/XML/screenshot/verification lưu trong workspace client:
`artifacts/common_studio_2026-11-07/`.

## Pilot training dài đã chuẩn bị, chưa chạy

| Phần | Ngân sách/cấu hình |
|---|---|
| Fresh research learner | seed11, không resume smoke/A/C |
| Training | 20.000 transitions, tối đa 144 fresh launches kể cả auto-reset cuối |
| Source schedule | luân phiên stop6/8 s, horizon14 s, 140 ticks/episode |
| Algorithm | LR0,0003; gamma0,99; tau0,005; MLP256×256; batch256 |
| Replay / warmup | **32.768 / 10.000**; profile common tách effective hash khỏi legacy replay1M |
| Updates | tối đa 10.000 critic/5.000 actor sau warmup nếu hoàn tất bình thường; báo counters thực |
| Checkpoints | mỗi5.000 bước thêm, final và khi dừng ở boundary hợp lệ |
| Evaluation | final checkpoint cố định; B0/classical scheduled/TD3 × stop6/8 = 6 launches/840ticks |
| Wall cap | 180 phút; không tự retry hoặc thêm bước nếu kết quả nhỏ/unknown |
| Hardware | 0 |

20.000 bước là **pilot có giới hạn**, không được coi là đủ hội tụ hoặc
multiple-seed confirmation. Không chọn checkpoint theo evaluation rồi
gọi cùng dữ liệu là holdout. Các condition6/8 đã xem, không là unseen test.

**Trở ngại hiện tại là dung lượng:** preflight ước tính cần **6,99 GiB trống**,
bao gồm dự phòng1 GiB; lúc kiểm còn **4,93 GiB**. Đây là dự toán từ raw episode
lịch sử với mức dự phòng40 MiB/launch, không phải upper bound bảo đảm.
Worker kiểm trước khi launch và dừng nếu còn dưới512 MiB trong quá trình.
Không tự xóa dữ liệu, giảm steps hoặc đổi profile sau khi gặp gate này.

## Tiếp theo theo thứ tự

1. Chọn output trên ổ/thư mục có ít nhất khoảng7 GiB trống; nên có dư thêm
   vì kích thước raw không cố định. Không cần thu real để mở nhánh này.
2. Trong Studio chọn **common103D/1D → sàn sạch → research h5**, bỏ Resume,
   seed11,20.000steps,checkpoint5.000,180phút; bật eval6condition rồi Train.
   Request mẫu: `src/nino_rl/config/common_studio_pilot_2026_11_07.json`
   và QA `pilot_request.json`; GUI tạo request riêng
   từ các trường đang hiển thị và kiểm disk/hash trước khi chạy.
3. Theo dõi TensorBoard: actor/critic loss, reward, velocity error, requested
   action và window. Xem `coverage.json`, trace/projection và số update thực;
   phần action nằm ngoài window không được coi là authority hữu ích.
4. Sau budget, xem task/stop/tracking, native velocity RMSE và hai GT grids
   ở mỗi condition; nếu đổi kết luận theo grid thì UNKNOWN. Không promote
   chỉ từ reward đẹp hoặc checkpoint tồn tại. Lỗi giữ nguyên raw/checkpoint,
   đóng job; không tự tạo lượt bù.
5. Chỉ sau review pilot mới chốt nhiều seed, tuning/ablation/history/OOD.
   Gate thắng baseline phục vụ promotion, không là điều kiện cho phép train.

Mở Studio: `bash ~/ninorobot/src/nino_pi/scripts/mode_gui.sh --train`.
Để xem smoke vừa chạy, chọn thư mục lưu `~/nino_research/common_studio_smoke_20261107_v1`,
bấm đọc lại phiên, chọn dòng hoàn tất; không bấm Train để xem kết quả.
