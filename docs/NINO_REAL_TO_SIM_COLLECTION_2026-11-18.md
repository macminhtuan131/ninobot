# Thu dữ liệu thật cho Sim trên Pi .112

Dùng Pi `d@192.168.0.112`. Bộ thu riêng nằm tại
`/home/d/nino_runtime/real_to_sim_collection_20261118_v1`.
Bộ này ghi dữ liệu từ stack đang có. Người vận hành chạy bài thử bằng
stack thật đã kiểm tra. Recorder không phát trajectory hoặc bật motor.

## Chọn dữ liệu cần thu

| Mục đích trong Sim | Đã có bằng chứng gì | Cần thu thêm và cách lấy |
|---|---|---|
| Response từ final command đến reported wheel | Sáu bag Nav2 velocity ngày 17/11, đã dùng diagnostic replay | Lặp tiến-dừng cùng sàn, tải, caster và backend. Giữ raw command, wheel, status và thời gian từng giai đoạn. |
| Geometry và quán tính | Config khai báo radius 0,060 m, track 0,345 m, chưa là số đo hiệu dụng | Đo riêng hai bánh, tâm tiếp xúc, khối lượng/vị trí tải, kích thước và caster. Ghi phương pháp và sai số. COM/inertia chưa đo giữ unknown. |
| Chuyển động thân xe | Có odometry và AMCL | Không camera vẫn đo endpoint bằng mốc sàn/thước. Muốn trajectory, tốc độ, slip hoặc stopping theo thời gian cần reference độc lập được kiểm và đồng bộ riêng. |
| IMU/noise và vibration | Raw IMU có sẵn. Snapshot 17/11 là mounting identity/XYZ zero, khác hồ sơ 27/10 yaw +90° | Xác minh tư thế/trục trước dùng body XYZ. Thu đứng yên để xem bias/noise, rồi giữ IMU từng trial. Không tự sửa raw/TF. |
| Shaping, mode và giới hạn motor | Có final command, nav source, smoother, status | Giữ config/source thực dùng, owner, watchdog, mode và limits. Target/current/torque đo độc lập chưa có giữ null. `hardware.local.json` hiện thuộc nhánh torque, không xác nhận mode velocity của lượt mới. |
| Gờ, dây, hõm và dốc | Bag sàn Nav2 chưa xác nhận các contact này | Sau nhóm sàn sạch, đo geometry/slope, vật liệu, độ mềm, cách cố định, hướng tiếp cận, caster/tải và kết quả mỗi lượt. Giữ cả failures. |
| Bối cảnh navigation | Có map, plan, initialpose, goal và action status trong bag 17/11 | Profile velocity đã bổ sung các topic này ở mức optional. Sao lưu map/YAML và config/launch thật. AMCL vẫn là estimator. |

Ngày 18/11 đã kiểm read-only sáu bag ngày 17/11 trên Pi. Tổng message từ
SQLite khớp metadata ở cả sáu. Kiểm này không giải mã lại mọi message,
không xác nhận coverage hoặc live sensor readiness. Snapshot tại workspace
phát triển là `artifacts/real_to_sim_collection_20261118/pi_retained_inventory.json`.

[Review velocity 18/11](REAL_TO_SIM_VELOCITY_REVIEW_2026-11-18.md) vẫn chưa
promote fit vào physics. Bánh trái kém đối chứng ở một holdout. Giữ physics
danh nghĩa đến khi có kiểm chứng trên các phiên giữ lại.

## Mở bộ thu và kiểm sensor

Trên laptop, vào Pi bằng key đang dùng.

```bash
ssh -o StrictHostKeyChecking=yes -i "$HOME/.ssh/nino_pi_flash_ed25519" d@192.168.0.112
```

Trong terminal Pi, source môi trường stack thật.

```bash
source "$HOME/nino-real-test/scripts/env.sh"
export NINO_CAPTURE_TOOLS="$HOME/nino_runtime/real_to_sim_collection_20261118_v1"
export PYTHONPATH="$NINO_CAPTURE_TOOLS${PYTHONPATH:+:$PYTHONPATH}"
printenv ROS_DOMAIN_ID RMW_IMPLEMENTATION ROS_AUTOMATIC_DISCOVERY_RANGE
ros2 topic list -t
ros2 topic info /cmd_vel --verbose
ros2 topic info /motor_fb --verbose
/usr/bin/python3 -m nino_pi.hardware_audit \
	--duration 30 \
	--output "$HOME/nino_audits/real_to_sim_$(date -u +%Y%m%dT%H%M%S)_$$"
```

