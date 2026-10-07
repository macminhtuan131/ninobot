# Tổng quan tài liệu và đối chiếu với Nino

Ngày tra cứu: **04/10/2026**. Có **32 công trình** trong danh mục, kèm tài liệu phần mềm chính thức. Đây là tổng quan có phạm vi, không phải tuyên bố đã tìm mọi bài báo hay một systematic review theo PRISMA.

Danh mục có cấu trúc để tra cứu lại: [sources.json](sources.json). Báo cáo dự án: [tiến độ và đối chiếu Nino](../BAO_CAO_TIEN_DO_VA_DOI_CHIEU_RL_NINO_2026-10-04.md).

## 1. Phạm vi và cách tìm

Tìm bằng tiêu đề chính xác và các nhóm từ khóa: `wheeled robot reinforcement learning rough terrain`, `residual reinforcement learning PID robot control`, `mobile robot path tracking robust PID`, `Nav2 regulated pure pursuit MPPI DWB`, `automatic terrain curriculum wheeled mobility`, `IMU proprioception adaptation`, `sim-to-real dynamics randomization`, `Optuna Hyperband reward design Eureka`, `hierarchical policy switching`, và tiêu đề bài warehouse do người dùng cung cấp. Kiểm tra thêm công trình 2025–2026.

Ưu tiên bài gốc trên arXiv, trang tác giả, tạp chí/hội nghị và tài liệu chính thức. Dùng bài survey để mở rộng phạm vi, không coi nó là bằng chứng thực nghiệm của một thuật toán cụ thể. Không dùng Reddit, blog tổng hợp hoặc trích dẫn bên thứ ba làm căn cứ kỹ thuật.

Mức tiếp cận:

- **FT**: truy cập được toàn văn; kiểm tra các phần phương pháp/kết quả liên quan, không hàm ý đã tái lập thực nghiệm.
- **A**: kiểm tra trang bài và abstract; nhận xét chỉ dựa trên thông tin đó.
- **I**: thông tin/đoạn trích được lập chỉ mục từ nguồn xuất bản chính; mở trực tiếp gặp hạn chế. Cần lấy toàn văn trước khi dùng chi tiết để triển khai.

Không so trực tiếp phần trăm thành công giữa các bài và Nino: robot, bản đồ, success criterion, số episode và điều kiện khác nhau. Các nhận xét “có thể áp dụng” bên dưới là **suy luận thiết kế**, chưa phải cải thiện đã đo trên Nino.

## 2. Công trình gần nhất với mục tiêu của dự án

