# Pilot v3 lượt1 — raw đạt, primary unknown, pilot đóng

Session wheel_repeatability_v3_20261102T091339485407Z:25/25hash khớp,SQLiteok,
metadata24.882message khớp,closure đạt. Hai bánh có tiến và operator xác nhận
tự dừng,không can thiệp/lệch/giật rõ;RC AUTO/cùng sàn tải.

Collision monitor StopZone ngắt final command ở+0,262..1,002s và+1,602..1,802s
(tính từ firstforward). Khoảng thứhai đi vào primary+1,25..1,75s nên metric
unknown theo contract,không phải lỗi logger. Pilot reviewed_unknown,stopped1/3,
hai slot còn lại đóng. Không retry/bù hoặc chuyểnwindow để đạt.

Rawscan có các điểm trong vùng phía sau;người dùng xác nhận có người/đồ vật
sát phía sau. Không gọi false trigger,không sửa gain/current/StopZone.
Quãng encoder nominal khoảng4,33cm,không bodyGT;profile ngắn và monitor
intervention giải thích việc chỉ đi ngắn.

## Bước tiếp theo

Nếu terminal1 còn mở thì Ctrl+C sau khi recorder đã FINISHED. Dọn vùng quét
quanh xe,bao gồm phía sau/hai bên;kiểm scan mới và StopZone bằng quan sát
chỉ đọc/zero trước motion mới. LiDAR từng mất stream cuối phiên,hiện kiểm
lại có31scan/5s;chưa quy nguyên nhân. Không chạy lại slot2/3 đã đóng.

Chỉ sau khi layout/source health đạt mới chốt một protocol motion mới.
Chưa bodyreference/slip/governor/RL. Artifact workspace:
`artifacts/wheel_repeatability_v3_evaluation_2026-11-02/slot1/REPORT.md`,
`command_wheel_trace.png`, `primary.json`, `ledger_after_review.json`.
