# BÁO CÁO TIẾN ĐỘ DỰ ÁN RL NINO

**Ngày:** 11/10/2026. **Mốc chốt số liệu trực tiếp:** khoảng 19:24, giờ Asia/Bangkok.

**Phạm vi:** mô phỏng Gazebo/ROS 2, hai phần rough terrain và flat cable, PPO, bộ điều khiển tham chiếu, định vị, reward, Optuna và hướng chuyển sang robot thật. Báo cáo sử dụng kết quả đã lưu trong dự án; không chạy thêm mô phỏng để viết báo cáo.

## 1. Kết luận hiện tại

**Dự án đã cải thiện nền tảng điều khiển, độ tin cậy của đánh giá và khả năng học của critic. Tuy nhiên, chưa có bằng chứng đủ mạnh rằng PPO hiện tại tốt hơn bộ điều khiển PI trên toàn bộ yêu cầu của bài toán.**

- **Flat:** các pilot mới giữ được 24/24 lần đến đích trong những bộ đánh giá đã hoàn thành. Một số PPO giảm rung rõ rệt, nhưng tăng trượt bánh; pilot tăng phạt trượt gần nhất lại có cả rung và trượt cao hơn PI. Chưa có ứng viên vượt đầy đủ điều kiện chấp nhận.
- **Rough:** đã tìm được một cấu hình địa hình khả thi hơn và xác nhận PI trên E1/N1/S1 với ba cấu hình vật lý. PPO dùng cảm biến phù hợp phần cứng có thể đến đích và bám đường tốt trên E1, nhưng chưa học ổn định hành vi giảm tốc khi nhiễu rồi phục hồi tốc độ. Pilot sửa riêng cân bằng reward đang chạy, chưa có kết luận đánh giá cuối.
- **Optuna:** đang giữ lại, chưa chạy tiếp. Không nên tối ưu tham số trên một cơ chế điều khiển hoặc mục tiêu học chưa được xác nhận.
- **Sim-to-real:** chưa được chứng minh. Hiện có tiến bộ về tính phù hợp của đầu vào cảm biến; chưa có kiểm chứng hiệu quả điều khiển trên robot thật.

### Lưu ý về tên “PID”

Các phép so sánh đã lưu dùng **bộ bám đường kết hợp PI vận tốc riêng cho hai bánh chủ động**. Mã `effort_drive.py` có thành phần P và I trong điều khiển vận tốc; đây không phải phép thử một bộ PID đầy đủ có thành phần D.

Vì vậy, các bảng dưới ghi **PI** để phản ánh đúng đối chứng đã thực sự chạy. Kết luận “RL tốt/kém hơn PI” không đồng nghĩa đã so sánh với mọi cách chỉnh PID, Nav2 hoặc MPC.

PPO hiện vẫn sử dụng PI ở tầng động cơ. So sánh thực tế là **bộ điều khiển cổ điển** với **bộ điều khiển cổ điển có thêm chính sách PPO điều chỉnh lệnh**.

## 2. Dự án và thuật toán đã phát triển như thế nào?

### 2.1. Từ cable course sang địa hình rough và bản đồ kết hợp

Ban đầu, dự án tập trung vào hành lang có cáp/chướng ngại và checkpoint cũ khoảng 1,5 triệu bước. Sau đó bổ sung các hõm, ổ gà, gò và vùng dốc; phát triển bản đồ kết hợp rồi tách rough/flat để huấn luyện và chẩn đoán riêng.

Rough được mở rộng về độ đa dạng, có vùng đích xung quanh và các tuyến E1, N1, S1 cùng các tuyến khác người dùng vẽ. Mục tiêu chuyển từ chỉ đến đích trên đường thẳng sang bám quỹ đạo qua địa hình gây thay đổi IMU và phản ứng bánh xe.

**Điểm cần phân biệt:** có nhiều tuyến trên một mesh giúp tăng độ phủ bài toán, nhưng chưa chứng minh thích nghi với địa hình chưa gặp. Số bước lớn của checkpoint cũ cũng không bảo đảm tốt trên contract hoặc bản đồ mới.

### 2.2. Thay đổi giao diện hành động

- **Flat cũ:** PPO điều chỉnh tốc độ và thêm hiệu chỉnh mô-men chung/vi sai. Ablation cho thấy bỏ hiệu chỉnh mô-men giúp tăng đến đích nhưng chạy chậm.
- **Flat mới:** chuyển sang tốc độ và hiệu chỉnh yaw có giới hạn qua bộ điều khiển PI; bổ sung phản hồi bám đường và xử lý tiếp cận đích.
- **Rough hiện tại:** thu hẹp bài toán về **một hành động tốc độ**. Bộ bám đường/PI giữ quyền điều khiển hướng; không có mô-men residual do PPO tự do thêm vào. Cách này giúp xác định rõ PPO có học điều chỉnh chuyển động theo nhiễu hay không.

