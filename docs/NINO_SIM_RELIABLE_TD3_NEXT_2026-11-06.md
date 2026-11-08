> Cập nhật06/11: pilot TD3 RELIABLE với lifecycle từng episode đã đóng; xem [kết quả](../docs/NINO_SIM_RELIABLE_TD3_RESULT_2026-11-06.md) và [protocol](../docs/NINO_SIM_RELIABLE_TD3_PROTOCOL_2026-11-06.md). Chưa promote hoặc mở training/hardware mới.

# Kế tiếp: fresh TD3 common103D/1D với reliable joint candidate

06/11/2026 · **Draft, chưa triển khai learner mới hoặc release training.**
Candidate đã qua1fixturepaired1000messages và2B0qualificationstop6/8s.
Không có bằng chứng rootcause50ms đã được giải quyết; cảBE/RELIABLE đềuđủ
trongfixture, qualificationkhôngoptimizerload. Không cần đợi dữliệu thật
để thiết kế bounded learner test, nhưng không tự promote checkpoint.

## Giữ và bỏ

Giữ frozen controller103D/1D, history5, sourceplanpreview/window, common±0,005m/s,
reward cost vật lý và PI/physics/follower. Candidate chỉ joint observer
RELIABLE, cácchannel/QoS khácgiữ. Không tăngqueue hoặc đổi cácgate saufailure.

Giữ partial700ticks của batchcũ làm diagnostic, **không resume hoặc nối
vào replay mới**. Không nạp modelV3/Studio/inspection. Identity learner mới
phải pin candidate fingerprint +qualificationmanifest và ghi release/budget
riêng; parentflags lịch sử không sửa.

## Một pilot mới đề xuất

- Fresh learner seeds11/22/33,1.024transition/seed,tổng3.072. CPU32²,
  LR3e−4,gamma0,99,tau0,005,batch32,buffer8192,warmup64,train_freq1,
  gradient_steps1,policy_delay2,targetnoise0,2/clip0,5,exploration0,1scalar.
- Trainstop6/8 xen kẽ,14s/140ticks/episode,bắtđầu6;7full +44tick cắtphải/seed.
  Không thêm transition để hoàn tất episode8. Zero actorhead/targetsync,
  critic/optimizer mới; không gọi warmup/exploration làzero.
- Nếu3seed hoàn thành hợp lệ:10fresh evaluallaunches B0/classical mỗi6/8
  +3learner mỗi6/8. Thứtự khóa trướctrain, tất cảcheckpointcuốibudget được
  đánhgiá, không chọnseed/checkpoint sau kếtquả. Tổng4.472controlticks/34launches.
- Không thêmphysics smoke. Episode đầu nằmtrongbudget để kiểm integration;
  learnerupdates bắtđầu từ65cũng kiểm loadthực trongngânsách. Wall deadline
  riêng phải chốt từthroughput B0 +marginoptimizer, không bịa realtime.

## Việc phải xây offline trước collect

1. Trainer mới dùng candidatebackend; không sửa scientific module cũ để
   thayparentidentity. Replay giữrequest1D,obs103,nextobs103,reward/done/timeout,
   requested/mapped/accepted trace; export/import đầy đủmodel/targets/
   critics/optimizers/replay/config/runtime/ABI.
2. Thiết kế lifecycle **từng episode** cho primarylog và processobserver:
   sau khiGazebo/ROSexecutor cũđóng mới quaylog/startobserver mới; READY/ACK
   và epoch/namespace tách. Không mang lateststamp/count từlaunchtrước
   qua reset, không xửlý sample cũ làsupport củaepochmới.
3. `BoundaryBackend` hiệnđượcqualify cho1launch/instance; không giả đã
   đủ8reset trongmộtlearner. Phải test orchestration bằngfixture reset/
   close/cancel/failure, không gọi Gazebo smoke ngoài budget.
4. Giữ gateprimary/support/physical/task/stop/GTheader/replay nhưprotocol mới.
   IndependentBE vẫn chỉaudit, không váprimary. Nếu dùng nguyên candidate
   hiệnđãqualify thì timeoutBE cũngquarantine; phânbiệtprimaryhealthy với
   auxiliaryfailure trongreport, không sửa semantics sauoutcome.
5. Artifact partial đóngngaykhi acquisition/physics/learner/nonfinite/fault
   xảyra; không tựretries, không chạyseed/slot cònlại. Nhận đủobservations
   ởbiên khôngchứngminh mọi transient/rawsample đềuđủ.

## Gate và điểm dừng

- Bắt đầu với protocol/budget/fingerprint/order/metrics khóa trướcjob.
- Đủ model/replay/target/optimizer parity; expected960criticupdates/seed,
  finiteactorchange/gradients/losses. Budgetcắtphải không épterminal.
- Hếtfull episode phải cómarker0,95m +quietstop2s, path/estimatebounds và
  sensor40ms. NativeRMSE primary; GT-header20ms/+10ms riêng, giữspikes/failure.
- Minimumworthwhileeffect vẫnnull; so từngseed/stop với cảB0 vàclassical,
  không dùngreturn đểthay outcome. Không thắngclassical hoặc effectsampling-
  sensitive →unknown/no promotion; không mởbudgetdài/PPO/DR hoặchardware.
- Reliabilitycandidate là correction duy nhất đangxét. Nếu mới vẫnfail:
  giữ artifact, phânbiệt kênhlỗi, không thêm correctionqueue/chunk/gain/
  collector trongcùngpilot; quyết định dừng/chuyểnbaseline hoặc thiết kế
  acquisition khác riêng, không chuỗi mini train→logger→retry vôhạn.
