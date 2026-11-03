# Lệnh thu dữ liệu từ to-do GUI — 03/11/2026

## Cách dùng trong GUI

1. Mở GUI, điền IP/key ở phần kết nối; không cần kết nối chỉ để xem lệnh.
2. Tab **Tiến độ / kết quả / to-do → To-do**, chọn T07 rồi **Lệnh thu / Copy**; có thể double-click dòng.
3. Chọn phiên và bước; **Copy lệnh bước đã chọn**, dán vào đúng terminal ghi trong GUI.
4. Không dán toàn bộ hướng dẫn vào một terminal: terminal stack/recorder cần được giữ mở song song.

Lệnh mặc định bên dưới dùng `d@192.168.0.109`. GUI render lại theo IP/key hiện tại.
Lần chuẩn bị này không SSH, launch, flash, enable hoặc chạy robot. Bộ lệnh được kiểm offline; readiness thật có thể fail.

## Backend và giới hạn

- Diagnostic dùng firmware RC hiện có, cần RC AUTO; không phụ thuộc firmware GUI chưa nạp.
- Giữ +0,05 m/s, ramp 0,10 m/s², source 2 s, bag 60 s.
- Một namespace mới `collection_commands_20261103_v1`, tối đa một diagnostic do người vận hành gọi; không sửa hoặc mở slot cũ.
- Deploy chỉ copy, cùng version không reset ledger. START stack chỉ zero; RUN TRIAL mới enable/tiến.
- Readiness giữ STOP, freshness, owner, exact endpoint GID/type đã có bằng chứng. GID đổi cần review read-only; không auto nhận mọi anonymous endpoint.
- Record-diagnostic kiểm live trước allocation, giữ thao tác AUTO/pose/caster/video. Video phải thấy bánh/thân/mốc sàn; không tự xác nhận body khi source sequence xong.
- Các mục độ lặp/body-reference/navigation tương lai hiện tạo draft, không giả vờ có protocol motion đã release.
- Chờ recorder FINISHED trước reboot/tắt nguồn. Giữ lỗi/raw; không auto retry hoặc đổi gain/current.

## Artifact và đánh giá

`inventory/`: raw hardware audit. `nino_real_data/wheel_body_diagnostic_*`: nguyên bag/metadata/hash/events.
`reviews/<UTC>/`: raw_quality, analysis và trace khi có forward anchor; không sửa raw.
Fetch copy phiên cuối đã đóng và review (nếu có) về thư mục mới `~/nino_real_data_imports/<UTC>/`.
Video trên điện thoại/camera phải copy riêng; chưa có video hoặc đồng bộ thì body/slip/physical-stop giữ unknown.
Review tự động tối đa Q2, chưa tự pass window/body hoặc mở repeatability.
Nếu thiếu topic/endpoint/stack hoặc thông báo lỗi: giữ nguyên output và session; sửa theo lỗi thực, không force hoặc bỏ monitor.

## Kiểm kê cảm biến / backend

Chỉ đọc; không phát enable/vận tốc.

### 0 · Cài bộ lệnh vào Pi (một lần)

**Terminal:** Laptop  
**Tác động:** Chỉ copy

Không sửa firmware, không chạy stack. Cài lại cùng phiên bản không reset ledger.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy deploy --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

### 1 · Kiểm driver / topic

**Terminal:** Laptop  
**Tác động:** Chỉ đọc

Agent, bridge và LiDAR cần đang chạy như sensor stage trước đó. Nếu thiếu, giữ output lỗi để sửa; không tự flash.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" inventory'
```

## Đứng yên · thu 60 giây

Chỉ recorder; không ARM/tiến. Không cần lặp nếu chỉ muốn kiểm lại IMU sign.

### 0 · Cài bộ lệnh vào Pi (một lần)

**Terminal:** Laptop  
**Tác động:** Chỉ copy

Không sửa firmware, không chạy stack. Cài lại cùng phiên bản không reset ledger.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy deploy --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

### 1 · Kiểm driver / topic

**Terminal:** Laptop  
**Tác động:** Chỉ đọc

Agent, bridge và LiDAR cần đang chạy như sensor stage trước đó. Nếu thiếu, giữ output lỗi để sửa; không tự flash.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" inventory'
```

### 2 · Thu đứng yên 60 s

**Terminal:** Laptop  
**Tác động:** Chỉ thu

Giữ xe yên; không enable/teleop. Chờ FINISHED, không reboot trong lúc đóng bag.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" stationary'
```

### Copy dữ liệu về laptop

**Terminal:** Laptop, sau khi recorder kết thúc  
**Tác động:** Chỉ copy

Copy nguyên thư mục raw/sidecar; không xóa dữ liệu trên Pi.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy fetch --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

## Tiến–dừng + video · 1 lượt

Firmware RC hiện có: RC AUTO. 0,05 m/s; ramp 0,10 m/s²; source 2 s; bag 60 s. Một lượt mới, không dùng slot cũ.

### 0 · Cài bộ lệnh vào Pi (một lần)

**Terminal:** Laptop  
**Tác động:** Chỉ copy

Không sửa firmware, không chạy stack. Cài lại cùng phiên bản không reset ledger.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy deploy --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

### 1 · Kiểm driver / topic

**Terminal:** Laptop  
**Tác động:** Chỉ đọc

Agent, bridge và LiDAR cần đang chạy như sensor stage trước đó. Nếu thiếu, giữ output lỗi để sửa; không tự flash.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" inventory'
```

