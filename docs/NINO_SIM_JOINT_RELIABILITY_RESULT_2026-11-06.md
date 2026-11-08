# Kết quả candidate joint RELIABLE: fixture và B0 qualification

06/11/2026 · **hai stage đã đóng; candidate đạt functional qualification,
chưa train với candidate và chưa chứng minh sửa failure50ms.**

## Quyết định

Giữ một candidate riêng cho bước learner tiếp theo: primary joint reader
RELIABLE, depth100; các QoS khác/subscriptions khác giữ nguyên. Không thay
backend frozen hoặc resume partial TD3700ticks. Fixture cho compatibility;
B0 qualification cho task/stop/contract dưới candidate, không có optimizer
load hoặc causal comparison về hiệu quả QoS.

Tiếp theo xây/chốt [learner protocol mới](NINO_SIM_RELIABLE_TD3_NEXT_2026-11-06.md)
với lifecycle observer/epoch từng episode và fresh model/replay/optimizer.
Draft chưa release/chạy train. Reliability là correction duy nhất đang xét;
không thêm queue/chunk/gain correction nếu pilot mới thất bại.

## Đã triển khai

- `joint_reliability_candidate.py`: subclass của instrumented diagnostic
  backend. Chỉ thay reliability subscription joint trước owned launch và
  trước sample đầu; giữ depth/history/durability/lifespan/deadline/liveliness/
  lease/namespace conventions. Kiểm identity/QoS subscription khác không đổi.
- `joint_reliability_worker.py`: readers fixture process riêng, ghi cùng
  stream, pause/ACK/source/receipt/hash/counter và closure. Không motor output.
- `residual_joint_reliability.py`/YAML/script: hai stage độc lập, manifest/
  dependency hash, budget/timeout/consume, không retry. Fixture no-go khóa
  qualification trong cả GUI và runner, không chuẩn bị world sau no-go.
- GUI profile **Joint RELIABLE ·fixture rồi B0 qualification**, hai nút có
  gate, progress/result/error và bảng QC/metric. Giữ TRAIN TD3 V3/100D/2D
  riêng; candidate không tự đổi checkpoint schema hoặc phát command thật.

Relative change “chỉ QoS” tính từ instrumented diagnostic backend. So với
failed learner cũ còn có hash logging/sidecar và khác workload; không coi
qualification này là matched causal experiment của oldfailure.

## Stage1: một source stream ROS-only có fault

Domain139/local, source RELIABLE/depth100. Một handshake stamp9s được cảhai
ACK, sau đó **1.000JointState/500Hz**, header10s +index×2ms. Tổng1.001publish
attempts. Không gửi thêm để váduôi; publishreturn không là DDSdeliveryACK.

| Reader | Labeled nhận/nguồn | Thiếu / duplicate / payload lệch | Actual pause | Pause startlag | Nguồn phát trong pause | Endpoint age |
|---|---:|---|---:|---:|---:|---:|
| BEST_EFFORT | 1.000/1.000 | 0/0/0 | 100,346944ms | 0,677256ms | 50 | 0ms |
| RELIABLE | 1.000/1.000 | 0/0/0 | 100,320865ms | 0,708438ms | 50 | 0ms |

Có thêm1handshake/reader trong raw, không gọi rawcount1.001 là1.001labeled
samples. Maximum publishcall0,227163ms; maximum sourceinterval2,163689ms.
Các fixture gates được khóa trước outcome; không thấy backpressure vượt
100ms hoặc pacinginterval vượt40ms trong stream này.

Candidate_compatible=true. **Cảhai đều đủ** nên chưa thấy reliability benefit
trong fixture này; không ngoại suy loss-free hoặc chữa50ms của failure khác.
Không dùng hash CDR serialize lại làm payloadparity; dùng canonicalfieldhash.

## Stage2: candidate B0 clear stop6/8

Hai fresh launches đúng thứtự6s rồi8s;140native ticks/lượt,280 tổng. Request
scalar0, common/diff residual0; baseline follower/PI/physics/task/nominalreward
và103D/1D contract giữ. Primary RELIABLE, independent BEST_EFFORT chỉaudit.