Với rough hiện tại, hệ số tốc độ nằm trong **0,55–1,00**, có ramp cố định **0,4 đơn vị hệ số/giây**. Lệnh yaw của PI không bị nhân theo hệ số giảm tốc. Hai bánh vẫn được PI điều khiển độc lập; pilot này không yêu cầu PPO xuất hai mô-men bánh độc lập.

### 2.3. Tách định vị khỏi đánh giá vật lý

Trước đây, encoder có thể báo robot tiến lên trong khi bánh quay nhưng thân xe đứng yên, hoặc báo gần đích khi vị trí vật lý chưa đến. Điều này làm tỷ lệ thành công và nguyên nhân thất bại khó tin cậy.

Các profile mới dùng phản hồi IMU/encoder và LiDAR với hình học tường đã biết để hiệu chỉnh vị trí. Đích đến, sai số bám đường và thứ tự đi qua các cổng tuyến vẫn được đánh giá độc lập bằng vị trí vật lý của Gazebo.

**Ground truth được dùng cho đánh giá và một số thành phần reward; không được đưa thành phép đo vị trí/vận tốc đặc quyền cho actor trong pilot rough phần cứng hiện tại.**

### 2.4. Chuyển từ “train lâu hơn” sang kiểm tra cơ chế học

Quy trình hiện nay kiểm tra lần lượt:

1. Robot có thực sự đi qua được địa hình không?
2. Cảm biến/định vị và thời gian hành động có đúng không?
3. Điều chỉnh tốc độ có thật sự ảnh hưởng đến rung/trượt không?
4. Observation và exploration có cho PPO thấy, thử được hành vi mong muốn không?
5. Reward có trả điểm cho hành vi đúng không?
6. Sau đó mới xem xét train dài hơn hoặc Optuna.

Các mô hình, trial thất bại và study cũ được giữ lại. Khi đổi ý nghĩa hành động, observation, estimator hoặc reward contract, không tiếp tục optimizer cũ một cách không tương thích. Có nhánh chuyển actor có kiểm chứng với critic/optimizer mới; có nhánh khởi tạo hoàn toàn mới.

## 3. Những cải thiện đã có bằng chứng

| Hạng mục | Trước đây | Tiến bộ đã đo được | Giới hạn còn lại |
|---|---|---|---|
| Đến đích ở flat | Checkpoint torque trong một phép thử đạt 11/24, PI đạt 23/24 | Các pilot mới đạt 24/24 trong những bộ kiểm tra đã hoàn thành | Profile/seed đã thay đổi; không phải phép thử chỉ thay một yếu tố |
| Định vị | Dừng sớm; bánh quay gây sai lệch quãng đường | Profile flat phản hồi mới có 24/24 đến đích; sai lệch cuối ước lượng/vật lý trung bình khoảng 1,08 mm trong mô phỏng | Tường/hình học đã biết, cảm biến mô phỏng; không suy ra độ chính xác thật |
| Critic flat | Explained variance âm/gần 0; gradient critic lấn actor | Scale-only đạt EV khoảng 0,641; aligned-impact khoảng 0,710 | Critic tốt hơn không tự bảo đảm chất lượng chuyển động tốt hơn |
| Critic rough | Trial 8 có EV âm trong audit | Nhánh sửa đơn vị reward đạt EV khoảng 0,410; pilot hiện tại ghi khoảng 0,961 trong training | Khác contract; EV hiện tại chưa phải đánh giá hành vi cuối |
| Chẩn đoán rough | Timeout/stall dễ bị xem là lỗi policy | Có bằng chứng tiếp xúc chassis, caster và bánh chủ động mất tải | Giảm độ nổi địa hình là thay bài toán; không chứng minh đã giải quyết map gốc |
| Khả thi với cảm biến thật | Một số thử nghiệm dùng LiDAR mô phỏng không có trên robot thật | PI hardware-only đạt 27/27 trong 3 tuyến × 3 profile × 3 seed | Bộ kiểm tra nhỏ, fixed map và định vị dựa vào tường |
| Observation rough | Lịch sử đầu cuối thiếu tóm tắt rung và trạng thái detector | 72 giá trị/frame × 5 frame = 360 đầu vào, thêm RMS/peak IMU, trạng thái nhiễu và lệnh thực thi | Chưa chứng minh causal dependence vào IMU hoặc tổng quát hóa |
| Đánh giá chất lượng | Rung thấp có thể chỉ do chạy chậm | Có PI toàn tốc và PI khớp thời gian; đo cả cửa sổ nhiễu | Matching vẫn cần kiểm tra dung sai; seed giống nhau không làm mô phỏng hoàn toàn tất định |

