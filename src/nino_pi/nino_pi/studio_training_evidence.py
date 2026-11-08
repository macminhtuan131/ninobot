"""Read-only counter evidence; never releases training or hardware authority."""
import hashlib
import json
from pathlib import Path


def completed_training(plan):
    record=plan.get('studio_training_completed')
    if not record:return None
    root=Path(record['artifact'])
    def read(name,expected):
        path=root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Studio training evidence hash mismatch: '+name)
        return json.loads(path.read_text())
    manifest=read('manifest.json',record['manifest_sha256'])
    result=read('training_result.json',record['training_result_sha256'])
    if manifest.get('status')!='completed' or manifest['files'].get('training_result.json')!=record['training_result_sha256']:
        raise ValueError('Studio training evidence is not a completed sealed job')
    job=read('job.json',manifest['files']['job.json'])
    if job.get('status')!='completed' or job['request']['seed']!=record['seed']:
        raise ValueError('Studio training job/seed mismatch')
    cumulative=record.get('counter_scope')=='cumulative_single_learner'
    if cumulative:
        if result['starting_global_steps']+result['transitions']!=result['global_steps']:
            raise ValueError('Continuation/global counter mismatch')
        if result['transitions']!=record['job_transitions'] or result['starting_global_steps']!=record['starting_global_steps']:
            raise ValueError('Continuation local counter mismatch')
    mapping=dict(training_transitions='global_steps' if cumulative else 'transitions',critic_updates='optimizer_updates_total',actor_updates='actor_updates_total')
    for key,actual in mapping.items():
        if result[actual]!=record[key]:raise ValueError('Studio training counter mismatch: '+key)
    if result.get('engine')!='common103_v1':raise ValueError('Unsupported completed Studio engine')
    value=dict(seed=record['seed'],studio_completed=True,**{key:result[actual] for key,actual in mapping.items()})
    if cumulative:value.update(job_transitions=result['transitions'],starting_global_steps=result['starting_global_steps'],counter_scope=record['counter_scope'])
    return value


def scientific_assessment(plan):
    """Verify the latest bounded diagnostic and link it to the sealed learner.

    Small metadata only: no model/replay load, job, authority or release.
    """
    record=plan.get('latest_sim_assessment')
    if not record:return None
    root=Path(record['artifact']);manifest_path=root/'manifest.json'
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=record['manifest_sha256']:
        raise ValueError('Offline assessment manifest changed')
    manifest=json.loads(manifest_path.read_text())
    if manifest.get('status')!='completed':raise ValueError('Offline assessment is not complete')
    def read(name):
        p=root/name
        if hashlib.sha256(p.read_bytes()).hexdigest()!=manifest['files'][name]:raise ValueError('Offline assessment file changed: '+name)
        return json.loads(p.read_text())
    decision=read('decision.json');analysis=read('analysis.json');protocol=read('protocol.json')
    if decision['decision']!='KEEP_CLASSICAL_FOR_CURRENT_CLEAR_FLOOR_PLANNED_STOP_ENVELOPE':
        raise ValueError('Unsupported scientific decision')
    if decision.get('new_ablation_or_training_released') is not False or not decision.get('all_immutable_inputs_match'):
        raise ValueError('Assessment scope/release mismatch')
    for key in ('new_physics_steps','optimizer_updates','hardware_actions'):
        if decision[key]!=0:raise ValueError('Assessment must be read-only')
    completed=completed_training(plan)
    if not completed or analysis['models']['30000']['global_steps']!=completed['training_transitions']:
        raise ValueError('Assessment is not linked to the latest completed learner')
    if (analysis['models']['30000']['critic_updates'],analysis['models']['30000']['actor_updates'])!=(completed['critic_updates'],completed['actor_updates']):
        raise ValueError('Assessment learner update mismatch')
    if Path(protocol['checkpoints']['30000']).parent.parent!=Path(plan['studio_training_completed']['artifact']):
        raise ValueError('Assessment checkpoint belongs to another learner')
    if sum(analysis['training_counts'].values())!=completed['training_transitions'] or analysis['corpus_rows']!=1680:
        raise ValueError('Assessment corpus count mismatch')
    summary=(f"ĐÃ REVIEW · TD3 {completed['training_transitions']:,} global steps, "
        f"{completed['critic_updates']:,} critic/{completed['actor_updates']:,} actor updates · cùng seed {completed['seed']}.\n"
        'ƯU TIÊN CLASSICAL SCHEDULED · clear-box / lịch dừng biết trước 6–8 s / Ki0,10. '
        'Phân tích offline đã đóng; TD3 chưa promote. Xem outline cho công việc tiếp theo; chưa mở lượt thu mới.')
    return dict(completed=completed,decision=decision,analysis=analysis,report=record['report'],summary=summary,
        training_artifact=plan['studio_training_completed']['artifact'])


def continuation_summary(plan):
    """Live trace progress is separate from the hash-verified completed counters."""
    assessment=scientific_assessment(plan)
    if assessment:return 'CONTINUATION ĐÃ REVIEW · 30.000 bước; giữ classical cho envelope này; không tự train thêm.'
    record=plan.get('training_studio',{}).get('active_continuation')
    if not record:return None
    try:state=json.loads(Path(record['status_file']).read_text())
    except (OSError,ValueError):return 'Continuation đã được cấp budget; chưa đọc được snapshot. Không chạy thêm job.'
    if state.get('artifact')!=record['artifact']:
        raise ValueError('Continuation status belongs to another artifact')
    status=state.get('status')
    if status=='running':
        value=state.get('global_steps_from_trace')
        if type(value) is not int or not record['starting_global_steps']<=value<=record['target_global_steps']:
            raise ValueError('Invalid continuation progress counter')
        return f"CONTINUATION ĐANG CHẠY · trace global{value:,}/{record['target_global_steps']:,}; chưa là QC replay cuối. Không bấm Train thêm."
    if status=='completed':return 'CONTINUATION WORKER ĐÃ HOÀN TẤT · xem QC/evaluation trước quyết định tiếp; không tự promote hoặc train thêm.'
    if status in ('failed','cancelled'):return 'CONTINUATION ĐÃ ĐÓNG DO LỖI/DỪNG · giữ raw/checkpoint, xem error/QC; không tự retry.'
    return 'Continuation chưa xác định trạng thái; xem snapshot/log, không suy thành thành công.'