| ID | Công trình, năm và nguồn gốc | Họ làm gì; Nino khác ở đâu | Mức |
|---|---|---|---|
| P05 | Xu, Pan, Xiao, **[Reinforcement Learning for Wheeled Mobility on Vertically Challenging Terrain](https://arxiv.org/html/2409.02383v2)**, 2024 | PPO, terrain curriculum, elevation encoder SWAE, điều khiển tốc độ/góc lái qua PID trong Chrono; có robot V4W thật. Nino dùng differential drive có caster, history cảm biến và residual torque từng bánh trong Gazebo. | FT |
| P06 | Xu, Pan, Xiao, **[VertiSelector: Automatic Curriculum Learning for Wheeled Mobility on Vertically Challenging Terrain](https://cs.gmu.edu/~xxiao2/papers/vs.pdf)**, 2025; [trang tác giả](https://xutong05.github.io/publication/vs/) | Chọn terrain theo learning potential/TD error, có kiểm chứng mô phỏng và vật lý. Curriculum Nino là các stage định trước, chuyển bằng cửa sổ success; chưa tự chọn địa hình theo TD error. | FT |
| P03 | Johannink và cộng sự, **[Residual Reinforcement Learning for Robot Control](https://arxiv.org/html/1812.03201v2)**, 2018, công bố ICRA 2019 | Ghép feedback controller với phần bù RL; thực nghiệm lắp ráp có tiếp xúc. Nino áp dụng nguyên lý phần bù cho wheel PI và tiếp xúc bánh–địa hình. Residual RL đã có tiền lệ. | FT |
| P04 | Silver, Allen, Tenenbaum, Kaelbling, **[Residual Policy Learning](https://arxiv.org/abs/1812.06298)**, 2018/2019 | Học cải thiện controller có sẵn trong manipulation, gồm controller thiết kế tay và MPC. Bài hỗ trợ hướng giữ baseline tốt; không chứng minh residual luôn cải thiện mọi robot. | A |
| P09 | Lee và cộng sự, **[Learning Robust Autonomous Navigation and Locomotion for Wheeled-Legged Robots](https://arxiv.org/abs/2405.01792)**, 2024 | Hệ phân cấp locomotion/navigation, privileged learning, nhiệm vụ đô thị thực tế. Robot có chân và khả năng đi/lăn; Nino không có chân, hiện chỉ theo đường thẳng và chưa triển khai supervisor switching. | A |
| P29 | Li và cộng sự, **[Research on reinforcement learning based warehouse robot navigation algorithm in complex warehouse layout](https://arxiv.org/abs/2411.06128)**, 2024 | PP-D kết hợp Dijkstra với PPO để navigation trong kho. Nino tập trung ổn định trajectory và tương tác vật lý bằng wheel torque. PDF đã đọc phần phương pháp/thực nghiệm; metric của bài chưa đủ để so head-to-head với Nino. | FT, PDF người dùng |

**Hệ quả cho tính mới:** “dùng PPO”, “dùng IMU”, “curriculum”, “RL cộng PID/PI” và “phân cấp/chuyển hành vi” đều không phải ý tưởng mới độc lập. Tiềm năng của Nino nằm ở bài toán và cách kiểm chứng: robot caster nhỏ, pothole/cable theo kích thước bánh, kiểm soát phần bù hai bánh, chấm bằng pose vật lý và đánh giá handoff trên cùng course.

## 3. Điều khiển truyền thống, path tracking và navigation

| ID | Công trình | Nội dung liên quan và giới hạn đối chiếu | Mức |
|---|---|---|---|
| P11 | Normey-Rico, Alcalá, Gómez-Ortega, Camacho, **[Mobile robot path tracking using a robust PID controller](https://www.sciencedirect.com/science/article/pii/S0967066101000661)**, 2001 | PID path tracking với mô hình đơn giản có trễ và thiết kế robust; có thực nghiệm. Baseline hiện tại của Nino là wheel-speed PI với reference thẳng, chưa phải toàn bộ controller PID bám đường của bài. | I |
| P12 | Macenski, Singh, Martin, Gines, **[Regulated Pure Pursuit for Robot Path Tracking](https://arxiv.org/html/2305.20026v1)**, 2023 | Điều chỉnh tốc độ theo độ cong và nguy cơ va chạm, có trong Nav2. Là đối chứng thích hợp cho outer path tracking; vẫn cần wheel controller và không mặc nhiên mô hình hóa caster mắc pothole. | FT |
| P13 | Fox, Burgard, Thrun, **[The Dynamic Window Approach to Collision Avoidance](https://publications.ri.cmu.edu/the-dynamic-window-approach-to-collision-avoidance)**, 1997 | Local motion/collision avoidance có xét khả năng chuyển động của robot; đã thử trên RHINO. DWA/DWB không tự trở thành bộ bù torque cho va đập và mất tải bánh. | A, trang cơ quan tác giả |
| P14 | Rösmann, Hoffmann, Bertram, **[Integrated online trajectory planning and optimization in distinctive topologies](https://www.sciencedirect.com/science/article/pii/S0921889016300495)**, 2017; [danh mục tác giả](https://rst.etit.tu-dortmund.de/lehrstuhl/team/roesmann/) | TEB tối ưu trajectory và thời gian trong các topology khác nhau, có ràng buộc nonholonomic. Khác lớp điều khiển vật lý bánh của Nino; chưa đọc được toàn văn nguồn xuất bản trong phiên này. | I |
| P15 | Williams, Aldrich, Theodorou, **[Model Predictive Path Integral Control using Covariance Variable Importance Sampling](https://arxiv.org/abs/1509.01149)**, 2015 | Điều khiển dự đoán bằng sampling trajectory, nền tảng MPPI. Cần mô hình/cost; Nino có thể dùng MPPI ở lớp reference và residual ở lớp bánh, nhưng chưa triển khai hoặc đo cách ghép đó. | A |
| P16 | Ohnishi, Takahashi, **[DWPP: Dynamic Window Pure Pursuit Considering Velocity and Acceleration Constraints](https://arxiv.org/abs/2601.15006)**, 2026 | Pure pursuit xét giới hạn vận tốc/gia tốc trực tiếp. Có liên hệ với giới hạn wheel speed/rate của Nino; chức năng rolling mới không đồng nghĩa bản Nav2 Jazzy cài tại máy đã có nó. | A |

### Tài liệu chính thức dùng khi thiết kế đối chứng

- **[Nav2 Navigation Servers, Jazzy](https://docs.nav2.org/jazzy/getting_started/navigation_concepts/navigation_servers/)**: phân biệt planner, controller, behavior và tổ chức navigation.
- **[Nav2 RPP](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/controller_plugins/configuring_regulated_pp/)**: cơ chế regulation và collision checking. Đây là tài liệu rolling; cần đối chiếu bản Jazzy trước khi sao chép cấu hình.
- **[Nav2 MPPI](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/controller_plugins/mppi_controller/configuring_mppic/)**: motion model differential/omni/Ackermann, cost critics và sampling prediction. Không lấy tốc độ benchmark trong docs làm tốc độ đo trên máy Nino.
- **[Nav2 AMCL](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/)** và **[robot_localization, tài liệu trong repo chính thức](https://github.com/cra-ros-pkg/robot_localization/blob/rolling-devel/doc/configuring_robot_localization.rst)**: định vị bằng laser/map và fusion cảm biến. EKF encoder–IMU không tự cung cấp vị trí tuyệt đối XY khi bánh trượt.

## 4. Nền tảng RL và phương pháp huấn luyện

| ID | Công trình | Có thể học gì cho Nino | Mức |
|---|---|---|---|
| P01 | Schulman và cộng sự, **[Proximal Policy Optimization Algorithms](https://arxiv.org/abs/1707.06347)**, 2017 | Cập nhật policy bằng surrogate objective có clipping. Là nền tảng thuật toán đang dùng, không đảm bảo success tăng đơn điệu. | A |
| P02 | Schulman và cộng sự, **[High-Dimensional Continuous Control Using Generalized Advantage Estimation](https://arxiv.org/abs/1506.02438)**, 2015/2016 | GAE cân bằng bias/variance của advantage. Nino dùng `gae_lambda`; thay nó không sửa được lỗi pose hoặc definition của task. | A |
| P26 | Haarnoja, Zhou, Abbeel, Levine, **[Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning with a Stochastic Actor](https://arxiv.org/abs/1801.01290)**, 2018 | Replay/off-policy là hướng thử khi sampling vật lý đắt. Chưa có benchmark SAC trong Nino; không suy ra đổi PPO sang SAC sẽ chữa current failure. | A |
| P25 | Henderson và cộng sự, **[Deep Reinforcement Learning that Matters](https://arxiv.org/abs/1709.06560)**, 2017/2018 | Nhấn mạnh biến thiên, tái lập và báo cáo đánh giá. Cần nhiều seed huấn luyện, protocol cố định; không chọn riêng seed thành công để công bố tỷ lệ. | A |
| P17 | Akiba và cộng sự, **[Optuna: A Next-generation Hyperparameter Optimization Framework](https://arxiv.org/abs/1907.10902)**, 2019 | Tối ưu search space do người phát triển khai báo. Nino split tuner tìm 5 reward weights và 4 PPO hyperparameters; Optuna không viết lại reward logic. | A |
| P18 | Li và cộng sự, **[Hyperband: A Novel Bandit-Based Approach to Hyperparameter Optimization](https://arxiv.org/abs/1603.06560)**, 2016/2018 | Phân bổ ngân sách và dừng sớm cấu hình yếu. Có thể giảm chi phí tuning; RL học chậm khiến cắt quá sớm loại nhầm cấu hình. Split tuner hiện chưa triển khai pruning trung gian. | A |
| P19 | Ma và cộng sự, **[Eureka: Human-Level Reward Design via Coding Large Language Models](https://arxiv.org/abs/2310.12931)**, 2023/2024 | LLM tạo và sửa mã reward qua vòng đánh giá. Có thể đề xuất candidate, nhưng cần evaluator cố định độc lập và chi phí train; Nino chưa tích hợp Eureka. | A |
| P20 | Florensa và cộng sự, **[Reverse Curriculum Generation for Reinforcement Learning](https://arxiv.org/abs/1707.05300)**, 2017 | Mở rộng trạng thái bắt đầu từ gần đích ra xa. Gợi ý học arrival trước, sau đó tăng khoảng cách; khác curriculum thêm cable hiện có. | A |
| P21 | Narvekar và cộng sự, **[Curriculum Learning for Reinforcement Learning Domains: A Framework and Survey](https://jmlr.org/papers/v21/20-212.html)**, 2020 | Khung phân loại curriculum/transfer. Hỗ trợ thiết kế difficulty, tiêu chí chuyển stage và replay; survey không cung cấp một lịch tối ưu riêng cho Nino. | A |
| P22 | Peng, Andrychowicz, Zaremba, Abbeel, **[Sim-to-Real Transfer of Robotic Control with Dynamics Randomization](https://arxiv.org/abs/1710.06537)**, 2017/2018 | Randomize dynamics khi train; thử trên thao tác robot. Gợi ý friction, delay, mass/payload, motor uncertainty; tính hiệu quả trên Nino cần đo riêng. | A |
| P23 | Tobin và cộng sự, **[Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World](https://arxiv.org/abs/1703.06907)**, 2017 | Randomization thị giác để transfer perception. Không đồng nhất với randomization động lực học wheel contact; Nino không dùng image actor. | A |
| P24 | Bacon, Harb, Precup, **[The Option-Critic Architecture](https://arxiv.org/abs/1609.05140)**, 2016/2017 | Học policy, termination và lựa chọn options. Switch theo vị trí có latch dự kiến ở Nino là supervisor thiết kế tay, chưa phải Option-Critic. | A |

## 5. Thích nghi từ cảm biến và các robot khác cấu trúc

| ID | Công trình | Liên quan và giới hạn | Mức |
|---|---|---|---|
| P07 | Kumar, Fu, Pathak, Malik, **[RMA: Rapid Motor Adaptation for Legged Robots](https://arxiv.org/abs/2107.04034)**, 2021 | Base policy và adaptation module cho thay đổi địa hình/payload; robot quadruped thật. History CNN Nino có thể suy luận động học ngắn hạn, nhưng chưa có module adaptation huấn luyện như RMA. | A |
| P08 | Miki và cộng sự, **[Learning robust perceptive locomotion for quadrupedal robots in the wild](https://arxiv.org/abs/2201.08117)**, 2022 | Kết hợp proprioception/exteroception bằng recurrent encoder có attention, xử lý perception không đáng tin. Gợi ý train robustness cho terrain preview; khác actor feedforward có history của Nino. | A |
| P10 | Rudin, Hoeller, Reist, Hutter, **[Learning to Walk in Minutes Using Massively Parallel Deep Reinforcement Learning](https://arxiv.org/abs/2109.11978)**, 2021/2022 | GPU mô phỏng hàng loạt và curriculum, có transfer robot. Nino dùng Gazebo CPU và ROS; CUDA cho policy không tạo cùng mức parallel physics. | A |
| P27 | Kendall và cộng sự, **[Learning to Drive in a Day](https://arxiv.org/abs/1807.00412)**, 2018 | Học lane following từ ảnh trực tiếp trên xe, có safety driver. Chứng minh hướng feedback từ môi trường, nhưng không cùng wheel/caster terrain-control task. | A |
| P28 | Xiao, Liu, Warnell, Stone, **[Motion Planning and Control for Mobile Robot Navigation Using Machine Learning: a Survey](https://arxiv.org/abs/2011.13112)**, 2020/2022 | Phân loại quan hệ giữa navigation cổ điển và học máy. Giúp xác định Nino thuộc lớp learned control augmentation; không phải đã thay mọi lớp navigation. | A |
| P30 | Li và cộng sự, **[CTBC: Contact-Triggered Blind Climbing for Wheeled Bipedal Robots with Instruction Learning and Reinforcement Learning](https://arxiv.org/abs/2509.02986)**, 2025, bản sửa 2026 | Contact trigger và motion chân để vượt vật cản từ proprioception. Nino không có chân; không thể chuyển cơ chế nâng chân sang caster robot. | A |
| P31 | Sun và cộng sự, **[ATRos: Learning Energy-Efficient Agile Locomotion for Wheeled-legged Robots](https://arxiv.org/abs/2510.09980)**, 2025 | Ước lượng trạng thái ngoài từ proprioception, phối hợp chân/bánh; trang bài ghi submitted workshop. Cần phân biệt preprint/workshop với công trình đã được kiểm chứng độc lập. | A |
| P32 | Yang và cộng sự, **[Energy-Efficient Omnidirectional Locomotion for Wheeled Quadrupeds via Predictive Energy-Aware Nominal Gait Selection](https://arxiv.org/abs/2601.10723)**, IROS 2025, trang arXiv 2025/2026 | Chọn nominal gait bằng dự đoán công suất, cộng residual RL. Nino chỉ phạt effort/torque proxy, chưa đo công suất hay năng lượng điện thật. | A |

## 6. Cách áp dụng có thứ tự

1. **Ưu tiên P03/P04 + P11/P12:** giữ controller baseline tốt, giới hạn phần bù theo failure thật; so với PI/PID bám đường và RPP trước khi thêm network.
2. **P06/P20/P21:** nếu stage 0 còn không ổn định, dùng curriculum khoảng cách/arrival; khi ổn mới thêm cable, angle và adaptive items. Curriculum không sửa pose sai.
3. **P07/P08/P22:** sau khi localizer và baseline ổn, train trên nhiều terrain/dynamics và noise; thử history/preview ablation để đo khả năng thích nghi thực sự.
4. **P25:** lưu config, geometry hash, model hash, seed và raw trajectories; đối chiếu metric vật lý với metric odometry.
5. **P09/P24:** specialist switching cần transition được kiểm thử; hai policy giỏi riêng chưa chứng minh controller ghép giỏi.
6. **P17/P18/P19:** tuning sau khi task/evaluator đúng. Tránh tối ưu score trên cùng tập seed rồi gọi đó là test độc lập.

## 7. Các giới hạn của lần tra cứu này

Một số trang ScienceDirect/IEEE chặn mở trực tiếp; P11/P14 được đánh dấu I. Hai bài mới về Ackermann off-road và hierarchical residual bicycle đã tìm thấy nhưng không đưa vào bảng so sánh kỹ thuật vì chưa xác minh đủ nội dung. Không có hardware experiment mới trên Nino; không thực thi code của các bài báo. Kết luận “Nino có contribution mới” vẫn cần ablation, đối chứng và kiểm tra literature bổ sung chuyên sâu.

Danh mục này hỗ trợ báo cáo dự án; nó không thay thế thẩm định chất lượng từng venue. Tỷ lệ của bài warehouse được ghi theo tác giả, không dùng để kết luận nó tốt hơn Nino hay hơn Nav2.
