# Pilot chuyển động v3 — sẵn sàng thu lượt 1

> **Kết quả mới nhất:** v3 đã đóng1/3;raw đạt nhưng primaryunknown do StopZone can thiệp. Người dùng xác nhận có người/đồ vật phía sau. Không chạy lại slot2/3. [Đánh giá và bước tiếp theo](NINO_WHEEL_REPEATABILITY_PILOT_V3_RESULT_2026-11-02.md). Nội dung cũ bên dưới là lịch sử.


Người dùng đã yêu cầu tối đa 3 lượt mới, profile 0,05 m/s, ramp tham chiếu
0,10 m/s², source tiến 2 s rồi zero/disable, ghi 60 s. Review từng lượt.
V1/v2 cũ đều stopped1/3; v3 **0/3**, không reuse/retry/bù slot cũ.

## Đã kiểm

29 unit tests và 6 mock handoff cases đạt. Actuation/control/primary metrics
giữ nguyên. Collector resilient riêng và sync sau closure. Pi đã reboot,
Agent/readers đã nối lại; readiness gắn boot49371bb8. File hashes22/22,
file-only check và startup live zero-only đạt, launch đóng exit0.
Assistant chưa chạy source/enable hoặc motion trial.

## Lượt 1 — ba terminal trên Pi

Giữ xe yên trên sàn trống, cùng tải, RC AUTO; người vận hành cạnh nút dừng.

Terminal 1, chờ READY rồi giữ mở:
```bash
bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v3/start_stack.sh
```

Terminal 2, nhập AUTO và ghi pose/caster (`unknown` nếu chưa biết):
```bash
bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v3/record_wheel.sh
```

Khi terminal 2 in Output và bắt đầu ghi, terminal 3 chạy ngay:
```bash
bash ~/nino_runtime/wheel_repeatability_pilot_20261102_v3/run_trial.sh
```

Trial sẽ kết thúc trước recorder. **Không reboot/ngắt nguồn/đóng terminal 2**
đến `FINISHED: recorder closed; session files synced`. Sau đó Ctrl+C terminal 1.
Gửi output và quan sát xe tiến/tự dừng/lệch/giật/can thiệp. Chưa chạy lượt 2
trước review. Nếu lỗi, giữ dữ liệu và không chạy lại.

## Review và bước sau

Mỗi lượt kiểm hash/metadata/integrity, full command chain và primary mean
velocity mỗi bánh ở source+1,25..1,75s trừ baseline−2..0s, báo trái−phải.
Giữ support rules và mọi spike. Unknown/failure đóng các slot còn lại.
Lượt 1 vừa kiểm integration trong ngân sách3; không thêm smoke chuyển động.

Sau pilot đạt, mới chốt body reference độc lập; chưa đổi gain/current,
firmware hoặc thử vật cản. Giữ nguyên thư mục bag gồm WAL/SHM nếu có.

Artifact workspace: `artifacts/wheel_repeatability_pilot_v3_2026-11-02/`.
Contract SHA256: `09aa070ec277c1eb91a0b03478b8962a0369d0bdf30a900d60bd5f32e40d2e61`.
