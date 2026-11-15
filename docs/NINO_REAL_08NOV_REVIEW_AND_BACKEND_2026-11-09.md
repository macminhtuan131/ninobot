# Review real 08/11, backend tiếp theo và sensor stack .103

Ngày 09/11/2026. Đã SSH vào Pi `d@192.168.0.103`, đọc các phiên mới của
`~/nino-real-test`, tải bản sao về laptop và review trực tiếp. Không chạy
motor, flash, đổi gain/current, nạp actor hay gửi goal trong lần này.

## 1. Kết luận và phạm vi bằng chứng

1. Có dữ liệu real mới hơn cutoff 02/11 của bảng cũ. **Tám phiên đều thuộc
   nhóm SAC80k torque**, không phải tám lượt TD3 hoặc velocity SysID.
2. **6/8 bag đạt SQLite integrity và khớp toàn bộ topic/total counts với
   metadata**, tổng 313.555 messages. Sáu phiên vẫn có launch exit 120;
   bag đóng được không biến launch thành completed/pass.
3. Hai bag lỗi được giữ nguyên: một lỗi index, một malformed. Cả hai thiếu
   metadata; không reindex/recover tại chỗ hoặc tự viết metadata để promote.
4. Sáu bag hợp lệ có một Nav2 SUCCEEDED, ba ABORTED, hai không goal. Không
   đủ baseline/độ lặp để kết luận SAC tốt hơn hoặc kém hơn cổ điển.
5. Chọn **native velocity-reference backend cho đợt real SysID phục vụ TD3
   tiếp theo**. PI/SAC torque là nhánh riêng, không tự tiếp tục live SAC.
6. Agent/LiDAR/bridge/EKF/TF đã lên, **motion readiness vẫn false**: chưa có
   Collision Monitor đang active, chưa xác minh hình học/mounting hiện tại
   tương ứng contract mới. Không thu motion trong lần review này.

Nguồn client: `artifacts/real_review_2026-11-09_103/` có snapshot, analyzer,
analysis, hashes, sensor launch và live verification. Các file real gốc
trên Pi không thay đổi bởi review; snapshot/script review không tự là replay TD3.

## 2. Từng phiên và chất lượng theo claim

Thời gian trong tên phiên là local 08/11. Outcome Nav2 là software status,
không tự xác nhận arrival/dừng vật lý. Pose là AMCL/odometry estimate.

| Session | SQLite / metadata | Messages đọc SQL | Trace controller | Outcome và cách dùng |
|---|---|---:|---:|---|
| `173542_AhDsVS` | Integrity OK, metadata/counts khớp | 1.218 | 0 | Không goal; chỉ chẩn đoán startup |
| `173632_gBfF8K` | Integrity OK, metadata/counts khớp | 63.663 | 92 | Nav2 SUCCEEDED; logger 104 pose/499 IMU trong goal; timing fault sau/ngoài các mẫu armed cần giữ riêng |
| `174117_jv3smq` | **Index timestamp_idx sai; thiếu metadata** | 218.764 đọc tuần tự được, không promote | 0 | Không goal; incomplete/corrupt, giữ diagnostic |
| `181957_1cGGCo` | Integrity OK, metadata/counts khớp | 23.709 | 0 | Không goal; chưa là một motion experiment |
| `182154_y5D4AL` | Integrity OK, metadata/counts khớp | 139.512 | 437, chỉ 1 armed | Nav2 ABORTED; phần lớn trace không phải active SAC control |
| `182803_ijNbeF` | Integrity OK, metadata/counts khớp | 41.474 | 210, 25 armed | Nav2 ABORTED; có stale wheel và TF future extrapolation |
| `183048_4gjBAo` | Integrity OK, metadata/counts khớp | 43.979 | 384, 66 armed | Nav2 ABORTED; có stale input/TF fault |
| `183305_qtdgqR` | **Malformed; thiếu metadata** | Unknown, không coi là 0 mẫu | 117 | Logger riêng ghi SUCCEEDED với 252 pose/1.199 IMU; bag không dùng làm xác nhận đầy đủ |