Giữ domain/discovery giống terminal driver. Không tự đổi domain vì topic
list trống. `env.sh` source overlay, không khởi stack. Audit chạy đứng yên
khi người vận hành kiểm soát robot. Nếu thiếu sensor, kiểm stack thật trước.

Đọc `REPORT.md`, `report.json`, `graph.json`, `tf.json`, `parameters.json`
và `power.json`. Kiểm mapping/đơn vị wheel theo driver, publisher command,
headers/clock, TF và cảnh báo nguồn. Count/rate không xác nhận encoder đúng
dấu hoặc không mất gói.

## Chuẩn bị một thư mục cho mỗi lượt

Trong cùng terminal Pi, tạo config và annotation mới.

```bash
mkdir -p "$HOME/nino_collection_sessions"
export NINO_CASE="$(mktemp -d "$HOME/nino_collection_sessions/wheel_$(date -u +%Y%m%dT%H%M%S)_XXXXXX")"
cp "$NINO_CAPTURE_TOOLS/config/real_collection_velocity_sysid.json" "$NINO_CASE/topics.json"
cp "$NINO_CAPTURE_TOOLS/config/real_collection_qos.yaml" "$NINO_CASE/qos.yaml"
cp "$NINO_CAPTURE_TOOLS/config/wheel_response_session.template.json" "$NINO_CASE/session.json"
cp "$NINO_CAPTURE_TOOLS/config/body_reference_observation.template.json" "$NINO_CASE/body_reference.json"
cp "$NINO_CAPTURE_TOOLS/config/real_to_sim_trial.template.json" "$NINO_CASE/trial.json"
/usr/bin/python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path
p = Path(os.environ['NINO_CASE'])
for name in ('session.json', 'body_reference.json', 'trial.json'):
    value = json.loads((p / name).read_text())
    value['session_id'] = p.name
    if name == 'session.json':
        value['date_utc'] = datetime.now(timezone.utc).isoformat()
    (p / name).write_text(json.dumps(value, indent=2) + '\n')
print(p)
PY
nano "$NINO_CASE/session.json"
nano "$NINO_CASE/trial.json"
```

Điền sàn/tải/caster, protocol/limits, controller/mode, firmware có bằng
chứng, geometry, uncertainty và nhóm lặp. Chốt split và condition trước
khi xem kết quả. Không chia hàng của cùng session vào cả fit và holdout.
Unknown giữ `null`, không điền zero thay thế.
[Field guide](../src/nino_pi/REAL_SESSION_FIELD_GUIDE.md) giải thích từng trường.

Profile mặc định ghi 60 giây. Chọn thời lượng bao trọn baseline, chuyển
động và hậu dừng, tối đa 300 giây theo collector. Đổi topic/QoS theo endpoint
thực. Muốn chứng minh toàn chuỗi Nav2, đặt các tầng thực sự có như
`/cmd_vel_nav` và `/cmd_vel_smoothed` thành required trong bản `topics.json`.
Không thêm publisher giả để điền kênh sự kiện.

Để ghi bag đứng yên trước, dùng `config/stm32_usb_collection.json` và
`config/real_session.template.json` từ bộ thu. Đặt stage là inventory đứng
yên. Profile inventory không yêu cầu command có sample lúc idle. Nó vẫn
yêu cầu raw IMU, motor feedback/status, `/scan_raw` và static TF.

Lưu config/launch thực dùng và map vào `$NINO_CASE/config_snapshot`.
Lấy từ stack hiện tại, không dùng config bag 17/11 như config đang chạy.
Ghi path/SHA256 vào `trial.json`. Với tham số đổi trong runtime, lưu thêm
`ros2 param dump /TEN_NODE_THUC_TE` của node đó. Không dump credentials
hoặc toàn bộ môi trường shell.

## Kiểm đầu vào rồi ghi raw

```bash
/usr/bin/python3 -m nino_pi.collect_real_data \
	--config "$NINO_CASE/topics.json" \
	--session "$NINO_CASE/session.json" \
	--qos "$NINO_CASE/qos.yaml" \
	--output "$NINO_CASE/raw" --check
```

`--check` chỉ đọc config và in kế hoạch. Nó không mở node, kiểm sensor sống,
kiểm motion release hoặc enforce `preflight_required_topics`.

Ghi phiên bằng lệnh sau. Kết thúc đủ thời lượng giúp recorder đóng metadata.

```bash
/usr/bin/python3 -m nino_pi.collect_real_data \
	--config "$NINO_CASE/topics.json" \
	--session "$NINO_CASE/session.json" \
	--qos "$NINO_CASE/qos.yaml" \
	--output "$NINO_CASE/raw"
```