| Điều kiện | Native nominal vRMSE(m/s) | GT20ms / +10ms(m/s) | PathRMSE(mm) | Task/stop | Primary/independent joint maxage |
|---|---:|---|---:|---|---|
| B0 stop6s | 0,004970135 | 0,006256031 /0,006260530 | 0,099126 | đạt/đạt | 1/1ms |
| B0 stop8s | 0,005461392 | 0,007283607 /0,007288841 | 0,075487 | đạt/đạt | 1/1ms |

Native support của toàn IMU/wheel/GT/drive max19ms và17ms theo lượt; gate40ms
giữ. Hai GT-header diagnostics đều hợp lệ, không interpolation hoặc đổi
primarygrid sauoutcome. Không so các số trên với historicalB0 để tuyên bố
QoS cải thiện tracking hoặc làm kiểm định thống kê.

-426feedbackchecks/lượt =420controlchecks(2half +1finalrecheck/tick)
  +6setup; tổng852, không là852independenttrials.
- Primary/independent nhận9.499/9.499 và8.517/8.517joint records gồmstartup;
 18.016sharedstamps, canonicalpayloadmismatch0, không stampchỉmộtđường trong
  hai file đãghi. Không có publishercounter nên không suy toànstream loss-free.
-280persisted diagnosticreplay rows khớp obs103/request1D/nextobs/reward/
  done/timeout. Đây không là TD3trainingreplay; không optimizer/actor được tạo.
-580worldrequests ACK/completion/clock đúng, retry0;29.000physicssteps trong
  cácmulti_step requests gồmsettling, không gồmfree-startupiterations.
-4parameterreadbacks;1.400causal estimatorupdates wheel/IMU, không truthinput
  vào controller. GT/contact chỉlabels/setup/audit nhưparent.

## Integrity và software QA

Fixture35files +qualification64files =**99artifact hashes**;130prelaunch
sourcefiles được kiểm trước cập nhật presentation/metadata. Scientific
runner/candidate/worker/config/script và frozenparents không đổi sau sealed
jobs. Gui/report metadata được cập nhật kếtquả thật, không sửa raw.

**45software/GUI tests đạt**(13contract/ROS-QoS tests +32GUI). ROS Node thật
trong unitfixture domain140 kiểm replace subscription khi executorđangchạy,
không message stream hoặc Gazebo. Lỗi chuẩn bị banđầu `deepcopy(QoSProfile)`
không hỗ trợ C++Duration được giữXML; đã sửa constructorpreserveallpolicies
trước release, không tiêu thụ livefixture hoặc physicsbudget.

Hai package `nino_pi`/`nino_rl` build và kiểm source/install cuối trong
`NINO_SIM_JOINT_RELIABILITY_VERIFICATION_2026-11-06.json`.

## Không thể kết luận

- Chưa đo optimizerload, multi-episode childreset hoặc behavior của learner
  dưới candidate. Hai B0launches không là kiểm repeatability/generalization.
- Không tách được oldfailure thành publisher/DDS/consumer từ những lần sạch
  mới. Oldrootcause vẫnunknown; không có upstreampublicationcounter.
- Không có minimumworthwhileeffect được chấpnhận, không learnedbenefit hoặc
  deployment/hardware release. Realdata cutoff02/11/2026 không đổi.
- Partial700ticks/636critic/318actorupdates của batchcũ vẫnđóng; không dùng
  unusedslots làm budget của experiment mới.

## Artifact và một việc tiếp theo

Root `/home/tuanmac/nino_research/sim_joint_reliability_v1`:

- `20261106T020552213960Z_sim-joint-reliability-fixture`
- `20261106T020606195914Z_sim-joint-reliability-gazebo`

Fingerprint candidate stage family:
`e2e0748afe1b560e1b00ee847029e5481d8654a84f7187d711750fe173bc10a8`.

Một việc tiếp theo: chuẩn bị trainer fresh103D/1D trên candidate, trước hết
kiểm orchestration reset/close/epoch bằng softwarefixture; sau đó mới chốt
release/budget trước collect. [Draft cụ thể](NINO_SIM_RELIABLE_TD3_NEXT_2026-11-06.md).
Không mở thêm Gazebo/training trong hai stage vừađóng, không thêm correction.
