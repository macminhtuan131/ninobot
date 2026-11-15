"""Run the user-selected source/current-report graphify pipeline locally.

Host-agent semantic usage is unavailable; zero counters are placeholders and are
explicitly disclosed rather than presented as zero-cost model extraction.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.build import build_from_json
from graphify.cache import save_semantic_cache
from graphify.cluster import cluster, score_all
from graphify.diagnostics import diagnose_extraction, format_diagnostic_report
from graphify.export import to_json
from graphify.report import generate

ROOT=Path('/home/tuanmac/ninorobot')
OUT=ROOT/'graphify-out'
SPEC=ROOT/'.codex/skills/graphify/references/extraction-spec.md'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def merge_and_build():
    chunks=read(OUT/'.graphify_chunks.json')
    ast=read(OUT/'.graphify_ast.json');known={n['id'] for n in ast['nodes']}
    results=[]
    # Validate ALL host results before writing chunks or changing the cache.
    for index,files in enumerate(chunks):
        data=read(Path(f'/tmp/nino_graphify_chunk_{index}_20261114.json'))
        assert isinstance(data,dict) and isinstance(data['nodes'],list) and isinstance(data['edges'],list)
        assert isinstance(data.get('hyperedges',[]),list)
        expected={f:sum(1 for _ in Path(f).open(encoding='utf-8')) for f in files}
        assert data['coverage']==expected,(index,data['coverage'],expected)
        assert not known.intersection(n['id'] for n in data['nodes']), 'Do not overwrite an AST anchor'
        for node in data['nodes']:
            assert node['source_file'] in files
            assert node['file_type'] in {'code','document','paper','image','rationale','concept'}
        for edge in data['edges']:
            assert edge['source_file'] in files
            assert edge['confidence'] in {'EXTRACTED','INFERRED','AMBIGUOUS'}
            assert 'confidence_score' in edge
            if edge['confidence']=='EXTRACTED':assert edge['confidence_score']==1.0
        data['usage_status']='host_token_usage_not_exposed; numeric counters are placeholders'
        results.append(data)
    nodes=ast['nodes']+[n for d in results for n in d['nodes']]
    endpoints={n['id'] for n in nodes}
    for data in results:
        for edge in data['edges']:
            assert edge['source'] in endpoints and edge['target'] in endpoints,edge
        for edge in data.get('hyperedges',[]):
            assert all(n in endpoints for n in edge['nodes']),edge
    for index,data in enumerate(results):save(OUT/f'.graphify_chunk_{index:02d}.json',data)
    new=dict(nodes=[n for d in results for n in d['nodes']],
             edges=[e for d in results for e in d['edges']],
             hyperedges=[e for d in results for e in d.get('hyperedges',[])],
             input_tokens=0,output_tokens=0,usage_status='host_token_usage_not_exposed')
    save(OUT/'.graphify_semantic_new.json',new)
    uncached=(OUT/'.graphify_uncached.txt').read_text().splitlines()
    cached=save_semantic_cache(new['nodes'],new['edges'],new['hyperedges'],root=str(ROOT),
        allowed_source_files=uncached,prompt_file=str(SPEC),partial_source_files=[])
    print(f'Semantic cache: {cached} files',flush=True)
    semantic=new
    old=OUT/'.graphify_cached.json'
    if old.exists():
        previous=read(old)
        semantic=dict(new,nodes=previous['nodes']+new['nodes'],edges=previous['edges']+new['edges'],
                      hyperedges=previous.get('hyperedges',[])+new['hyperedges'])
    seen=set();deduped=[]
    for node in semantic['nodes']:
        if node['id'] not in seen:seen.add(node['id']);deduped.append(node)
    semantic['nodes']=deduped
    save(OUT/'.graphify_semantic.json',semantic)
    extraction=dict(nodes=ast['nodes']+semantic['nodes'],edges=ast['edges']+semantic['edges'],
        hyperedges=semantic['hyperedges'],input_tokens=0,output_tokens=0,
        usage_status='AST no model tokens; semantic host usage unavailable')
    save(OUT/'.graphify_extract.json',extraction)
    diagnostic=diagnose_extraction(extraction,directed=False,root=str(ROOT))
    save(OUT/'diagnostics.json',diagnostic)
    print(format_diagnostic_report(diagnostic),flush=True)
    graph=build_from_json(extraction,root=str(ROOT),directed=False)
    assert graph.number_of_nodes()>0
    communities=cluster(graph);cohesion=score_all(graph,communities)
    gods=god_nodes(graph,top_n=5)
    surprises=surprising_connections(graph,communities,top_n=3)
    labels={key:'Community '+str(key) for key in communities}
    questions=suggest_questions(graph,communities,labels,top_n=3)
    assert to_json(graph,communities,str(OUT/'graph.json'),force=False)
    analysis=dict(communities={str(k):v for k,v in communities.items()},
        cohesion={str(k):v for k,v in cohesion.items()},gods=gods,surprises=surprises,questions=questions)
    save(OUT/'.graphify_analysis.json',analysis)
    detection=read(OUT/'.graphify_detect.json')
    report=generate(graph,communities,cohesion,labels,gods,surprises,detection,
                    dict(input=0,output=0),str(ROOT),suggested_questions=questions)
    (OUT/'GRAPH_REPORT.md').write_text(report,encoding='utf-8')
    ranked=[]
    for cid,members in communities.items():
        ranked.append(dict(id=cid,size=len(members),cohesion=cohesion[cid],
            sources=Counter(graph.nodes[n].get('source_file','') for n in members).most_common(7),
            labels=[graph.nodes[n].get('label',n) for n in sorted(members,key=lambda n:graph.degree(n),reverse=True)[:12]]))
    save(OUT/'community_overview.json',ranked)
    save(OUT/'build_summary.json',dict(nodes=graph.number_of_nodes(),edges=graph.number_of_edges(),
        ast_nodes=len(ast['nodes']),ast_edges=len(ast['edges']),semantic_nodes=len(semantic['nodes']),
        semantic_edges=len(semantic['edges']),communities=len(communities),
        semantic_files_completely_read=16,host_token_usage_exposed=False,
        model_api_called=False,built_utc=datetime.now(timezone.utc).isoformat()))
    print('Graph:',graph.number_of_nodes(),'nodes,',graph.number_of_edges(),'edges,',len(communities),'communities',flush=True)


if __name__=='__main__':merge_and_build()
