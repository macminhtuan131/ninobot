# Kết quả: contract TD3/cổ điển cùng preview103D/1D

05/11/2026 · **Đã triển khai và qualification offline qua nút GUI.**
Không có train, optimizer, Gazebo, physics request hoặc thao tác robot thật.
Đây là bước phần mềm sau [stop-time transfer](NINO_SIM_STOP_TRANSFER_RESULT_2026-11-05.md).

## 1. Đã làm và chưa chứng minh gì?

**[N — source/software]** Có config/ABI mới, adapter shared window, Gym
wrapper và replay audit cho common-only. Cả TD3 và classical nhận schema
103D giống nhau: history100D causal +countdown source stop +window flag +
request scalar trước đó. Countdown withdrawal suy từ stop và lead0,5s chung.
Actor xuất scalar1D∈[−1,1], tương ứng request common±0,005m/s; differential0,
yaw follower vẫn hoạt động. Legacy pipeline/PI/projection không bị sửa.

**[N — qualification]** Kiểm thành công840 synthetic fixture transitions,
280 replay rows, zero-init scalar head/target và save/load model/critics/
targets. Optimizer state rỗng và mọi trọng số giữ nguyên. Đây không là
840lượt/bước Gazebo hoặc kết quả policy đã được học.

**[S]** Contract giải quyết được bất đối xứng preview trong thiết kế cho
phép so sau này; chưa chứng minh TD3 có lợi thế hoặc cần thiết. Current
clear6/8s đã có baseline cổ điển tốt; remaining gap dưới gain/lag thay đổi
vẫn là giả thuyết. Không tạo randomization tùy ý để làm baseline yếu.

**[Đ]** Bước tiếp là [qualification wrapper trong Gazebo](NINO_SIM_EQUAL_INFORMATION_GAZEBO_NEXT_2026-11-05.md),
draft tối đa4launches/560ticks/optimizer0, chưa triển khai hoặc chạy. Sau
integration mới chốt bounded learner pilot theo remaining gap, objective,
profile/seeds/timesteps và split. Không cần đợi real data để làm Sim; cũng
không tự mở train chỉ vì có phần mềm mới.

## 2. Khác biệt so với nhánh V3

| Hạng mục | V3/Studio hiện có | Contract mới đã kiểm offline |
|---|---|---|
| Observation |100D=20×5 |103D=100history+2plan+previous requested scalar |
| Action |2D common/diff, scale0,04m/s |1D common, request bound0,005m/s |
| Planned stop |Actor không nhận preview tương ứng |Cùng packet kế hoạch cho cả hai controller |
| Shared withdrawal |Chưa là rule chung cho arm frozen |Window chung trước planned stop0,5s |
| Replay action |Proposal2D của task cũ |Request scalar1D trước gate; mapped2D giữ riêng |
| Reward action cost |Normalized theo scale0,04m/s |Giữ thang vật lý0,04m/s, q=0,125a |
| Checkpoint |V3/Studio100D/2D |Identity mới; reject V3, chưa có model đã train |

Model offline `inspection_model_untrained.zip` và file
`synthetic_replay_do_not_train.pkl` không phải bundle train/resume. Chưa nối
trainer103D/1D vào tab TRAIN TD3 cũ. Tab đó vẫn phục vụ V3 theo scope trước;
GUI mới nói rõ sự khác biệt, không giả vờ một nút cũ đã train ABI mới.

Trong trace mới, top-level `policy_proposal` và `abi_sha256` thuộc103D/1D;
`inherited_policy_proposal`, `inherited_abi_sha256` và reference trace100D
giữ semantics của adapter cũ. Không gắn ABI cũ lên replay mới.

## 3. Fixture và những phép kiểm đã đạt

Ba arm phần mềm B0/classical/proposal probe ×hai stop6/8s ×140ticks=840.
Probe là chu kỳ deterministic−1/0/+1, không policy được train.

| Stop | Arm | Fixture ticks | Window mở | Request khác0 bị window chặn |
|---|---|---:|---:|---:|
|6s |B0 |140 |31 |0 |
|6s |Classical |140 |31 |0 |
|6s |Probe |140 |31 |72 |
|8s |B0 |140 |51 |0 |
|8s |Classical |140 |51 |0 |
|8s |Probe |140 |51 |59 |