**Những tiến bộ trên là có thật, nhưng bao gồm cả tiến bộ của PI, estimator, môi trường và phương pháp đánh giá. Không được ghi toàn bộ là “RL đã cải thiện”.**

## 4. So sánh RL và PI: kết quả tốt và kém đều được giữ

### 4.1. Flat: bằng chứng ban đầu về hiệu chỉnh mô-men

Phép thử hai cáp được ghi trong báo cáo ngày 07/10:

| Phương án | Đến đích vật lý | Nhận xét |
|---|---:|---|
| PI | 23/24 — 95,8% | Đối chứng tốt nhất về tỷ lệ đến đích trong bộ này |
| PPO có hiệu chỉnh torque | 11/24 — 45,8% | Kém PI rõ rệt |
| Cùng PPO nhưng tắt hiệu chỉnh torque | 20/24 — 83,3% | Cải thiện thành công; thời gian các lần thành công trung bình 28,61 s, không đạt mục tiêu 22 s |

Kết quả ủng hộ việc kiểm tra lại quyền điều khiển torque. Nó chưa cô lập được riêng hiệu chỉnh mô-men chung hay vi sai là nguyên nhân chính.

### 4.2. Flat: các pilot mới trên stage hai cáp

Mỗi dòng dùng **PI đi kèm cùng bộ scenario của pilot đó**. Thời gian, RMSE, rung và slip là trung bình các episode. Rung là RMS gia tốc đứng, đơn vị m/s²; slip là chỉ số không đơn vị của dự án.

| Pilot | Đến đích PPO / PI | Thời gian PPO / PI (s) | RMSE vật lý PPO / PI (cm) | Rung PPO / PI | Slip PPO / PI | Kết luận |
|---|---:|---:|---:|---:|---:|---|
| Actor pilot trước sửa critic | 24/24 / 24/24 | 18,20 / 17,53 | 3,59 / 2,88 | 3,658 / 2,735 | 0,1895 / 0,1915 | Slip giảm ít; thời gian, tracking và rung kém hơn |
| Scale-only, seed train 42 | 24/24 / 24/24 | 18,18 / 17,53 | 3,78 / 3,77 | 2,002 / 2,836 | 0,1934 / 0,1833 | Rung giảm 29,4%, slip tăng 5,5%; không qua quality gate |
| Aligned-impact | 24/24 / 24/24 | 17,92 / 17,63 | 3,58 / 3,52 | 2,537 / 2,635 | 0,1914 / 0,1985 | Rung và slip giảm khoảng 3,7%/3,6%; chưa đủ quality gate |
| Scale-only lặp, seed train 43 | 24/24 / 24/24 | 17,97 / 17,61 | 3,79 / 3,76 | 2,570 / 3,503 | 0,1999 / 0,1922 | Rung giảm 26,6%, slip tăng 4,0%; không qua quality gate |
| Pilot tăng phạt slip gần nhất | 24/24 / 24/24 | 17,94 / 17,52 | 3,40 / 3,31 | 3,153 / 2,932 | 0,2034 / 0,1842 | Rung tăng 7,6%, slip tăng 10,4%; không qua quality gate |

**Kết luận flat:** RL mới đã giữ được đến đích trong các bộ này và có tiềm năng giảm rung. Tuy nhiên, chưa có cải thiện đồng thời đủ mức về arrival, thời gian, bám đường và chất lượng. PI vẫn là lựa chọn tham chiếu đáng tin cậy hơn theo tiêu chuẩn chấp nhận hiện tại.

Các dòng thuộc những nhánh reward/contract khác nhau; không so sánh raw return giữa chúng. PI cũng có biến thiên giữa các batch. Dòng pilot slip gần nhất dùng 15 PI episode đã lưu và 9 episode khôi phục với encoder history 100 thay cho 1; provenance này được giữ trong báo cáo, không coi là batch hoàn toàn đồng nhất về transport.

### 4.3. Rough cũ: trial 8, fixed map nguyên bản, 20 seed 12000–12019