Sau khi recorder đang nhận baseline, người vận hành chạy bài thử bằng nguồn
điều khiển thật đã kiểm. Dùng một trial mỗi bag cho nhóm tiến-dừng. Giữ điều
kiện ban đầu giống nhau, đoạn ramp, hold, zero và hậu dừng. Chỉ đổi một điều
kiện mỗi nhóm. Số lượt, tốc độ, ramp, khoảng cách và giới hạn dừng lấy từ
protocol được chấp nhận cho robot hiện tại. Proposal 0,05 m/s trong profile
chưa là motion release.

Recorder dừng hoặc Ctrl+C không dừng robot. Dùng cơ chế dừng của stack thật.
Giữ trial bị ngắt, abort và spike. Không tự retry để thay kết quả xấu.

## Đo thân xe khi không có camera

1. Đánh dấu điểm cố định trên thân. Ghi vị trí marker và hệ trục mốc sàn
   trong `body_reference.json`.
2. Đo XY và hướng ban đầu bằng thước/mốc. Ghi độ chia dụng cụ, phương pháp
   và uncertainty. Đo lại cùng marker sau khi xe đã đứng yên.
3. Đặt `reference_method=manual_endpoint`. Điền `manual_endpoint`,
   `reference.body_displacement_m` và bằng chứng người quan sát. Để speed,
   latency, slip là null. Giữ các QC định lượng theo thời gian là false.

Endpoint chỉ đo dịch chuyển đầu-cuối. Không chia cho thời lượng bag rồi
gọi đó là response speed hoặc stopping distance từ lúc zero command.
Bán kính lăn hiệu dụng chỉ đo trong trial gần thẳng, có tải, đã kiểm ít
slip, dùng góc bánh cùng khoảng đầu-cuối và ghi uncertainty.

Nếu có trajectory LiDAR/tracker đã kiểm độc lập, điền `time_series_reference`
với file gốc, frame, clock, calibration, sai số và đoạn mất tracking. Ghi
mọi phụ thuộc encoder/IMU. `/odom`, AMCL hoặc scan deskew dùng encoder
không tự trở thành body ground truth độc lập.

## Xác minh IMU và đo vật cản

Pi có `collect_imu_frame.py` và `evaluate_frame.py` tại
`~/nino_runtime/real_prepare_20261109_v2`. Trong ROS/domain đúng, kiểm import.

```bash
/usr/bin/python3 "$HOME/nino_runtime/real_prepare_20261109_v2/collect_imu_frame.py" --check
```

Khi drive đã được người vận hành xác nhận không tạo mô-men và có thể đỡ
robot chắc chắn, chạy file đó không có `--check`. Công cụ hỏi xác nhận và
hướng dẫn LEVEL, NOSE_UP, LEFT_SIDE_UP, mỗi tư thế 5 giây. Giữ output và nhãn
tư thế. Gravity khi nằm ngang không phân biệt yaw 0 với +90°. Phép kiểm này
không đo translation mounting hoặc gyro scale.

Với nhóm gờ/dây/hõm/dốc, điền `scenario` trong session trước mỗi lượt.
Đo chiều cao/độ sâu, bề rộng, bán kính/edge, khoảng cách vật cản, góc tiếp
cận và slope. Dây mềm cần vật liệu, đường kính, độ căng, cách cố định và
biến dạng. Ghi contact quan sát cùng uncertainty, không suy thời điểm chính
xác từ spike IMU. Thiếu phép đo thì thứ tự contact/caster angle/force giữ unknown.

## Ghi sự kiện và kiểm sau mỗi lượt

Điền `events` trong `trial.json` bằng cấu trúc `event_entry_template`.
Ghi origin, clock, boot ID, phương pháp sync và uncertainty. Dùng trace
command thật để ghi thay reference theo bag receipt. Sự kiện người quan
sát phải có nhãn operator và sai số. Receipt không là thời gian STM32
thực thi hoặc thân xe bắt đầu đáp ứng.

```bash
cat "$NINO_CASE/raw/manifest.json"
ros2 bag info "$NINO_CASE/raw/bag"
cat "$NINO_CASE/raw/audit/REPORT.md"
```

Kiểm closure/hash, type, wheel mapping/units, source/receipt clock,
duplicate/backward stamps, gaps và coverage toàn baseline/ramp/hold/zero/hậu
dừng. Count tổng khớp chưa đủ. Phiên velocity có request `/cmd_torque` hoặc
`/cmd_mit` giữ làm diagnostic, loại khỏi fit velocity-only, kể cả request zero.

