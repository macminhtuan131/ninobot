# Kiểm recorder sau phiên bị ngắt — bước hiện tại

> **Kết quả mới nhất:** stationaryv2đạt,22/22hash,SQLiteok,cótelemetrycuốiphiên. Không chạy lại capture đã dùng. [Bước hiện tại](NINO_CURRENT_STATUS_2026-11-02.md): đề xuất motion pilot mới có giới hạn, chưa release. Nội dung dưới đây là lịch sử.


Người dùng xác nhận đã reboot/ngắt nguồn trong phiên đứng yên v1; không kết luận đó là recorder/Pi tự lỗi. V1 vẫn incomplete, motion pilotv2 vẫn stopped1/3.

Đã chuẩn bị storage preset resilient bằng collector riêng;26tests và fixture offline đạt. Chưa chứng minh chống mất điện hoặc capture trênPi mới đạt.

## Một capture đứng yên mới, tối đa1

Không dùng teleop/enable, giữ xe yên và Pi có nguồn đến khi helper kết thúc. TrênPi:

```bash
bash ~/nino_runtime/stationary_closure_20261102_v2/run_once.sh
```

Đợi dòng `FINISHED: collector closed; session files synced` và returncode0. **Không reboot/ngắt nguồn giữa phiên; đủ60s chưa đồng nghĩa file đã đóng.** Nếu lỗi, giữ output và không chạy lại. Sau đó assistant kiểm metadata/hash/integrity và samples cuối55..60s.

Chưa chạy helper mới; chưa mở ngân sách motion. Artifact workspace: `artifacts/recorder_reliability_review_2026-11-02/REPORT.md`.

Preset giảm nguy cơ crash corruption, không bảo đảm zero loss: [ROS bag SQLite Jazzy](https://github.com/ros2/rosbag2/blob/jazzy/rosbag2_storage_sqlite3/README.md).
