# Phiên sau khi dọn vùng thử — complete 1/1

Session wheel_clear_zone_20261102T094226594883Z:raw25/25file hash khớp,
SQLiteok,metadata23.995message khớp,collector đóngsạch. Source39positive,
smoothed/final50positive,max0,05m/s,yaw0; không thấy final bị monitorngắt
như v3. ScanXY chẩnđoán trongmotion có0điểm trongzone.

Primary hợp lệ:delta meanvelocity trái0,834241,phải0,820122rad/s;
trái−phải0,014119rad/s. Baseline97mẫu,primary24mẫu mỗi bánh,giữ mọi spike.
Nominal encoder distance khoảng9,65cm(R0,060m khai báo),không bodyGT/slip.

**Ngân sách 1/1 đã dùng và phiên đã complete:** operator xác nhận xe tiến rồi
tự dừng, không cần can thiệp hoặc lệch/giật rõ. RC AUTO/cùng sàn tải được
xác nhận trong metadata đầu phiên. Không chạy lại helper hoặc thêm phiên.

V3cũ vẫn đóng1/3;không gộplượt kháclayout thànhrepeatability.
Sau khi complete,chốt riêng ngân sáchlặp cógiớihạn cùngscene/profile;
chưa tăngtốc/gain/current hoặc thửobstacle/governor.

Artifact workspace: `artifacts/clear_zone_motion_evaluation_2026-11-02/REPORT.md`,
`primary.json`, `command_wheel_trace.png`.
