# Một phiên chuyển động mới — vùng thử đã kiểm

> **Kết quả mới nhất:** phiên dọn vùng thử đã thu1/1,data gate vàprimaryđạt;operator đã xác nhận và phiên complete1/1. Không chạy lại helper. [Kết quả](NINO_CLEAR_ZONE_MOTION_RESULT_2026-11-02.md).


Người dùng báo đã dọn xung quanh và yêu cầu phiên tiếp theo. Đây là một
capture mới duy nhất, không mở lại slot2/3 của pilotv3 đã đóng. Hiện0/1.

31tests và6mock cases đạt. Live zero-check có35scan/5,073s,không điểm trong
vùng tĩnh,không STOP mới; lifecycle active,zero references mới,owner đúng,
không enable/forward. Runtime guard kiểm lại5s trước cấp session.
Firmware,gain/current,StopZone và profile0,05m/s,ramp0,10m/s²,source2s,
zero/disable,bag60s giữ nguyên. Scene readiness không bảo đảm vật cản sẽ
không đi vào vùng khi xe chạy; giữ người/đồ vật ngoài vùng quét suốt phiên.

## Ba terminal trên Pi

Terminal1 — chờREADY,giữ mở:
```bash
bash ~/nino_runtime/wheel_clear_zone_20261102_v1/start_stack.sh
```
Terminal2 — nhậpAUTO và ghi pose/caster (`unknown` nếu chưa biết):
```bash
bash ~/nino_runtime/wheel_clear_zone_20261102_v1/record_wheel.sh
```
Khi terminal2inOutput và bắt đầu thu,terminal3chạy ngay:
```bash
bash ~/nino_runtime/wheel_clear_zone_20261102_v1/run_trial.sh
```

Không reboot/ngắt nguồn hoặc đóngterminalthu đếnFINISHED. Sau đóCtrl+C
terminal1,gửioutput và quan sát tiến/tựdừng/lệch/giật/canthiệp. Chỉmộtlượt,
khôngretry hoặc lượt2. Nếuguard báoblocked,cần báooutput,không chạy liên
tục để ép qua. Primarywindows/support và mọi spike giữ nguyên khi review.

Artifact workspace:`artifacts/clear_zone_motion_2026-11-02/REPORT.md`.
Contract SHA256:`857ba21b36bc5fc629bb556fd496b8f20bf2ee4d1f46df4dfd061f26c89e0e89`.