Phiên `173632` có completion theo Nav2 khoảng 10,407 s, AMCL cross-track
RMSE khoảng 0,0332 m theo cửa sổ/logger lịch sử. Đây là **một kết quả estimate**,
không ground-truth path error, không physical stopping và không TD3 benefit.
Không lấy metric đẹp của goal aborted làm success hoặc loại failure khỏi mẫu.

## 3. Integrity/hash: đã kiểm gì và chưa kiểm gì?

- Đối chiếu **171 entries hash snapshot cấu hình/source/model** trong tám
  manifest: tất cả khớp. Cả tám snapshot cùng actor/model SAC80k và cùng
  core/node/features/config controller được pin; hardware snapshot có thay đổi.
- Hash **293 file của tám session** trên Pi và bản local: khớp từng file.
  Local hashes trước/sau review không đổi. Không tính bản copy là session mới.
- Raw DB/log không có historical checksum đầy đủ từ lúc capture trong
  manifest cũ. Hash lần review này là baseline mới, **không chứng minh raw
  chưa từng hỏng/thay đổi trước review**. Config hash đạt không chứng minh DB tốt.
- Đã decode 532.319 messages đọc được từ bảy DB; không lỗi CDR/type trong phần
  đọc được. Con số này gồm DB lỗi index, không phải số message đủ điều kiện
  benchmark. DB malformed không có count hợp lệ.
- DB cuối malformed ngay trên Pi, SHA256
  `800f5eeff84fe3153b55432e5472c2e77a95ca74b0b3115662ed37a58e4a4f61`,
  khớp bản local; không phải lỗi chỉ xuất hiện do tải file. Không có nonempty
  WAL cần merge trong snapshot này. Chưa kết luận nguyên nhân là nguồn, SD,
  reboot hay teardown.
- Sáu recorder log có chuỗi flush/Recording stopped; hai phiên lỗi không có
  chuỗi đóng và launch exit record. Không biết chắc nguyên nhân ngắt.
- Cả tám `outcome.json` vẫn null ở operator outcome/stop reason. Không tự
  điền lại lịch sử theo suy đoán hoặc theo status Nav2.

## 4. Lỗ hổng dataset và lỗi có bằng chứng

### Recorder thiếu đường actuator thật

Script `run_logged_real.sh` lịch sử ghi command Nav2/preview, nhưng **không
ghi `/cmd_torque`, `/motor_enable`, `/cmd_mit`, `/scan_raw` hoặc
`/collision_monitor_state`**. Trace `total` là lệnh controller tính, không phải
torque đo hoặc bằng chứng riêng rằng firmware nhận nó. Không tạo thêm những
topic này vào bag cũ. Profile thu tiếp cần ghi các đường thực dùng và đường
mode-changing/owner/STOP liên quan, chỉ đòi có mẫu ở kênh đúng contract.

### Timing/TF

Các phiên ABORTED có stale wheel/IMU/odom hoặc TF tại sensor time mới hơn
TF map pose khoảng một mẫu. Snapshot log còn có EKF missed update rate.
Đây là vấn đề integration/timing, chưa là kết luận SAC không học được.
Không tăng deadline hoặc đổi stamp sang giờ nhận chỉ để bỏ fault. Cần giữ
tuổi mẫu, skew và thời gian chờ TF theo contract nhân quả khi tích hợp controller.

### Contract/mounting khác nhánh cũ

Source Pi mới dùng observation **23D, SAC torque residual**, PI gain
0,30/0,10/Kd0 và mounting IMU identity. Nhánh TD3/history ở repo chính có
ABI/action khác. Pi hiện khai báo IMU xyz0/rpy0; khác TF gần đúng/yaw +90°
trong bằng chứng 27/10. Không overwrite hai bộ số để giả vờ thống nhất:
cần xác nhận thay firmware/frame hoặc mounting khi chọn real adapter mới.