| Chỉ số | PPO trial 8 | PI toàn tốc | PI khớp thời gian |
|---|---:|---:|---:|
| Đến đích vật lý | 20/20 | 20/20 | 20/20 |
| Thời gian (s) | 38,91 | 27,11 | 38,72 |
| RMSE vật lý (cm) | 2,34 | 2,04 | 2,61 |
| Rung RMS (m/s²) | 1,145 | 1,561 | 1,137 |
| Slip RMS | 0,03502 | 0,05267 | 0,04058 |
| Điểm đánh giá cố định, cao hơn tốt hơn | 8,725 | 13,467 | 8,512 |

So với PI toàn tốc, PPO êm hơn và ít trượt nhưng **chậm hơn khoảng 43,6%**, điểm tổng thể thấp hơn. So với PI khớp thời gian, rung gần tương đương, slip giảm khoảng 13,7% và tracking tốt hơn; có lợi ích riêng về slip trong bộ này, nhưng chưa chứng minh lợi ích tổng quát.

Đây là kết quả lịch sử của setup v16 với cảm biến/định vị mô phỏng khác pilot phần cứng hiện tại. Không dùng nó để tuyên bố policy hiện tại đạt cùng hiệu quả hay chuyển được trực tiếp sang robot thật.

### 4.4. Rough hardware-only: observable v2, E1 half-relief, 5 seed 17100–17104

| Chỉ số | PPO | PI toàn tốc | PI khớp thời gian |
|---|---:|---:|---:|
| Đến đích vật lý | 5/5 | 5/5 | 5/5 |
| Thời gian (s) | 29,10 | 26,98 | 29,00 |
| RMSE vật lý (cm) | 1,68 | 1,67 | 1,62 |
| Rung RMS (m/s²) | 1,229 | 1,321 | 1,266 |
| Slip RMS | 0,01643 | 0,01754 | 0,01712 |

Nhìn toàn hành trình, PPO giảm rung khoảng **3,0%** và slip khoảng **4,1%** so với PI khớp thời gian. Tuy nhiên, trong **cửa sổ nhiễu**, năng lượng rung trên mét giảm 7,54% còn năng lượng slip trên mét **tăng 10,12%**, vượt giới hạn tăng 10% đã đặt.

Ngoài ra, policy không qua điều kiện giảm tốc/phục hồi: bốn episode duy trì cruise khoảng 0,936–0,938 thay vì phục hồi đủ; episode còn lại không có giảm tốc đủ rõ. **Pilot không đạt cả behavior gate và ride-quality gate.**

Các kết quả toàn hành trình tốt hơn một chút không được dùng để bỏ qua thất bại ở đoạn cần thích nghi.

### 4.5. Cơ chế phản ứng theo quy tắc: có ích, nhưng chưa phải PPO học được

Một bộ giảm tốc ngắn dựa trên IMU/encoder, rồi phục hồi, đã được thử trên 10 seed rough:

- 10/10 đến đích và phục hồi tốc độ.
- Thời gian tăng 4,41%.
- Năng lượng rung trên mét trong cửa sổ nhiễu giảm 6,13%.
- Năng lượng slip trên mét giảm 2,21%; slip RMS toàn hành trình tăng khoảng 0,09%.
- Mức giảm năng lượng rung trung vị theo cặp chỉ 1,51%, nên lợi ích không đồng đều.

Đây là bằng chứng **quyền điều khiển tốc độ có thể hữu ích** trong bài toán đã thử. Nó không phải bằng chứng PPO đã học được cùng cơ chế.

Ở flat cũng đã có một screening 3 seed về điều chỉnh tốc độ trước cáp: lịch giảm tốc biết vị trí cáp đạt 3/3, thời gian 21,03 s so với 17,53 s của PI toàn tốc; rung giảm từ 4,905 xuống 3,080 và slip từ 0,334 xuống 0,299. Đây là thử nghiệm quyền điều khiển với vị trí cáp đã biết, không phải policy triển khai chỉ dùng cảm biến. Không so giá trị này trực tiếp với các batch 24 seed ở trên.

## 5. Khó khăn, giải pháp đang dùng và hạn chế của giải pháp

