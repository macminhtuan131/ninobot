# Đợt đo độ lặp riêng — đã chốt và sẵn sàng lượt 1

> **Cập nhật sau lượt 1 — đợt đã đóng 1/3, hai slot còn lại đóng.**
> Session `clear_floor_repeatability_20261102T100409043176Z`: raw/hash/SQLite đạt,
> nhưng Collision Monitor STOP suốt đoạn tiến, final `/cmd_vel` luôn zero.
> Người vận hành xác nhận xe không di chuyển và có người/đồ vật sát phải/sau phải.
> Primary unknown; không chạy lại các lệnh thu bên dưới. Bước tiếp theo là kiểm
> vùng quét read-only với người/laptop ở vị trí thao tác thực tế; chưa motor trial mới.
> Đã lưu báo cáo workspace `artifacts/clear_floor_repeatability_evaluation_2026-11-02/slot1/REPORT.md`.

**Tối đa 3 lượt mới**, một condition, review sau mỗi lượt. Hiện **0/3**.
Phiên clear-zone complete1/1 giữ riêng, không tính vào đợt này.

## Profile và điều kiện giữ cố định

- Source tiến 0,05 m/s, ramp tham chiếu 0,10 m/s².
- Source tiến 2 s rồi zero/disable, quan sát 3 s, bag 60 s/lượt.
- Cùng firmware, RC AUTO, geometry/mounting, sàn/tải và boot.
- Người/đồ vật ngoài StopZone, cả phía sau và hai bên; không đi vào khi thu.
- Không tăng tốc, đổi gain/current hoặc thêm vật cản.

Guard kiểm 5 s scan mới/vùng trống trước mỗi session; nếu readiness không
đạt trước cấp slot thì chưa tiêu slot nhưng cần đọc lỗi, không lặp để ép qua.
Khi đã cấp slot, lỗi/unknown/đổi điều kiện đóng phần còn lại; không retry/bù.

## Đánh giá đã freeze

Primary là mean raw wheel velocity source+1,25..1,75 s trừ baseline−2..0 s,
báo từng bánh và trái−phải. Final reference phải 0,05±1e-6 m/s; giữ support
wheel100 ms/command200 ms và mọi spike. Secondary giữ positiondelta,phase
min/max/gaps,command/monitor/status và quan sát tiến/tự dừng/lệch/giật.

Sau 3 reviewed pass, báo từng giá trị và median/range; không coi 3 lượt là
proof equivalence/generalization. Chưa có tolerance ứng dụng để tự chỉnh gain.

## Lượt 1 — ba terminal trên Pi

Chuẩn bị sẵn cả ba terminal và dòng ghi pose/caster trước khi khởi động.
Collision Monitor có `stop_pub_timeout: 60`: sau khi đứng yên lâu, nó ngừng
phát zero; recorder sẽ từ chối vì final command stale. Không hạ freshness
hoặc thay timeout. Lỗi preallocation này chưa tiêu slot.

Terminal 1 — chờ READY rồi giữ mở; mở terminal 2 ngay sau READY, trong 30 s:
```bash
bash ~/nino_runtime/clear_floor_repeatability_20261102_v1/start_stack.sh
```

Terminal 2 — nhập AUTO và ghi pose/caster (`unknown` nếu chưa biết):
```bash
bash ~/nino_runtime/clear_floor_repeatability_20261102_v1/record_wheel.sh
```

Khi terminal 2 in Output và bắt đầu ghi, terminal 3 chạy ngay:
```bash
bash ~/nino_runtime/clear_floor_repeatability_20261102_v1/run_trial.sh
```

Giữ Pi có nguồn và terminal thu đến FINISHED; sau đó Ctrl+C terminal 1.
Gửi output và quan sát của chính lượt này. **Chưa chạy lượt 2/3 trước review.**

36 unit tests +6 mock handoff cases và live zero-only readiness đạt; chưa
phát enable/forward hoặc thu motion trong đợt mới. Một preflight đạt không
bảo đảm vật cản/stream sẽ giữ nguyên, nên guard kiểm lại trước từng session.

Artifact workspace: `artifacts/clear_floor_repeatability_2026-11-02/REPORT.md`,
`MEASUREMENT_PLAN.md`, `pilot_contract.json`. Contract SHA256:
`683a9bceb2396a9d1e048605023f8762f9c088ddf2a78de20419ad30c030ab05`.

Sau đợt đạt mới chốt protocol reference thân xe có scale/timing uncertainty;
chưa body/slip/governor claim ở đây.

## Preallocation bị chặn ngày 02/11 — vẫn 0/3

Người vận hành gặp `/cmd_vel absent/stale` sau nhập metadata. Đọc trực tiếp
trên Pi xác nhận không có ledger/active session, `can_begin=1`; hai node
active, selected/smoothed mới và zero, final publisher tồn tại nhưng không
có mẫu mới. Log startup `20261102T095618318840Z` đã từng đạt READY; snapshot
đóng ghi final age khoảng 329 s. Hiện tượng phù hợp zero-publication timeout
60 s; không phải bằng chứng mất agent hoặc lỗi motor. CLI `ros2 param get`
không tìm thấy node nên chưa có parameter readback độc lập trong lần kiểm này.

Đã SIGINT đúng launcher của phiên chờ, launch returncode 0, không forced
shutdown, không enable/forward. Khởi động lại terminal 1 rồi thu ngay theo
trình tự trên; giữ vùng quanh xe trống (snapshot cuối có điểm trong zone).
Contract/controller/primary/budget không đổi. Raw diagnostic và log giữ trong
artifact workspace cùng tên; chưa tạo session đo hoặc chạy lượt chuyển động.