## 5. Backend đã chọn cho bước tiếp

**Đích hiện hành:** gờ không biết trước, vượt được và bám quỹ đạo; triển khai
TD3 dự kiến bù velocity reference có giới hạn. Vì vậy đợt dữ liệu kế tiếp
chọn **velocity backend của firmware**, không PI torque trên Pi.

```text
Nguồn reference đã review → shaping/limits → Collision Monitor → /cmd_vel
→ firmware velocity mode → motor internal velocity loop

/motor_fb + status + IMU + command chain → wheel-response ID / History
```

- Chưa chạy chuỗi này trong lần restore. Nguồn `/cmd_vel` có thể chọn velocity
  mode; phải xác minh backend/mode trong protocol, không suy từ config torque.
- Không chồng thêm wheel velocity PI xuất torque trên Pi ở cùng lượt.
- Không copy gain/torque cap/action scale của sim hoặc SAC80k sang velocity.
- Hồ sơ/test torque/SAC vẫn giữ; watchdog/CAN diagnostic và physical wheel
  sign hỗ trợ mức tương ứng, không tự xác minh velocity stop/body dynamics.
- Train TD3 sim vẫn tiếp tục độc lập; tám phiên real không được nạp làm replay
  hoặc coi là deployment validation của checkpoint common103.

## 6. Sensor stack live đã khôi phục

Giữ Agent domain0/921600. Tạo sensor-only launch riêng, dùng config **đang
cài trên Pi**, đã đối chiếu source/install hash cho robot/bridge/EKF/Xacro.
Không launch controller/actor/Nav2. Bridge `allow_motor_enable=false`, publisher
và service enable được remap ra namespace sensor-only không nối firmware.

| Kênh | Rate quan sát khoảng | P95 source age so clock Pi trong cửa sổ |
|---|---:|---:|
| IMU raw | 46,96 Hz | 10,42 ms |
| Motor feedback | 46,96 Hz | 14,57 ms |
| Motor status | 46,95 Hz | Không header; không suy source age |
| IMU bridge / joints / unfiltered odom | 46,96–46,97 Hz | 11,48 / 15,56 / 16,68 ms |
| EKF odom | 46,52 Hz | 30,89 ms |
| Scan raw | 6,81 Hz | 1,54 ms theo stamp driver |
| Scan deskew | 6,86 Hz | 42,27 ms; max khoảng 132,2 ms |

Cửa sổ live khoảng 12 s; không source reversal/nonfinite ở các giá trị đã
kiểm. Source age còn phụ thuộc clock/stamp semantics, không motor latency
hoặc guarantee dưới tải Nav2. Không lấy max của cửa sổ làm hard bound.

- `base_footprint ← laser`, `base_footprint ← imu_link`,
  `odom ← base_footprint` lookup được.
- `/odom` có một owner EKF, `/odom/unfiltered` một owner bridge. RSP và EKF
  cùng xuất `/tf` cho các cạnh khác nhau; không gọi là cạnh odom có hai owner.
- Không publisher firmware `/cmd_vel`, `/cmd_torque`, `/cmd_mit`,
  `/motor_enable` trong snapshot. Không request arm/enable.
- `map ← base_footprint` chưa có vì không chạy AMCL; đây không là localization
  ready. **Collision Monitor chưa chạy/active, STOP chưa được kiểm live.**
- Monitor trong repo Pi dùng `FootprintApproach`, cần footprint local costmap
  và scan/TF; khác StopZone của helper cũ. Không trộn hai cấu hình hoặc gọi
  sensor ready là motion ready, không bypass monitor để có dữ liệu.