| Khó khăn đã gặp | Giải pháp đang dùng/đã thử | Khó khăn còn lại khi dùng giải pháp |
|---|---|---|
| Đến đích “ảo”, dừng sớm do odometry | IMU/encoder đồng bộ; LiDAR sửa vị trí; chấm đích bằng pose vật lý độc lập | Phụ thuộc tường đã biết và visibility; không phải SLAM cho môi trường bất kỳ |
| Bánh quay nhưng xe không tiến ở S1/N1 | Đo tiếp xúc, phát hiện slip/stall, kiểm tra quãng dịch chuyển độc lập | Định vị đúng không tạo lực bám cho bánh đã mất tải hoặc nhấc chassis khỏi địa hình |
| Góc N1 bám đường kém hoặc mắc cạn | Phanh sớm, giữ yaw authority, thử profile turn anticipation | Có profile đến 3/3 nhưng RMSE 9,33 cm; profile khác 0/3. Không được tăng ngưỡng để gọi là đạt |
| Map gốc quá khó với chassis/caster | Snapshot riêng giảm relief xuống 50%, giữ visual/collision chung mesh | Giải quyết tính khả thi trên map dễ hơn; chưa giải quyết benchmark gốc |
| Sensor mô phỏng không có trên robot thật | Bỏ downward preview và wall cloud 33 kênh khỏi rough actor/estimator | IMU/encoder chủ yếu phản ứng sau tiếp xúc; LiDAR ngang không bảo đảm nhìn được hõm phía trước |
| Critic yếu, gradient critic lấn actor | Audit GAE/gradient; scale reward learner; critic/optimizer mới | MSE giảm một phần do đổi đơn vị; cần EV và kết quả vật lý. Không tự sửa reward sai mục tiêu |
| Reward impact không khớp RMS rung | Đối chiếu tích phân/peak và thử aligned-impact | Pilot chỉ cải thiện nhỏ; reward mới cần kiểm chứng, không coi “đúng công thức” là đã tốt |
| Tăng phạt slip không giảm slip flat | Audit quanh cáp thứ hai, lệnh yaw/tốc độ, tốc độ bánh và giới hạn motor | Quan hệ lệnh–đáp ứng chưa đủ để kết luận nguyên nhân; thêm penalty có thể đổi hành vi ngoài ý muốn |
| Detector rough bị recovery lockout | Recovery giới hạn 0,8 s; holding 0,6 s; cooldown 1,2 s | Đã sửa rearming, nhưng detector “quiet” vẫn có rung; policy vẫn có thể chọn chậm vừa phải |
| Actor thiếu lịch sử rung/lệnh thực thi | Thêm interval IMU RMS/peak, trạng thái detector, lệnh published/executed; 360 input | Nhiều input hơn không chứng minh học tốt hơn; đổi contract làm actor cũ không thể resume nguyên dạng |
| PPO chưa thử giảm tốc đủ lâu | gSDE làm mới mỗi 6 bước; kiểm tra exploration có slowdown/recovery | Thử được hành vi chưa có nghĩa giữ được hành vi sau tối ưu |
| Reward trả điểm cao cho cruise hơi chậm | Audit từng thành phần; đổi riêng velocity sigma 0,4 → 0,1 | Có thể ép policy luôn toàn tốc hoặc tăng slip lúc tăng tốc; pilot mới phải giữ quality gate |
| Crash, mất điện, discovery và timing interruption | Checkpoint, log, recover evaluation; domain/partition riêng; giữ timing checks | Resume mất phần rollout chưa hoàn tất; lỗi hạ tầng không được tính là tham số RL kém |
| Tuning tốn thời gian nhưng không ra ứng viên đạt | Giữ Optuna; thu hẹp giả thuyết và pilot có ngân sách cố định | Ít trial hơn trước mắt, nhưng tránh tối ưu một bài toán chưa có tín hiệu mục tiêu đúng |

### Nguyên nhân reward rough chưa khuyến khích phục hồi đủ

Audit observable v2 cho thấy PPO nhận raw return trung bình **19,153**, cao hơn PI toàn tốc **18,738**, dù không đạt hành vi phục hồi mong muốn.

PPO được lợi khoảng **0,626** điểm từ giảm chi phí rung, trong khi chi phí thời gian tăng chỉ **0,106** và chi phí bám vận tốc tăng **0,044**. Vì vậy, một policy chạy chậm vừa phải có thể được trả điểm cao. Đây là bằng chứng lệch giữa incentive training và tiêu chí mong muốn, không chỉ là “PPO cần train lâu hơn”.

Audit slip còn cho thấy giai đoạn tăng tốc có slip dư dương ở 4/5 scenario, còn duy trì giảm tốc có slip thấp hơn ở 4/5. Đây là **liên hệ trong trace**, chưa chứng minh nhân quả: các phase gặp địa hình khác nhau. Chỉ số slip là proxy chênh vận tốc bánh/thân, không phải phép đo trực tiếp tiếp xúc bánh.

## 6. Pilot rough đang chạy tại mốc báo cáo

Output: `rl_runs/rough_recovery_sigma_pilot_v1`, **contract revision 48**.