`captured_not_calibrated` chỉ kiểm storage/process/topic cơ bản. Nó chưa
chấm timing, body truth hoặc calibration. Mốc 150 ms và 10 Hz trong replay
18/11 thuộc phép replay đó, không là QC chung cho mọi thí nghiệm.

Giữ `$NINO_CASE/raw` nguyên sau khi có `sha256.json`. Bổ sung outcome,
body reference, events và config evidence bên ngoài raw. Lưu SHA256 của
`raw/manifest.json` và `raw/sha256.json` trong `trial.json`, rồi seal các
annotation bằng hash riêng. Không sửa session đã được collector copy.

Sau khi điền xong annotation, chạy đoạn sau trên Pi. Đoạn này kiểm các file
raw, nối bằng chứng vào trial và tạo hash annotation. Hai khóa source trong
raw hash manifest là hash mã nguồn, không phải đường dẫn file dữ liệu.

```bash
/usr/bin/python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
p = Path(os.environ['NINO_CASE'])
raw = p / 'raw'
hashes = json.loads((raw / 'sha256.json').read_text())
for name, expected in hashes.items():
    if name in ('collector_source', 'audit_source'):
        continue
    actual = hashlib.sha256((raw / name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit('Raw hash mismatch: ' + name)
trial = json.loads((p / 'trial.json').read_text())
for key, name in [('raw_manifest_path_sha256', 'raw/manifest.json'),
                  ('raw_sha256_manifest_path_sha256', 'raw/sha256.json'),
                  ('body_reference_path_sha256', 'body_reference.json')]:
    trial[key] = {'path': name, 'sha256': hashlib.sha256((p / name).read_bytes()).hexdigest()}
(p / 'trial.json').write_text(json.dumps(trial, indent=2) + '\n')
files = [p / name for name in ('session.json', 'topics.json', 'qos.yaml',
                              'body_reference.json', 'trial.json')]
files += sorted(q for q in (p / 'config_snapshot').rglob('*') if q.is_file())
sealed = {str(q.relative_to(p)): hashlib.sha256(q.read_bytes()).hexdigest() for q in files}
(p / 'annotation_sha256.json').write_text(json.dumps(sealed, indent=2) + '\n')
print('Raw file hashes match. Saved annotation_sha256.json.')
PY
```

## Lấy dữ liệu về và đưa vào Sim

Trên laptop, lấy cả thư mục trial, gồm failures và annotation.

```bash
mkdir -p "$HOME/nino_real_data_imports"
scp -r -o StrictHostKeyChecking=yes -i "$HOME/.ssh/nino_pi_flash_ed25519" \
	d@192.168.0.112:/home/d/nino_collection_sessions/TEN_THU_MUC_LUOT \
	"$HOME/nino_real_data_imports/"
```

Kiểm hash sau copy. Không phát bag command lên mạng đang nối motor.
Giữ real gốc, derived SI units và metadata provenance riêng.

Trên laptop, đặt `NINO_CASE` thành thư mục vừa tải rồi kiểm cả hai manifest.

```bash
export NINO_CASE="$HOME/nino_real_data_imports/TEN_THU_MUC_LUOT"
/usr/bin/python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
p = Path(os.environ['NINO_CASE'])
for base, manifest in [(p / 'raw', 'sha256.json'), (p, 'annotation_sha256.json')]:
    hashes = json.loads((base / manifest).read_text())
    for name, expected in hashes.items():
        if manifest == 'sha256.json' and name in ('collector_source', 'audit_source'):
            continue
        if hashlib.sha256((base / name).read_bytes()).hexdigest() != expected:
            raise SystemExit('Hash mismatch: ' + str(base / name))
print('Raw and annotation file hashes match after copy.')
PY
```

`nino_rl.real_velocity_replay` hiện pin holdout IDs và geometry cho sáu
phiên 17/11. CLI đó chưa nhận tùy ý trial mới. Đừng đổi tên trial mới thành
ID cũ hoặc chèn vào exporter lịch sử. Khi đủ nhóm mới, cần khai báo
split/geometry mới và adapter xuất dữ liệu có kiểm trước fit. Teleop/SysID
không tự là TD3 replay. Template vẫn giữ `physical_calibration_accepted=false`
và `td3_replay_eligible=false`.

## Phạm vi bổ sung lần này

Giữ collector hiện có theo **Laziness Protocol**. Bổ sung form no-camera,
events và các topic context đã thấy trên Pi. Theo **Prove It Works**, kiểm
form bằng collector trên laptop/Pi và đối chiếu hash bộ copy. Kiểm đầu vào
không thay phép thu vật lý hoặc qualification của robot.