Runtime sensor-only trên Pi:
`~/nino_runtime/sensor_restore_review_20261109_v1/` (launcher/log/verification).
Nó giữ lock bringup hiện có; phải đóng sensor-only có kiểm soát trước khi
launch stack đầy đủ để tránh hai bridge/EKF/LiDAR cùng chạy.

## 7. Đã có / còn thiếu và việc bổ sung tối thiểu

| Dữ liệu | Cập nhật sau review | Việc còn cần |
|---|---|---|
| IMU/wheel/status/scan | Có raw cũ/mới và sample live; status hiện khoảng 47 Hz, không còn mặc định 5 Hz | Kiểm theo cửa sổ tải thực của mỗi protocol |
| Physical wheel sign/mapping | Có test bánh riêng và operator confirmation 08/11 | Không cần yêu cầu lặp vô hạn; gắn firmware/backend đúng, không suy body motion |
| Watchdog MCU | Test schema4001: detect401/402ms, CAN TX403/404ms trong test zero-torque | Không là body stopping hoặc velocity-mode stop đã đo |
| Navigation/AMCL | Có một goal SUCCEEDED trong bag hợp lệ, ba ABORTED; một success logger-only ở bag hỏng | Outcome operator còn thiếu; chưa comparative benchmark hoặc pose GT |
| Velocity wheel SysID | Tám phiên torque không thay bộ velocity ID đã chốt | Diagnostic velocity riêng rồi bounded repeats/whole-session holdout nếu phù hợp |
| Body displacement | Chưa có reference định lượng độc lập được review | Thước/mốc đầu-cuối, uncertainty; camera không bắt buộc |
| Body velocity/slip | Chưa có reference theo thời gian đủ điều kiện | Candidate LiDAR-only estimator cần validation riêng; chưa bắt đo slip ngay |
| TD3 real benefit | Chưa có dữ liệu deployment TD3 phù hợp ABI | Giữ real authority0 trước shadow/validation riêng |

**Thứ tự tiếp theo:**

1. Đã chuẩn bị và đưa `scripts/run_logged_real_v2.sh` lên repo Pi: thêm ghi
   `/cmd_torque`, `/cmd_mit`, `/motor_enable`, `/scan_raw`,
   `/collision_monitor_state`; giữ script cũ và toàn bộ control/profile.
   `bash -n` local/Pi đạt, **chưa chạy recording bằng v2**. Đây là runner
   navigation cũ được bổ sung logging, không phải helper velocity2s mới;
   không dùng nó như motion release. Đóng/hash sau process kết thúc và QC
   vẫn cần kiểm từng phiên; bản này chưa chứng minh sửa nguyên nhân DB hỏng.
2. Qualify velocity chain/guard riêng không motion: đúng output owner,
   cùng scan/TF/footprint cấu hình, monitor active; xác nhận mounting/frame
   cho adapter sẽ dùng. Không dùng helper torque/SAC cho velocity pilot.
3. Khi chain đạt và người vận hành sẵn sàng: một diagnostic velocity trên
   sàn sạch, giữ proposal 0,05m/s, ramp0,10m/s², source2s, bag60s; thước/mốc
   đầu-cuối và quan sát từng bánh nếu nhìn được. Đây chưa là lượt đã chạy.
4. Nếu diagnostic nhất quán, chốt đợt tối đa3 repeats mới; phân tích wheel
   response và whole-session holdout. Không đủ excitation thì báo unknown,
   không tự đổi tốc độ/ramp hoặc tăng N. Không chỉnh gain/current/thử gờ lúc này.

## 8. Giới hạn và nguồn

Đọc snapshot từng phiên, analyzer CDR/SQL, manifest/config/controller/
measurements và source runner/logger; hồ sơ wheel/watchdog/status50; TF và
owner probe trực tiếp hôm nay. Không force-recover DB, không sửa các ledger
đã đóng, không có video mới hoặc physical test mới. Tài liệu cutoff02/11
vẫn là lịch sử đúng phạm vi của nó; báo cáo này bổ sung bằng chứng mới.
