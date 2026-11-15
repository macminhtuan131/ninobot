"""Name graph communities and finalize the explicitly selected build scope."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from graphify.analyze import suggest_questions
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.detect import detect, save_manifest
from graphify.cli import _stamped_manifest_files
from graphify.export import to_json
from graphify.paths import out_path
from graphify.report import generate
from graphify.watch import _read_build_excludes, _read_build_gitignore

ROOT=Path('/home/tuanmac/ninorobot');OUT=ROOT/'graphify-out'


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def name_for(row):
    # Source-derived labels for small peripheral communities. Curated architecture
    # labels below override these; no additional model/API calls are used.
    sources=[s for s,n in row['sources'] if s]
    if not sources:return 'Thư viện bên ngoài'
    preferred=[s for s in sources if '/test/' not in s and '/tests/' not in s]
    source=Path((preferred or sources)[0]);words=source.stem.replace('.launch',' launch').replace('_',' ').split()
    if words and words[0]=='test':words=words[1:];prefix='Kiểm thử'
    elif source.suffix in ('.yaml','.yml','.json'):prefix='Cấu hình'
    elif 'launch' in source.parts:prefix='ROS launch'
    elif 'scripts' in source.parts:prefix='Công cụ'
    elif 'nino_pi' in source.parts:prefix='Pi'
    else:prefix='Module'
    return ' '.join([prefix]+words[:max(1,5-len(prefix.split()))])


def main():
    extraction=read(OUT/'.graphify_extract.json');old_detection=read(OUT/'.graphify_detect.json')
    detection=detect(ROOT,extra_excludes=_read_build_excludes(out_path()),gitignore=_read_build_gitignore(out_path()))
    flatten=lambda d:{f for g in d['files'].values() for f in g}
    assert flatten(detection)==flatten(old_detection)
    detection['scope']=old_detection['scope']
    detection['warning']='Large source corpus: 802 selected files (786 code/config and 16 current documents). '
    detection['warning']+='The user explicitly chose this scope after reviewing the original 4,803-file corpus; historical snapshots are excluded.'
    save(OUT/'.graphify_detect.json',detection)
    analysis=read(OUT/'.graphify_analysis.json');overview=read(OUT/'community_overview.json')
    graph=build_from_json(extraction,root=str(ROOT),directed=False)
    communities={int(k):v for k,v in analysis['communities'].items()}
    cohesion={int(k):v for k,v in analysis['cohesion'].items()}
    labels={row['id']:name_for(row) for row in overview}
    labels.update({
        0:'Cấu hình và tuning',1:'Pipeline residual dùng chung',2:'Giao tiếp robot ROS',
        3:'CLI và chạy phiên',4:'Tài nguyên thí nghiệm',5:'Huấn luyện và checkpoint',
        6:'Biên thời gian encoder',7:'Quản lý tiến trình',8:'Audit governor và logger',
        9:'TD3 guided và Studio',10:'Launch và mô phỏng',11:'Bảng nghiên cứu Studio',
        12:'Quỹ đạo và PPO',13:'Đối chứng cùng thông tin',14:'ABI và residual pipeline',
        15:'TD3 và đánh giá',16:'GUI huấn luyện TD3',17:'ROS observer và acquisition',
        18:'Sàng lọc gain PI',19:'PI vận tốc bánh',20:'Tracking và reward',
        21:'Coverage và exploration TD3',22:'Audit động lực học',23:'Evaluation và common103 v2',
        24:'Ứng viên gain giữ',25:'Pilot và thu phiên',26:'Recorder và Optuna SQLite',
        27:'Kiểm thử H2 governor',28:'Gym và lịch sử',29:'Huấn luyện common v1',
        30:'Authority trước dừng',31:'Profile tham số TD3',32:'Drive readiness và coverage',
        33:'GUI chế độ robot',34:'Fixture gain và PI',38:'Nhận dạng đáp ứng bánh',
        47:'Backend vận tốc Gazebo',70:'Môi trường gờ Goal100',82:'Thu dữ liệu thật',
        99:'Đánh giá checkpoint Goal100',115:'QC dữ liệu thật',118:'Dashboard tập và checkpoint',
        128:'Follower và dừng đích',147:'Studio thu dữ liệu',163:'Scoring vật lý Goal100',
        167:'Governor trạng thái phản ứng',175:'Ghép observation và clock',
        253:'Kiến trúc và tiến độ',257:'Projection reference residual',
        287:'Reference residual và giới hạn',328:'Lịch sử observation',
    })
    assert set(labels)==set(communities)
    questions=suggest_questions(graph,communities,labels,top_n=3)
    save(OUT/'.graphify_labels.json',{str(k):v for k,v in labels.items()})
    analysis['questions']=questions;save(OUT/'.graphify_analysis.json',analysis)
    assert to_json(graph,communities,str(OUT/'graph.json'),community_labels=labels)
    report=generate(graph,communities,cohesion,labels,analysis['gods'],analysis['surprises'],
        detection,dict(input=0,output=0),str(ROOT),suggested_questions=questions)
    report=report.replace('- Token cost: 0 input · 0 output',
        '- Token cost: AST uses no model tokens. Actual host-agent semantic input/output usage is not exposed by the tools; totals are unknown, not zero. No separate model API was called.')
    notes='''
## Phạm vi và giới hạn kiểm chứng

- Phạm vi được người dùng chọn: toàn bộ code/config được detect trong `src/`, README và 15 tài liệu hiện trạng. Không gồm code snapshot trong `docs/`, artifact/episode/binary, toolchain hoặc môi trường Python. Source hiện diện không chứng minh module đang chạy trên robot.
- Ba nhóm đọc đầy đủ 16 tài liệu, có line-count coverage. AST nhận 786 file; 73 file không có node source, chủ yếu JSON/YAML. Danh sách ở `extraction_coverage.json`; không suy ra các file này không dùng đến.
- Graphify cảnh báo parser tại `src/nino_rl/nino_rl/ros_env.py` (47 symbol vẫn trích xuất). Python `ast.parse` đọc file này thành công; đây là giới hạn extractor, chưa là bằng chứng file Python sai cú pháp.
- **GRAPH HEALTH WARNING:** raw extraction có 5.201 cạnh thiếu node endpoint nội bộ, 40 self-loop và 1.735 cạnh có cùng cặp endpoint bị gộp khi dùng Graph không hướng. Builder bổ sung 136 node được đánh dấu `external` (các thư viện/import ngoài repository); graph xuất cuối không có cạnh trỏ tới ID không tồn tại. Cảnh báo raw và mẫu cạnh nằm trong `diagnostics.json`; không coi graph là call trace runtime hoặc chứng minh mọi quan hệ đã được resolve.
- Giữ đầy đủ raw extraction trong `extraction.json.gz` để tra các quan hệ/địa điểm bị gộp. File `graph.json` là graph chuẩn để query, còn HTML mặc định hiển thị theo cụm vì vượt 5.000 node.
- Độ tin cậy EXTRACTED/INFERRED/AMBIGUOUS là nhãn về nguồn quan hệ, không phải kết quả kiểm chứng controller, firmware hay chất lượng dataset. Kết quả nghiên cứu vẫn theo từng báo cáo/ngày/contract.
- Số token bằng 0 trong sidecar legacy là placeholder của API host; `cost.json` ghi rõ `usage_status=host_usage_unavailable`. Không có số token thực để tính tổng chi phí.
- `graphify-out/` được ghi trong working tree. Nếu chưa được ignore, nó xuất hiện trong `git status`; có thể commit các output cần chia sẻ hoặc thêm thư mục này vào `.gitignore` theo cách làm việc của nhóm. Tác vụ này không tự commit hay đổi `.gitignore`.
'''
    (OUT/'GRAPH_REPORT.md').write_text(report+'\n'+notes,encoding='utf-8')
    manifest_files=_stamped_manifest_files(detection['files'],extraction,ROOT,partial_source_files=set())
    semantic_types=('document','paper','image')
    dispatched={f for t in semantic_types for f in detection['files'].get(t,[])}
    stamped={f for values in manifest_files.values() for f in values}
    save_manifest(manifest_files,root=ROOT,scan_corpus=flatten(detection),clear_semantic=dispatched-stamped or None)
    save(OUT/'cost.json',dict(runs=[dict(date=datetime.now(timezone.utc).isoformat(),
        files=802,input_tokens=0,output_tokens=0,usage_status='host_usage_unavailable',
        structural_model_tokens=0,semantic_input_tokens_actual=None,semantic_output_tokens_actual=None,
        separate_model_api_calls=0)],total_input_tokens=0,total_output_tokens=0,
        usage_status='numeric total fields are unknown-usage placeholders, not actual consumption'))
    raw=(OUT/'.graphify_extract.json').read_bytes()
    archive=OUT/'extraction.json.gz'
    with archive.open('wb') as f:
        with gzip.GzipFile(filename='',fileobj=f,mode='wb',compresslevel=6,mtime=0) as z:z.write(raw)
    assert gzip.decompress(archive.read_bytes())==raw
    save(OUT/'extraction_archive.json',dict(path=archive.name,
        original_sha256=hashlib.sha256(raw).hexdigest(),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        original_bytes=len(raw),archive_bytes=archive.stat().st_size))
    print('Named',len(labels),'communities; 16 full document coverage records; manifest saved.',flush=True)
    print('GRAPH HEALTH WARNING retained in report; host semantic token usage disclosed as unavailable.',flush=True)


if __name__=='__main__':main()