| Thiết lập | Giá trị |
|---|---|
| Ngân sách | 20.480 bước |
| Seed training | 17000 |
| Khởi tạo | Cùng khởi tạo mới nguyên bản của observable v2; actor/critic mới, optimizer mới; không nạp checkpoint đã train |
| Thay đổi duy nhất trong config | `velocity_sigma_m_s: 0.4 → 0.1` |
| Tác dụng | Phạt sai vận tốc mạnh hơn 16 lần ngoài holding; phạt vận tốc trong holding vẫn bằng 0 |
| Không đổi | Reward weights khác, controller, estimator, terrain, observation, exploration, ramp và physical scoring |
| Bài toán | E1, fixed half-relief terrain, vật lý nominal; không randomize terrain trong training |
| Tiến độ đã ghi | 15.360 / 20.480 bước — 75% |
| Critic EV gần nhất | 0,961 trong training |
| Value loss gần nhất | 0,00287 trong đơn vị reward learner đã scale |
| Kết quả đánh giá cuối | Chưa có tại mốc chốt báo cáo |

Các episode training gần nhất khoảng 29,3–29,7 s và bám đường khoảng 1,6–1,7 cm. Đây là dữ liệu rollout đang học, **không thay thế phép so sánh deterministic với PI**.

Sau training, runner so PPO/PI toàn tốc/PI khớp thời gian trên 17100–17104. Chỉ khi qua toàn bộ điều kiện mới thử cùng model trên seed 18100–18104 với nominal, friction thấp và mass/inertia tăng 15%. Không tự train dài hơn hoặc chạy Optuna khi fail.

Các tiêu chí giữ nguyên gồm đến đích vật lý/đúng cổng tuyến, không rollover, RMSE đường ≤5 cm, sai lệch pose trung bình từng episode ≤10 cm, phục hồi cruise ≥0,95, có slowdown/recovery, thời gian ≤1,15 lần PI toàn tốc và các điều kiện cửa sổ rung/slip đã công bố. Bộ đánh giá nhỏ này vẫn chưa chứng minh unseen-terrain hay repeatability qua nhiều seed training.

## 7. Các bước tiếp theo có căn cứ

### Rough

1. Hoàn thành pilot sigma hiện tại, giữ nguyên contract và chấm điểm.
2. Đọc trace để kiểm tra giảm tốc ở nhiễu, phục hồi sau đó và slip khi tăng tốc. Nếu chỉ luôn chạy nhanh hoặc vẫn cruise chậm, không gọi là đã học thích nghi.
3. Nếu đạt, thực hiện confirmation mới về seed và physics đã định trước; sau đó mới kiểm tra thêm seed training độc lập và terrain/layout giữ lại.
4. Trước curriculum E1/N1/S1, xác nhận profile route-PI phù hợp **đúng contract đang dùng**. Kết quả feasibility PI trên half-relief không chứng minh PPO đã học N1/S1 hay map gốc đã được sửa.
5. Chỉ mở study Optuna mới khi mục tiêu và cơ chế học có tín hiệu hữu ích. Giữ evaluation objective cố định; không nhập score lịch sử không tương thích.

### Flat

1. Giữ pilot slip thất bại làm bằng chứng; không tăng penalty tiếp chỉ vì slip còn cao.
2. Dùng kết quả authority screening đã có để thiết kế một thử nghiệm ngắn, khớp điều kiện hơn về tốc độ/ramp tăng tốc quanh cáp thứ hai. Không cần lặp lại nguyên xi screening cũ. So với PI toàn tốc và PI khớp thời gian.
3. Phân biệt schedule biết vị trí cáp với controller có thể triển khai bằng cảm biến thật. Với LiDAR ngang/IMU/encoder, cần chứng minh quan sát và cơ chế phản ứng thực sự đủ cho nhiệm vụ.
4. Nếu control authority mang lại lợi ích giữ được arrival/timing/tracking, mới chạy một PPO pilot có một giả thuyết rõ, critic/optimizer phù hợp contract và reward được kiểm tra contribution.
5. Đạt quality gate rồi mới cân nhắc thêm cáp/adaptive items, train dài hoặc Optuna.

### Vai trò Optuna, Laya và TensorBoard

- **Optuna:** tìm tham số trong không gian và objective đã định. Không tự sửa chassis mắc cạn, input không có trên robot thật hoặc reward sai mục tiêu. Trial bị lỗi service/discovery khác trial hoàn tất nhưng không đạt chất lượng.
- **Laya trong tích hợp hiện tại:** hỗ trợ theo dõi và khuyến nghị. Không tự chỉnh reward, cập nhật policy hoặc chuyển curriculum.
- **TensorBoard:** ghi metric của training; đường success/reward đẹp không thay cho independent physical scoring và đối chứng PI.