### 2 · Chạy command stack ở ZERO

**Terminal:** Terminal 1 · Laptop  
**Tác động:** Phát zero qua stack

Chờ READY và giữ terminal này mở. Không ARM motor từ bước này.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" start-stack'
```

### 3 · Thu bag 60 s + bật quay video

**Terminal:** Terminal 2 · Laptop  
**Tác động:** Chỉ thu / cấp đúng 1 slot khi người vận hành bắt đầu

RC AUTO, vùng trống. Nhập AUTO và ghi pose/caster/video. Video thấy bánh, thân, mốc sàn; chạy bước 4 ngay khi báo Recorder only.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" record-diagnostic'
```

### 4 · Một lần tiến–zero–disable

**Terminal:** Terminal 3 · Laptop  
**Tác động:** ENABLE + tiến 0,05 m/s trong 2 s, rồi zero/disable

Đây là bước duy nhất yêu cầu chuyển động. Giữ vùng trống; STOP/fault/stale hủy lượt, không auto retry. Chờ terminal 2 FINISHED trước tắt nguồn.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" run-trial'
```

### Đọc raw + hash + kết quả

**Terminal:** Laptop, sau khi recorder kết thúc  
**Tác động:** Chỉ đọc / derived

Báo cáo chưa tự xác nhận video/body hoặc hoàn tất review người vận hành.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" review'
```

### Copy dữ liệu về laptop

**Terminal:** Laptop, sau khi recorder kết thúc  
**Tác động:** Chỉ copy

Copy nguyên thư mục raw/sidecar; không xóa dữ liệu trên Pi.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy fetch --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

## Kiểm dữ liệu lượt vừa thu

Chỉ đọc raw; kết quả derived riêng. Không tự kết luận thân tiến hoặc tự mở lượt tiếp.

### Đọc raw + hash + kết quả

**Terminal:** Laptop, sau khi recorder kết thúc  
**Tác động:** Chỉ đọc / derived

Báo cáo chưa tự xác nhận video/body hoặc hoàn tất review người vận hành.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" review'
```

### Copy dữ liệu về laptop

**Terminal:** Laptop, sau khi recorder kết thúc  
**Tác động:** Chỉ copy

Copy nguyên thư mục raw/sidecar; không xóa dữ liệu trên Pi.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy fetch --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

## Độ lặp · chuẩn bị sau diagnostic

Chỉ tạo draft tối đa 3 lượt. Chưa có lệnh motion repeatability trước review diagnostic/protocol mới.

### 0 · Cài bộ lệnh vào Pi (một lần)

**Terminal:** Laptop  
**Tác động:** Chỉ copy

Không sửa firmware, không chạy stack. Cài lại cùng phiên bản không reset ledger.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy deploy --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

### Tạo draft, không chạy robot

**Terminal:** Laptop  
**Tác động:** Chỉ tạo kế hoạch

Draft ghi prerequisites/unknown; không mở lại pilot đã đóng, không tự cấp thêm lượt.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" plan repeatability'
```

## Body reference / geometry · chuẩn bị

Chỉ tạo draft đo định lượng; chưa tự tăng tốc hoặc tính slip.

### 0 · Cài bộ lệnh vào Pi (một lần)

**Terminal:** Laptop  
**Tác động:** Chỉ copy

Không sửa firmware, không chạy stack. Cài lại cùng phiên bản không reset ledger.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy deploy --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

### Tạo draft, không chạy robot

**Terminal:** Laptop  
**Tác động:** Chỉ tạo kế hoạch

Draft ghi prerequisites/unknown; không mở lại pilot đã đóng, không tự cấp thêm lượt.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" plan body_reference'
```

## Backend GUI không RC · chuẩn bị

Bản firmware authority chưa được xác nhận nạp. Copy bridge không biến firmware RC thành GUI authority.

### Copy bridge hỗ trợ GUI

**Terminal:** Laptop  
**Tác động:** Chỉ copy

Cần firmware tương thích và kiểm authority riêng. Không có lệnh flash tự động trong recipe này.

```bash
env NINO_SSH_KEY=/home/tuanmac/.ssh/nino_pi_flash_ed25519 bash /home/tuanmac/ninorobot/src/nino_pi/scripts/deploy_mode_bridge.sh d@192.168.0.109
```

## Navigation / vật cản / learning · kế hoạch

Chỉ chuẩn bị kế hoạch. Chưa có protocol/limits cho chuyển động hoặc vật cản ở bước này.

### 0 · Cài bộ lệnh vào Pi (một lần)

**Terminal:** Laptop  
**Tác động:** Chỉ copy

Không sửa firmware, không chạy stack. Cài lại cùng phiên bản không reset ledger.

```bash
env PYTHONPATH=/home/tuanmac/ninorobot/src/nino_pi /usr/bin/python3 -m nino_pi.collection_deploy deploy --host d@192.168.0.109 --key /home/tuanmac/.ssh/nino_pi_flash_ed25519
```

### Tạo draft, không chạy robot

**Terminal:** Laptop  
**Tác động:** Chỉ tạo kế hoạch

Draft ghi prerequisites/unknown; không mở lại pilot đã đóng, không tự cấp thêm lượt.

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i /home/tuanmac/.ssh/nino_pi_flash_ed25519 d@192.168.0.109 'bash "$HOME/nino_runtime/collection_commands_20261103_v1/session.sh" plan future'
```