131 request khác0 ngoài window được giữ trong trace/replay đúng semantics;
mapped proposal lúc đó0. Replay280 rows của probe giữ cả requested action,
observation/next observation, reward và terminal/timeout, save/load khớp.
Fixture yaw0 có source từ0,5s nên nominal steady2,4s. **Correction sau
qualification Gazebo05/11:** source Gazebo cũng bắt đầu0,5s; yaw follower
nhỏ cùng wheel-ramp làm nominal v tại2,4s còn dưới0,2m/s, window mở2,5s.
Diễn giải cũ “source muộn một tick” sai và được sửa theo trace mới/cũ. Test
rule parity trên cùng source vẫn khớp; không thêm delay giả hoặc sửa raw.

24 contract/control tests đạt, gồm:

- Shared preview/window, zero source và history/owner/stale/fault/latch gates;
  GT/contact/caster thêm vào label không đổi actor input/action.
- Chống prepare hai lần, invalid action không clip im lặng, reset không
  carry history/nominal/request hoặc clock giữa episodes.
- Previous **requested** scalar hiện trong observation cả khi gate chặn,
  nên reward action-change không phụ thuộc một lệnh cũ bị che.
- Reward cost giữ cùng physical scale khi đổi biên action; không tăng
  penalty64lần do chuẩn hóa action mới. Cost request không bị xóa bởi gate.
- Deadline thật terminal; external timeout giữ next observation thuộc
  continuing MDP để bootstrap. Không giả đóng window tại truncation.
- Scalar head actor zero, target đồng bộ, save/load mọi network và empty
  optimizer state. Test chặn `.learn()` và `Adam.step()` vẫn qualify được.
- ABI/task/scale khác và V3 checkpoint bị từ chối; ledger đã có không retry.

19 GUI tests đạt; có kiểm đọc đúng artifact cho cả profile mới và profile
stop-transfer. Đã sửa thiếu ánh xạ file của nút **Xem kết quả** stop-transfer.
Mở GUI không chạy job; bấm nút qualification mới thực sự chạy worker và
đóng exit0, kiểm manifest rồi khóa rerun. Screenshot có10profile,6×5table
fixture; TRAIN TD3 và profile lịch sử vẫn riêng.

Initial failing test assumptions và một lượt test bị ngắt khi phát hiện
hash validation lặp theo từng reward tick đều được giữ trong QA. Đã chuyển
validation cấu hình sang lúc khởi tạo scorer; batch chính thức chạy sau
các correction này, không retry/bù slot physics hoặc giấu failure.

## 4. Provenance và giới hạn

Root:
`/home/tuanmac/nino_research/sim_equal_information_v1/20261105T115115446610Z_sim-equal-contract`.

- Fingerprint module/config/script/parent:
  `67bb76d3983535e6114c54532e7a9bb52bdef90639cff50a6c3c17bcfaecf86b`.
- ABI SHA256:
  `b8c71ccb876cb6f2f5ab66d08d74d9b3d8cfdbfac22ccfc3b326da16b5a2e6e0`.
-13artifact files và101prelaunch source files khớp SHA256 trước cập nhật hồ
  sơ kết quả.840trace rows được audit thêm requested/mapped/ABI/causal preview/
  reward, không dùng count/hash như bằng chứng chất lượng vật lý.
- History chuyển sang float32 có sai khác lớn nhất≈1,48×10⁻⁸ so trace double
  cũ, dưới tolerance2×10⁻⁶ của replay audit; không đòi bitwise double equality.
- Frozen stop-transfer và các parent source/config/script giữ fingerprint.
  Dữ liệu thật cutoff02/11, real data mới0; không SSH, motor enable hoặc
  command ownership changes. Kiểm này không là sim-to-real calibration.

[Verification](NINO_SIM_EQUAL_INFORMATION_VERIFICATION_2026-11-05.json)
giữ build/source-install parity, XML tests, worker/gui và source snapshot.
QA: `artifacts/sim_equal_information_2026-11-05/` trong workspace thread.

## 5. Điểm dừng và một việc kế tiếp

Minimum worthwhile effect, conditions/split/final test budget và timesteps
per training seed vẫn chưa chốt. Seeds11/22/33 trong config chỉ là đề xuất;
không có3learner seeds mới hoặc ngân sách train đã mở. Những unknown này
không cấm qualification/tuning cổ điển có contract riêng. Có thể chọn
engineering objective tạm minh bạch cho bounded Sim pilot mà chưa có yêu
cầu nhà máy hoàn chỉnh; không gọi nó là deployment acceptance.

**Một việc kế tiếp:** triển khai qualification wrapper103D/1D trong Gazebo
theo draft4launches, kiểm plan/source/scorer và request→reference trên
backend hiện có. Đạt thì thiết kế learner pilot; sai thì sửa adapter đúng
nguyên nhân hoặc giữ baseline. Không chạy một loạt tiny comparisons chỉ
để có thêm lần baseline thắng, hoặc dùng TD3 training che integration lỗi.