Tại mốc kiểm tra, rough pilot đang chạy; không thấy trainer/tuner flat hoặc worker Optuna hoạt động. `docs/flat_reward_critic_diagnostic_2026-10-10/supervisor.log` là log diagnostic đã hoàn thành.

## 8. Dự án đã sẵn sàng sim-to-real chưa?

**Chưa.** Rough hiện đã bỏ các input không có trên phần cứng, là một bước cần thiết, nhưng chưa đủ.

Những việc còn thiếu gồm đo đáp ứng motor và độ trễ thật; hiệu chuẩn IMU/LiDAR/encoder; mass/COM/caster/contact phù hợp robot; định vị độc lập hợp môi trường thật; nhiễu/dropout/dynamics có căn cứ thực nghiệm; kiểm chứng nhiều terrain và nhiều seed training; thử shadow mode rồi thử vật lý có giám sát.

PI đạt 27/27 trên các profile mô phỏng chỉ chứng minh tính khả thi trong bộ đó. Fresh PPO hiện tại mới train fixed E1/nominal. Chưa có bằng chứng nó điều khiển tốt mọi địa hình, thực hiện switching policy trên toàn course đã được xác nhận, hoặc tạo lợi ích trên robot thật.

## 9. Đánh giá cuối cùng

**Không phải mọi đánh giá đều tạo ra cải thiện PPO.** Nhiều thử nghiệm vừa qua thất bại, và chưa có policy thỏa toàn bộ tiêu chuẩn nâng cấp. Báo cáo này giữ nguyên kết quả kém thay vì chọn riêng metric thuận lợi.

Những thành quả rõ nhất hiện nay là: phát hiện score đích đến có thể sai; tách lỗi định vị khỏi lỗi tiếp xúc; chứng minh giới hạn cảm biến thật; sửa imbalance critic; đo được cơ chế giảm tốc hữu ích; và tìm ra reward đang ưu tiên cruise chậm hơn mong muốn.

**Lợi ích RL đã quan sát:** giảm rung ở một số pilot flat, giảm slip ở một số đối chứng rough khớp thời gian, bám đường/đến đích tốt trong các task đã thu hẹp. **Điều chưa đạt:** lợi ích tổng thể đáng tin cậy, slowdown/recovery học được ổn định, khả năng tổng quát và sim-to-real.

Vì vậy, PI vẫn là đối chứng và nền điều khiển chính. Pilot rough hiện tại kiểm tra một nguyên nhân cụ thể; kết quả của nó sẽ quyết định sửa tiếp hay tiến tới xác nhận/tuning, thay vì mặc định train càng lâu càng tốt.

## 10. Nguồn số liệu trong dự án

Các báo cáo giao thức có thể chứa trạng thái lịch sử. Kết quả hoàn tất được đối chiếu với report/JSON của từng run.

1. [Flat: torque và giao diện speed/yaw](FLAT_SPEED_YAW_PILOT_2026-10-07.md).
2. [Flat: estimator và feedback](FLAT_FEEDBACK_PILOT_2026-10-08.md).
3. [Flat: audit critic và reward](FLAT_REWARD_CRITIC_CORRECTION_2026-10-10.md).
4. [Flat: scale-only và aligned-impact](../rl_runs/flat_reward_validation_v1/REPORT.md).
5. [Flat: lặp seed training 43](../rl_runs/flat_value_scaled_seed43_v1/REPORT.md).
6. [Flat: pilot slip và PI khôi phục](../rl_runs/flat_targeted_pi_recovery_v2/REPORT.md).
7. [Flat: đáp ứng quanh cáp thứ hai](targeted_cable_response_2026-10-10/REPORT.md).
8. [Rough: trial 8 và PI matching](../rl_runs/rough_trial8_validation_v1/REPORT.md).
9. [Rough: bằng chứng stall/định vị](ROUGH_WALL_LOCALIZATION_2026-10-09.md).
10. [Nền tảng contact, cảm biến và control authority](rl_foundations_2026-10-11/REPORT.md).
11. [Rough: PI hardware-only trên ba profile](../rl_runs/rough_hardware_confirmation_v1/REPORT.md).
12. [Rough: reactive authority](ROUGH_REACTIVE_AUTHORITY_2026-10-11.md).
13. [Rough: observable v2 comparison](../rl_runs/rough_observable_pilot_v2/comparison.json).
14. [Rough: audit trace và contribution reward](rough_observable_audit_2026-10-11/REPORT.md).
15. [Rough: pilot sigma revision 48](ROUGH_RECOVERY_SIGMA_PILOT_2026-10-11.md), [live status](../rl_runs/rough_recovery_sigma_pilot_v1/status.json).

