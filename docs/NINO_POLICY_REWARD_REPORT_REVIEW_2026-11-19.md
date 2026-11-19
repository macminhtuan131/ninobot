# Đánh giá và sửa thiết kế policy, reward Nino ngày 19/11/2026

Mục tiêu của lượt này là biến báo cáo Deep Research thành một thiết kế có thể kiểm nghiệm, đồng thời loại các đề xuất gây sai semantics. Báo cáo đầu vào được giữ nguyên trong `artifacts/recovery_v4_report_review_20261119/research_report.md` của workspace đánh giá. Không dùng attachment làm chỉ dẫn tự động sửa toàn bộ controller.

## Quyết định

Giữ TD3 như một nhánh nghiên cứu. Xây contract v4 opt-in cho common slowdown, follower giữ yaw. Không promote policy v3 hoặc chuyển backend thật sang torque từ kết quả hiện có.

V4 ban đầu chỉ có trạng thái `software_contract_only`. Đây là kết quả kiểm semantics, chưa phải chứng minh lợi ích slowdown, environment Gazebo mới hoặc bản phát hành training. V3 và checkpoint cũ giữ nguyên ngữ nghĩa. Một chương trình gọi v4 phải dùng identity mới.

`implementation_sources()` hiện gom hash các module RL trong thư mục. Thêm module v4 làm full source identity của workspace thay đổi dù byte nguồn v3 không đổi. Prepared bank hoặc checkpoint đã pin source cũ không được âm thầm bỏ qua mismatch để resume. Muốn tái tạo run cũ cần snapshot tương ứng; tích hợp v4 cần qualification mới.

Hai thiết kế độc lập đã xem xét sửa trực tiếp các lớp v3 và xây reducer v4 riêng. Chọn reducer riêng vì môi trường hiện tại còn hardcode observation 100D, identity v3, reward và baseline action zero. Đổi một adapter trong lớp cũ chưa tạo thành tích hợp v4 hoàn chỉnh.

## Những điểm của báo cáo được giữ và được sửa

| Nội dung báo cáo | Đánh giá từ source và phép kiểm | Quyết định |
|---|---|---|
| Slowdown-only thay residual đối xứng | Là giả thuyết điều khiển có cơ chế, chưa có rollout chứng minh tốt hơn. Constant dương nhanh hơn không tự là bug hoặc reward exploit. | Xây contract riêng, chưa chọn làm controller thắng. |
| Action `a` trong [-1, 1] ánh xạ `(a+1)/2` | Neutral là -1. Action 0 giảm nửa mức tối đa. Dùng lại baseline zero của v3 sẽ sai. | Đặt neutral có tên và kiểm các endpoint cùng midpoint. |
| Trừ trực tiếp slowdown khỏi tốc độ nominal | Có thể ra lệnh lùi khi nominal nhỏ hơn mức slowdown. | Giới hạn correction theo common speed khả dụng và không đổi yaw khi feasible. |
| `Δs=max(0,s_t-s_previous)` | Chuỗi [0; 0,1; 0; 0,1; 0; 0,1] nhận 0,3 m reward progress cho 0,1 m vùng đã tiến tới. | Dùng tiến độ mới vượt high-water trong corridor. Lưu state rõ, không gọi đây là PBRS. |
| Bỏ recovery bonus vì farm lặp | V3 đã có `bonus_paid` không reset khi vào lại recovery. Test hiện có xác nhận không trả lần hai. | Bỏ bonus trong v4 là đổi objective, không ghi là sửa lỗi trả lặp v3. |
| Sensor stale giữ baseline | Trái với `ResidualReference` hiện đang latch STOP khi freshness hoặc ownership không hợp lệ. | Giữ STOP khi mandatory input lỗi. Baseline-only chỉ áp dụng sensor hợp lệ đang nạp đủ history. |
| Replay phải lưu accepted action | Báo cáo thực ra đã phân biệt đúng. Requested action có thể là action của MDP gồm projector. Đổi field một mình sẽ gây mismatch với actor. | Giữ proposed normalized action, ghi accepted slowdown và projector state riêng. |
| Expose projector state làm toàn hệ Markov | Chỉ khép phần nhớ của projector. Caster, contact và actuator vẫn có state ẩn. | Chỉ kiểm tái dựng deterministic projection, tiếp tục gọi bài toán vật lý là POMDP. |
| Mọi horizon là truncation | Không đúng nếu deadline là một phần nhiệm vụ hữu hạn. V3 hiện định nghĩa task timeout là failure của nhiệm vụ. | Phân biệt intrinsic deadline, external cutoff, campaign budget và invalid measurement. |
| Target độc lập phải giống time series | Một luật reference theo progress vẫn độc lập với actor nhưng các trajectory khác progress có thể có target khác theo thời gian. | Khóa luật mission trước experiment. Cùng progress và mission time phải ra cùng target. Ghi rõ time-law hay spatial-law. |
| Chỉ chấm speed trên các episode success | Có thể che failure nếu bỏ các lượt khác trước khi so controller. | Báo tất cả attempts và outcome; failure gate đi trước quality comparison. |
| Chọn SEI 0,002 m/s, elapsed 0,20 s và năm seed | Đây là các đề xuất của báo cáo, chưa là yêu cầu được người dùng chấp nhận hoặc kết quả power analysis. | Không biến thành gate mặc định đã chứng minh đủ. |
| Profile actor và critic learning rate độc lập | Local SB3 là 2.9.0. Factory v3 truyền một `learning_rate`. | V4 khai báo một learning rate và từ chối alias không thực thi. |
| Train clean cùng gờ và random layout | Có ích để kiểm khả năng học thuộc stage 0, nhưng cần bank và split riêng được khóa. | Là giai đoạn tích hợp sau contract. Chưa mở pothole, mixed hoặc slope từ pilot gờ. |