Các run trong `rl_runs/` có thể không được đưa lên Git. Báo cáo này lưu các bảng số liệu chính trong `docs/`; để tái lập đầy đủ vẫn cần model, config, trace và manifest gốc.

## Cập nhật sau mốc chốt: khoảng 21:30 ngày 11/10

Pilot rough sigma hoàn tất 20.480 bước nhưng **không đạt behavior/quality gate**:
5/5 đến đích, 27,40 s, RMSE 1,67 cm; năng lượng slip trong cửa sổ nhiễu tăng
18,75% so với PI khớp thời gian. Nó sửa cruise chậm nhưng giảm tốc chưa đủ.

Đã chạy so sánh rough reactive và thử một lịch giảm tốc ở cáp thứ hai của flat.
Chi tiết và số liệu đầy đủ ở [báo cáo reference mới](DISTURBANCE_REFERENCE_COMPARISONS_2026-10-11.md).

- **Rough reactive:** 5/5 đến đích; 28,14 s so với PI khớp thời gian 28,10 s;
  năng lượng rung trong cửa sổ giảm 10,92%, năng lượng slip tăng 4,89%, vẫn trong
  giới hạn đã đặt. Reference qua screen, PPO cũ không qua. Đã chuẩn bị contract
  revision 49 thêm đúng một cost về tốc độ mục tiêu 0,70 khi holding; chưa train.
- **Flat schedule:** 5/5 đến đích; 18,52 s so với PI toàn tốc 17,58 s và PI khớp
  thời gian 18,42 s. Năng lượng rung tại cáp thứ hai giảm 63,76% so với PI khớp
  thời gian. Tuy nhiên, rung toàn hành trình chỉ giảm 7,32% so với PI toàn tốc,
  slip tăng 0,53%, và vượt giới hạn promotion 18,5 s. Không khởi chạy PPO pilot
  có điều kiện; không đổi ngưỡng sau khi xem kết quả.

Hai so sánh đã hoàn tất, không thực hiện cập nhật PPO. Optuna/curriculum vẫn giữ
lại. Các phần phía trên phản ánh đúng snapshot 19:24, không phải trạng thái đang
train tại thời điểm cập nhật này.

## Cập nhật triển khai sau đó: pilot revision 49 và kiểm tra flat có điều kiện

Đã khởi chạy rough revision 49 trên CUDA: 20.480 bước, seed 17000, cùng khởi tạo
actor mới ban đầu, critic/optimizer mới. Chỉ bổ sung cost tốc độ trong pha holding;
terrain, controller, quan sát, ramp và chấm điểm vật lý giữ nguyên. Runner đánh giá
PPO với PI toàn tốc và PI khớp thời gian. Chỉ khi toàn bộ gate đạt mới mở study
rough mới với tối đa sáu trial. Nếu fail, audit exposure thực tế trong training và
giữ Optuna lại; không tự tăng reward hay kéo dài model thất bại.

Audit flat cho thấy phần rung tăng đáng kể nằm **trước** khi phanh ở cáp thứ hai,
khi cả hai controller còn dùng speed scale 1. Vì vậy không quy nguyên nhân đó cho
lệnh phanh về sau. Slip/rung sau x=4,80 rất nhỏ. Năm trace đều yên trong đoạn
x=4,55–4,60, hỗ trợ một chỉnh sửa nhỏ: bắt đầu phục hồi ở 4,55 thay vì 4,60 m.
Không sửa điểm bắt đầu phanh, tốc độ thấp, ramp, cáp đầu hoặc gate.

Flat đã được xếp hàng sau workflow rough để tránh tranh tài nguyên Gazebo. Chỉ
nếu schedule sửa đạt gate mới chạy pilot 20.480 bước với contract mới, actor
tương thích và critic/optimizer mới. Contract đó khai báo rõ dùng **vị trí cáp
trên bản đồ đã biết + pose ước lượng**, thay các input preview hướng xuống. Đây
không phải dự đoán cáp chưa biết từ LiDAR ngang. Nếu pilot đạt mới mở study flat
riêng; mọi model và study cũ giữ nguyên.

Các nhánh điều kiện chưa có kết quả cuối tại mốc khởi chạy này. Chi tiết, log và
lệnh theo dõi ở [workflow chuẩn bị tuning](COURSE_OPTUNA_READINESS_WORKFLOWS_2026-10-11.md).