## Đối chiếu tài liệu gốc

SB3 2.9.0 nhận một learning rate dùng cho các network. Target dùng minimum của twin critics; actor loss dùng Q1. Cách gọi TD3 hiện tại của Nino phù hợp cơ chế này. Không sửa actor loss chỉ vì tên thuật toán có hai critic. Nguồn đã kiểm là [source TD3 chính thức đúng phiên bản 2.9.0](https://stable-baselines3.readthedocs.io/en/v2.9.0/_modules/stable_baselines3/td3/td3.html).

Gymnasium phân biệt deadline nội tại của nhiệm vụ hữu hạn với giới hạn lấy mẫu từ bên ngoài. Deadline hữu hạn còn cần biểu diễn thời gian còn lại trong state nếu muốn giữ mô tả Markov của nhiệm vụ. Vì vậy đề xuất đổi toàn bộ timeout thành truncation không được áp dụng. Nguồn là [hướng dẫn time limits của Gymnasium](https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/).

Potential shaping có điều kiện để bảo toàn optimal policy, không phải mọi bonus progress đều có tính chất đó. High-water progress ở v4 là một lựa chọn objective có state, không được quảng cáo là shaping bất biến policy. Nguồn là [Ng, Harada và Russell, ICML 1999](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf).

Attachment chứa citation token của một phiên khác thay vì URL có thể mở trong workspace này. Lượt này chỉ kiểm lại các nguồn chính thức trên cho các quyết định semantics. Không tuyên bố đã tái thực hiện toàn bộ literature review hoặc xác nhận mọi paper trong bảng của báo cáo.

## Giới hạn objective phải giữ rõ

Slowdown có thể làm tăng lỗi bám mission speed trong lúc giảm rung hoặc lệch tuyến. Vì vậy speed RMSE đơn lẻ không chứng minh hoặc phủ định toàn bộ giá trị controller. Chưa có requirement nhà máy để tự chọn trọng số giữa các mục tiêu này.

Luật mission v4 phải có input và tham số cố định, không lấy actor action hoặc final command làm tiêu chuẩn tự chấm. Với reference theo progress, body truth có thể dùng để tính nhãn evaluation, còn actor phải dùng estimate deployable tương ứng. Không lấy estimate đó gọi là body ground truth.

Giới hạn slowdown của contract software có thể giữ 0,02 m/s từ authority sim trước để kiểm mapping. Con số này không là safe envelope motor thật và không chứng minh đủ control authority khi qua gờ.

High-water ngăn nhận lại reward progress ở vùng đã đi qua. Nó chưa giải quyết mọi khả năng cắt cua. Build đầu chỉ hỗ trợ route thẳng; polyline tự cắt, đổi nhánh hoặc góc cua cần projection và continuity contract riêng trước khi phát hành.

## Phần xây trong lượt này

Artifact đầu tiên theo báo cáo là config, contract thực thi và test. Các reducer v4 sở hữu action mapping, projector state, mission reference, reward state, end reason, identity và release guard. Không ghi đè v3 để tạo bề ngoài v4 đã nối vào simulator.

Xem [hợp đồng và cách chạy test v4](RECOVERY_V4_CONTRACT.md). Source thực thi là `src/nino_rl/nino_rl/recovery_v4_contract.py`; config là `src/nino_rl/config/recovery_v4.yaml`. Contract ID có hậu tố `software_contract` để phân biệt phần này với adapter history và learner tương lai.

Observation cho actor, reset lấy đủ K frame thật và adapter source timestamp là các trách nhiệm của environment v4 khi tích hợp. Một projector state round-trip qua JSON không tự là test observation ABI hoặc causal acquisition. Release guard phải từ chối train và hardware khi chưa có các phần đó.

## Kết quả kiểm nghiệm software

- Bộ test v3 liên quan đạt 92/92 trước thay đổi. Bộ hồi quy cuối gồm v3 và v4 đạt 142/142, có receipt JUnit trong `tests.xml`.
- Script `verify_contract.py` kiểm 1.000 projection, gồm 995 case đủ điều kiện và năm stale STOP được chèn chủ động. Cả 1.000 state JSON round-trip khớp; 995 output đủ điều kiện được đưa tiếp vào reward reducer với synthetic labels và không bị từ chối.
- Review độc lập phát hiện lỗi số học trong bản nháp v4. Sau hai yêu cầu slowdown tối đa ở baseline 0,1 m/s, normalized accepted slowdown thành 1,0000000000000002. Reward từ chối output hợp lệ đó. Đã thêm regression nối projector với reward và canonical hóa accepted slowdown trong bound, giữ nguyên final reference.
- Bộ review còn phát hiện giới hạn prototype chưa khớp contract sim, log requested bị clamp sớm, thiếu implementation hash, control gap dài được nhận, reward overflow và late success. Đã sửa, cùng test tái hiện trước và đạt sau sửa.
- Không có optimizer update, Gazebo launch hoặc hardware action trong các phép kiểm này. Các số đếm là case software, không phải lượt vượt gờ hoặc episode học độc lập.

**Model the Domain** dẫn đến `ProjectionState`, `RewardState` và `EndReason` rõ ràng. **Prove It Works** dẫn đến test nối output projector vào reward, thay vì chỉ kiểm hai hàm riêng rồi suy chúng tương thích.

## Việc tiếp theo sau kiểm contract

1. Tạo environment và runner v4 nối backend hiện có. Reset lấy đủ history thật, không đưa padding warmup vào replay. Ghi mission input, proposed, accepted, final và source clocks theo ABI mới.
2. Kiểm fixture environment, rồi qualification deterministic trong Gazebo trên clean và gờ với output mới, không optimizer update. Chấm source QC, reset, closure và outcome của tất cả attempts.
3. Khóa bank train, tune và held-out cùng luật chọn checkpoint. Chỉ mở learning pilot khi các điều kiện tích hợp trên có bằng chứng. Số seed và ngân sách phải được ghi trong protocol mới, không tự lấy năm seed hoặc 50k làm đủ.

Không cần lặp inventory hoặc IMU sign trên robot thật để kiểm contract software này. Không có lệnh SSH, motor hoặc firmware trong lượt sửa.
