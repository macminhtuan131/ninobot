"""Local fixed software jobs and verified progress; no SSH or robot commands."""
import json
import hashlib
import os
from pathlib import Path
import signal
from PyQt5 import QtCore as C

JOBS={
    'validate':('1 · Kiểm History / giới hạn / environment',()),
    'train-td3':('2 · TD3 fixture giảm bậc · 128 bước',('validate',)),
    'audit-td3':('2b · Kiểm replay / checkpoint / actor TD3',('train-td3',)),
    'train-ppo':('3 · PPO · đối chứng 128 bước',('validate',)),
    'compare':('4 · So B0 / B1 / Governor / TD3 / PPO',('train-td3','train-ppo')),
    'ros-fixture':('5 · Kiểm ROS → actor → trace',('train-td3',)),
    'gazebo-fixture':('6 · Kiểm backend Gazebo sàn phẳng',('validate',)),
    'factory-td3':('FACTORY · TD3 + Nino + wheel PI · 128 bước',()),
    'sim-baselines':('SIM 1 · B0 sàn sạch / gờ 6 mm / mixed 22 mm',()),
    'sim-train':('SIM 2 · TD3 h5 · pilot 256 bước',('sim-baselines',)),
    'sim-evaluate':('SIM 3 · B0 / B1 yaw / TD3 h5',('sim-train',)),
    'sim-v2-baselines':('SIM V2 · B0 tracking + dừng · 2 lượt/môi trường',()),
    'sim-v2-train':('SIM V2 · TD3 h5 · tối đa 512 transition',('sim-v2-baselines',)),
    'sim-v2-evaluate':('SIM V2 · B0 / speed control / TD3 · 2 lượt/arm',('sim-v2-train',)),
    'sim-bias-clear':('SIM · Checkpoint V2 đóng băng trên sàn sạch · 4 lượt',()),
    'sim-guidance-contract':('SIM · Reference follower → residual · kiểm offline',('sim-bias-clear',)),
    'sim-v3-baselines':('SIM V3 · Estimator + follower trong Gazebo · residual zero',()),
    'sim-guided-contact':('SIM · Guided baseline clear/gờ 6 mm · tối đa 4 lượt',()),
    'sim-v3-contract':('TD3 V3 · 1 Kiểm reward / zero-init / identity offline',()),
    'sim-v3-train':('TD3 V3 · 2 Train h5 · tối đa 512 transition',('sim-v3-contract',)),
    'sim-v3-evaluate':('TD3 V3 · 3 Guided B0 / TD3 · 8 lượt',('sim-v3-train',)),
    'sim-axis-ablation':('SIM · Frozen B0 / TD3 full / common-only · 6 lượt',()),
    'sim-classical-common':('SIM · Bù common cổ điển / B0 / frozen TD3 common · 6 lượt',()),
    'sim-stop-transfer':('SIM · Chuyển lịch dừng6s / bù rút5,5s · 6 lượt',()),
    'sim-equal-contract':('SIM · Contract TD3/cổ điển cùng preview · chỉ offline',()),
    'sim-joint-reliability-fixture':('SIM · 1 Fixture RELIABLE/BEST_EFFORT · 1000messages +pause',()),
    'sim-joint-reliability-gazebo':('SIM · 2 Candidate RELIABLE · B0 stop6/8 · 2launches',('sim-joint-reliability-fixture',)),
    'sim-joint-boundary':('SIM · Joint boundary · 2zero launches / 200ticks tối đa',()),
    'sim-reliable-eval-only':('SIM · Evaluation-only · B0 / cổ điển / 3 TD3 · 10 lượt',()),
    'sim-ready-eval-only':('SIM · A seed11/B0/cổ điển cùng reset ACK · 6eval/840ticks · không train',()),
    'sim-drive-readiness':('SIM · Reset drive ACK + quiet · 2zero launches /20ticks · không actor',()),
    'sim-coverage-v2-preflight':('SIM · Coverage V2: đường train đầy đủ / reset / replay offline',()),
    'sim-coverage-v2-study':('SIM · Coverage V2: budget riêng 2 arm × 3 seed + 16 eval',('sim-coverage-v2-preflight',)),
    'sim-coverage-preflight':('SIM · Coverage: kiểm sampler/replay/runner offline',()),
    'sim-coverage-study':('SIM · Coverage: 2 arm × 3 seed rồi 16 eval',('sim-coverage-preflight',)),
    'sim-reliable-td3':('SIM · TD3 RELIABLE · 3 seed × 1024 + 10 eval',()),
    'sim-common-td3':('SIM · Fresh TD3 common103D/1D · 3seed ×1024 +10eval',()),
    'sim-equal-gazebo':('SIM · Qualification103D/1D trong Gazebo · 4 lượt',()),
    'sysid':('7 · Phân tích SysID đã đăng ký',()),
    'sim-gain-baselines':('SIM · Gain baseline · 9lượt/1260ticks · không actor/train',()),
}


def repository():
    explicit=os.environ.get('NINO_REPO')
    candidates=[Path(explicit).expanduser()] if explicit else Path(__file__).resolve().parents
    for root in candidates:
        if (root/'src/nino_rl/scripts/residual_workflow.sh').is_file():return root
    raise ValueError('Cần source workspace Nino; đặt NINO_REPO nếu dùng bản cài.')


def workflow_state(root):
    from nino_rl.residual_workflow import latest
    result={}
    for action in JOBS:
        try:
            # GUI uses system Python; workers use the research venv. Display
            # verified historical results; each worker rechecks its own runtime.
            path=latest(root,action,check_runtime=False)
            if action=='sim-gain-baselines':
                from nino_rl.gain_baseline_qualification import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-ready-eval-only':
                from nino_rl.residual_ready_eval_only import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-drive-readiness':
                from nino_rl.residual_drive_readiness import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action in ('sim-coverage-v2-preflight','sim-coverage-v2-study'):
                from nino_rl.residual_coverage_study_v2 import validated_latest
                path=validated_latest(root,action,check_runtime=False)
            if action in ('sim-coverage-preflight','sim-coverage-study'):
                from nino_rl.residual_coverage_study import validated_latest
                path=validated_latest(root,action,check_runtime=False)
            if action in ('sim-joint-reliability-fixture','sim-joint-reliability-gazebo'):
                from nino_rl.residual_joint_reliability import validated_latest
                path=validated_latest(root,action,check_runtime=False)
            if action=='sim-joint-boundary':
                from nino_rl.residual_joint_boundary import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-reliable-eval-only':
                from nino_rl.residual_reliable_eval_only import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-reliable-td3':
                from nino_rl.residual_reliable_td3 import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-common-td3':
                from nino_rl.residual_common_td3 import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-equal-gazebo':
                from nino_rl.residual_equal_gazebo import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-equal-contract':
                from nino_rl.residual_equal_information import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-stop-transfer':
                from nino_rl.residual_stop_transfer import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-axis-ablation':
                from nino_rl.residual_axis_ablation import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-classical-common':
                from nino_rl.residual_classical_common import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action in ('sim-v3-contract','sim-v3-train','sim-v3-evaluate'):
                from nino_rl.residual_guided_td3 import validated_latest
                path=validated_latest(root,action,check_runtime=False)
            if action=='sim-bias-clear':
                from nino_rl.residual_clear_bias import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-guidance-contract':
                from nino_rl.residual_guidance_workflow import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-v3-baselines':
                from nino_rl.residual_guided_baseline import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action=='sim-guided-contact':
                from nino_rl.residual_guided_contact import validated_latest
                path=validated_latest(root,check_runtime=False)
            if action.startswith('sim-v2-'):
                from nino_rl.residual_sim_task import validated_latest
                path=validated_latest(root,action,check_runtime=False)
            if action in ('sim-baselines','sim-train','sim-evaluate'):
                from nino_rl.residual_sim_pilot import fingerprint
                manifest=json.loads((path/'manifest.json').read_text())
                if manifest.get('pilot_fingerprint')!=fingerprint():raise ValueError('Sim pilot source/protocol changed; retained artifact is historical')
                if action=='sim-train':
                    baseline=latest(root,'sim-baselines',check_runtime=False)
                    dependency=json.loads((path/'dependencies.json').read_text())
                    if dependency.get('baseline')!=str(baseline) or dependency.get('manifest_sha256')!=hashlib.sha256((baseline/'manifest.json').read_bytes()).hexdigest():
                        raise ValueError('B0 artifact changed after training; review the retained dependency chain')
                if action=='sim-evaluate':
                    trained=latest(root,'sim-train',check_runtime=False)
                    baseline=latest(root,'sim-baselines',check_runtime=False)
                    dependency=json.loads((trained/'dependencies.json').read_text())
                    if dependency.get('baseline')!=str(baseline) or dependency.get('manifest_sha256')!=hashlib.sha256((baseline/'manifest.json').read_bytes()).hexdigest():
                        raise ValueError('Evaluation input training belongs to an older B0 artifact')
                    evaluation=json.loads((path/'evaluation_result.json').read_text())
                    if evaluation.get('checkpoint')!=str(trained):raise ValueError('Checkpoint changed; retained evaluation is historical')
            if action=='factory-td3':
                from nino_rl.residual_factory_workflow import factory_fingerprint
                manifest=json.loads((path/'manifest.json').read_text())
                if manifest.get('factory_fingerprint')!=factory_fingerprint():
                    raise ValueError('Factory map/robot/backend changed; retained smoke is historical')
            if action=='audit-td3':
                from nino_rl import residual_td3_audit
                manifest=json.loads((path/'manifest.json').read_text())
                if manifest.get('auditor_sha256')!=hashlib.sha256(Path(residual_td3_audit.__file__).read_bytes()).hexdigest():
                    raise ValueError('TD3 audit implementation changed; audit again')
                current=latest(root,'train-td3',check_runtime=False)
                if manifest.get('input_artifact')!=str(current) or manifest.get('input_manifest_sha256')!=hashlib.sha256((current/'manifest.json').read_bytes()).hexdigest():
                    raise ValueError('TD3 checkpoint changed; audit the current one')
            label='PILOT MÔ TẢ · CHƯA PROMOTE' if action.startswith('sim-') else 'SMOKE ĐẠT · TASK CHƯA XÁC NHẬN' if action=='factory-td3' else 'ĐẠT PHẦN MỀM' if action!='sysid' else 'CANDIDATE · CẦN REVIEW'
            if action=='sim-gain-baselines':label='GAIN BASELINE ĐÃ ĐÓNG · XEM NATIVE/HEADER/TASK · CHƯA MỞ LEARNER'
            if action=='sim-ready-eval-only':label='EVAL-ONLY A ĐÃ ĐÓNG · XEM NATIVE/HEADER/TASK · CHƯA PROMOTE'
            if action=='sim-drive-readiness':label='RESET ACK + ZERO QUALIFICATION ĐẠT · CHƯA LEARNING/MOTION BENEFIT'
            if action=='sim-guidance-contract':label='ĐẠT OFFLINE · CHƯA NỐI GAZEBO / ROBOT'
            if action=='sim-v3-baselines':label='BASELINE GAZEBO · RESIDUAL ZERO · CHƯA LEARNING'
            if action=='sim-v3-contract':label='CONTRACT OFFLINE ĐẠT · ZERO-INIT / IDENTITY'
            if action=='sim-v3-train':label='ĐÃ TRAIN V3 · MỘT SEED · CHƯA PROMOTE'
            if action=='sim-v3-evaluate':label='ĐÃ ĐÁNH GIÁ V3 · XEM CHẤT LƯỢNG TỪNG LƯỢT'
            if action=='sim-axis-ablation':label='ABLATION ĐÃ ĐÓNG · FROZEN ACTOR · OPTIMIZER 0'
            if action=='sim-joint-reliability-fixture':
                f=json.loads((path/'fixture_result.json').read_text())
                label='FIXTURE COMPATIBLE · CHƯA CHỨNG MINH TÁC DỤNG QOS' if f['candidate_compatible'] else 'FIXTURE NO-GO/UNKNOWN · KHÔNG MỞ GAZEBO'
            if action=='sim-joint-reliability-gazebo':
                q=json.loads((path/'qualification_result.json').read_text())
                label='CANDIDATE B0 ĐẠT QUALIFICATION · CHƯA TRAIN' if q['qualification_pass'] else 'QUALIFICATION ĐÃ ĐÓNG · CHƯA ĐẠT/UNKNOWN'
            if action=='sim-joint-boundary':label='DIAGNOSTIC ĐÃ ĐÓNG · XEM ENDPOINT HAI OBSERVER · CHƯA MỞ TRAIN'
            if action=='sim-reliable-eval-only':label='EVAL-ONLY ĐÃ ĐÓNG · XEM NATIVE / HEADER / TASK · CHƯA PROMOTE'
            if action in ('sim-coverage-preflight','sim-coverage-v2-preflight'):label='PREFLIGHT OFFLINE ĐẠT · CHƯA RELEASE GAZEBO'
            if action in ('sim-coverage-study','sim-coverage-v2-study'):label='COVERAGE STUDY ĐÃ ĐÓNG · XEM BASELINE / GRIDS / COVERAGE'
            if action=='sim-reliable-td3':label='TD3 RELIABLE ĐÃ ĐÓNG · XEM BASELINE / GRIDS · CHƯA PROMOTE'
            if action=='sim-common-td3':label='TD3 3SEED ĐÃ ĐÓNG · XEM NATIVE/HEADER · CHƯA PROMOTE'
            if action=='sim-equal-gazebo':
                q=json.loads((path/'qualification_result.json').read_text())
                label='103D/1D GAZEBO ĐẠT TÍCH HỢP · CHƯA TRAIN' if q['qualification_pass'] else 'ĐỢT ĐÃ ĐÓNG · INTEGRATION UNKNOWN/FAILED'
            if action=='sim-equal-contract':label='CONTRACT 103D/1D ĐẠT OFFLINE · KHÔNG TRAIN/GAZEBO'
            if action=='sim-stop-transfer':label='CHUYỂN LỊCH DỪNG ĐÃ ĐÓNG · XEM NATIVE + HEADER · OPTIMIZER 0'
            if action=='sim-classical-common':label='ĐỐI CHỨNG COMMON CỔ ĐIỂN ĐÃ ĐÓNG · OPTIMIZER 0'
            if action=='sim-guided-contact':
                evaluation=json.loads((path/'evaluation_result.json').read_text())
                label='BASELINE GỜ · ĐẠT GATE ĐỀ XUẤT' if evaluation['baseline_functional_candidate'] else 'ĐỢT ĐÃ ĐÓNG · BASELINE CHƯA ĐẠT GATE'
            result[action]=dict(state='verified',path=str(path),label=label)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            if action=='sim-gain-baselines':
                from nino_rl.gain_baseline_qualification import retained_failure
                failed=retained_failure(root)
                if failed is not None:
                    result[action]=failed;continue
            if action=='sim-ready-eval-only':
                from nino_rl.residual_ready_eval_only import retained_failure
                failed=retained_failure(root)
                if failed is not None:
                    result[action]=failed;continue
            if action=='sim-drive-readiness':
                from nino_rl.residual_drive_readiness import retained_failure
                failed=retained_failure(root)
                if failed is not None:
                    result[action]=failed;continue
            if action in ('sim-coverage-preflight','sim-coverage-study','sim-coverage-v2-preflight','sim-coverage-v2-study'):
                failed=retained_coverage_failure(root,action)
                if failed is not None:
                    result[action]=failed;continue
            if action=='sim-reliable-eval-only':
                failed=retained_eval_failure(root)
                if failed is not None:
                    result[action]=failed;continue
            if action=='sim-reliable-td3':
                failed=retained_reliable_failure(root)
                if failed is not None:
                    result[action]=failed;continue
            if action=='sim-common-td3':
                failed=retained_common_failure(root)
                if failed is not None:
                    result[action]=failed;continue
            result[action]=dict(state='pending',path=None,label='CHƯA ĐẠT / ARTIFACT CŨ',error=str(exc))
    return result


def gain_baseline_release_ready(root):
    try:
        from nino_rl.gain_baseline_qualification import release_ready
        release_ready(root)
        return True
    except (OSError,ValueError,KeyError,TypeError):return False


def ready_eval_release_ready(root):
    try:
        from nino_rl.residual_ready_eval_only import release_ready
        release_ready(root)
        return True
    except (OSError,ValueError,KeyError,TypeError):return False


def drive_readiness_release_ready(root):
    try:
        from nino_rl.residual_drive_readiness import release_ready
        release_ready(root)
        return True
    except (OSError,ValueError,KeyError,TypeError):return False


def coverage_release_ready(root,action="sim-coverage-study"):
    try:
        if action=="sim-coverage-v2-study":
            from nino_rl.residual_coverage_study_v2 import release_ready
        else:
            from nino_rl.residual_coverage_study import release_ready
        release_ready(root,False)
        return True
    except (OSError,ValueError,KeyError,TypeError):return False


def retained_coverage_failure(root,action):
    if action.startswith("sim-coverage-v2-"):
        from nino_rl import residual_coverage_study_v2 as job
    else:
        from nino_rl import residual_coverage_study as job
    root=Path(root).resolve()
    try:
        row=next(r for r in reversed(job.read(root/'state.json')['runs']) if r['action']==action)
        if row['status'] not in ('failed','cancelled'):return None
        out=(root/row['path']).resolve()
        if out.parent!=root:raise ValueError('Coverage artifact path escape')
        manifest=job.read(out/'manifest.json')
        if manifest['status']!=row['status'] or manifest['coverage_fingerprint']!=job.fingerprint():return None
        for name,value in manifest['files'].items():
            path=(out/name).resolve()
            if not path.is_relative_to(out) or job.sha(path)!=value:raise ValueError('Coverage artifact changed')
        return dict(state='retained_failure',path=str(out),label='COVERAGE ĐÃ ĐÓNG DO LỖI · GIỮ ARTIFACT',error=row['error'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration):return None


def retained_eval_failure(root):
    from nino_rl import residual_reliable_eval_only as job
    root=Path(root)
    try:
        state=json.loads((root/'state.json').read_text())
        row=next(r for r in reversed(state['runs']) if r['action']==job.ACTION)
        if row['status'] not in ('failed','cancelled'):return None
        out=(root/row['path']).resolve()
        if out.parent!=root.resolve():raise ValueError('Artifact path escape')
        manifest=json.loads((out/'manifest.json').read_text())
        if manifest['status']!=row['status'] or manifest['reliable_eval_fingerprint']!=job.fingerprint():return None
        for name,value in manifest['files'].items():
            path=(out/name).resolve()
            if not path.is_relative_to(out) or job.sha(path)!=value:raise ValueError('Eval artifact changed')
        if json.loads((out/'dependencies.json').read_text())!=job.dependency_record(job.parent(False),job.protocol()):return None
        return dict(state='retained_failure',path=str(out),label='EVAL-ONLY ĐÃ ĐÓNG DO LỖI · GIỮ PARTIAL / KHÔNG RETRY',error=row['error'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration):return None


def retained_reliable_failure(root):
    """Verified sealed partial artifact; no completed-training claim."""
    from nino_rl.residual_reliable_td3 import fingerprint, ACTION
    root=Path(root)
    try:
        state=json.loads((root/'state.json').read_text())
        row=next(r for r in reversed(state['runs']) if r['action']==ACTION)
        if row['status'] not in ('failed','cancelled'):return None
        out=(root/row['path']).resolve()
        if out.parent!=root.resolve():raise ValueError('Artifact path escape')
        manifest=json.loads((out/'manifest.json').read_text())
        if manifest['status']!=row['status'] or manifest['reliable_td3_fingerprint']!=fingerprint():return None
        for name,expected in manifest['files'].items():
            path=(out/name).resolve()
            if not path.is_relative_to(out) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Retained artifact hash mismatch')
        return dict(state='retained_failure',path=str(out),label='TD3 RELIABLE ĐÃ ĐÓNG DO LỖI · PARTIAL · KHÔNG RETRY',error=row['error'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration):return None


def retained_common_failure(root):
    """Display quarantined data without treating a failed job as verified training."""
    from nino_rl.residual_common_td3 import fingerprint
    root=Path(root)
    try:
        state=json.loads((root/'state.json').read_text())
        row=next(r for r in reversed(state['runs']) if r['action']=='sim-common-td3')
        if row['status'] not in ('failed','cancelled'):return None
        out=(root/row['path']).resolve()
        if out.parent!=root.resolve():raise ValueError('Artifact outside selected root')
        manifest=json.loads((out/'manifest.json').read_text())
        if manifest['status']!=row['status'] or manifest['common_td3_fingerprint']!=fingerprint():return None
        for name,value in manifest['files'].items():
            path=(out/name).resolve()
            if not path.is_relative_to(out):raise ValueError('Artifact path escape')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=value:raise ValueError('Retained artifact hash mismatch')
        review=json.loads((root/'review.json').read_text())
        if review['artifact']!=str(out) or review['artifact_manifest_sha256']!=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest():return None
        return dict(state='retained_failure',path=str(out),label='ĐÃ ĐÓNG DO LỖI ĐO · PARTIAL, CHƯA HOÀN THÀNH PILOT',error=row['error'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration):return None


def joint_reliability_fixture_ready(root):
    try:
        from nino_rl.residual_joint_reliability import validated_latest,ACTIONS
        out=validated_latest(root,ACTIONS[0],check_runtime=False)
        return json.loads((out/'fixture_result.json').read_text())['candidate_compatible'] is True
    except (OSError,ValueError,KeyError,TypeError):return False


def guided_td3_consumed(root,action):
    if action in ('sim-drive-readiness','sim-ready-eval-only','sim-gain-baselines'):return (Path(root)/'state.json').exists()
    if action in ('sim-coverage-v2-preflight','sim-coverage-v2-study'):
        if not (Path(root)/'state.json').exists():return False
        try:
            rows=json.loads((Path(root)/'state.json').read_text())['runs']
            return any(r['action']=='sim-coverage-v2-study' or not r['action'].startswith('sim-coverage-v2-') for r in rows)
        except (OSError,ValueError,KeyError,TypeError):return True
    if action in ('sim-coverage-preflight','sim-coverage-study'):
        if not (Path(root)/'state.json').exists():return False
        try:
            rows=json.loads((Path(root)/'state.json').read_text())['runs']
            return any(r['action']=='sim-coverage-study' for r in rows)
        except (OSError,ValueError,KeyError,TypeError):return True
    if action not in ('sim-v3-contract','sim-v3-train','sim-v3-evaluate','sim-axis-ablation','sim-classical-common','sim-stop-transfer','sim-equal-contract','sim-equal-gazebo','sim-common-td3','sim-reliable-td3','sim-reliable-eval-only','sim-joint-boundary','sim-joint-reliability-fixture','sim-joint-reliability-gazebo'):return False
    path=Path(root)/'state.json'
    if not path.exists():return False
    if action in ('sim-axis-ablation','sim-classical-common','sim-stop-transfer','sim-equal-contract','sim-equal-gazebo','sim-common-td3','sim-reliable-td3','sim-reliable-eval-only','sim-joint-boundary'):return True  # single-batch root, including failure/corrupt ledger
    try:return any(row['action']==action for row in json.loads(path.read_text())['runs'])
    except (OSError,ValueError,KeyError,TypeError):return True  # corrupted ledger is not permission to retry


class ResearchRunner(C.QObject):
    update=C.pyqtSignal(dict)
    closed=C.pyqtSignal()
    def __init__(self,root,parent=None):
        super().__init__(parent);self.root=Path(root);self.process=None;self.buffer=b'';self.action=None;self.last={};self.cancelling=False
    @property
    def busy(self):return self.process is not None
    def start(self,action):
        if self.busy or action not in JOBS:return False
        state=workflow_state(self.root)
        if action=='sim-gain-baselines' and not gain_baseline_release_ready(self.root):
            raise ValueError('Gain baseline chưa release đúng root/source/tests')
        if action=='sim-ready-eval-only' and not ready_eval_release_ready(self.root):
            raise ValueError('Ready eval-only chưa release đúng root/source/tests')
        if action=='sim-drive-readiness' and not drive_readiness_release_ready(self.root):
            raise ValueError('Readiness zero qualification chưa release đúng root/source/tests')
        if action in ('sim-coverage-study','sim-coverage-v2-study') and not coverage_release_ready(self.root,action):
            raise ValueError('Coverage study chưa release; chỉ chạy preflight offline')
        if guided_td3_consumed(self.root,action):
            raise ValueError('Stage đã tiêu thụ; giữ cả failure, không tự mở lại slot')
        if (action.startswith('sim-v2-') or action in ('sim-bias-clear','sim-guidance-contract','sim-v3-baselines','sim-guided-contact')) and state[action]['state']=='verified':
            raise ValueError('Stage đã hoàn tất; xem kết quả. Mở budget/task mới bằng protocol có phiên bản, không bấm lại stage đã đóng.')
        for dep in JOBS[action][1]:
            if state[dep]['state']!='verified':raise ValueError('Chạy và đạt '+dep+' trước')
        if action=='sim-joint-reliability-gazebo' and not joint_reliability_fixture_ready(self.root):raise ValueError('Fixture no-go/unknown; chưa mở qualification Gazebo')
        if action=='sysid' and not (self.root/'registration.json').is_file():raise ValueError('Đăng ký CSV + metadata trước')
        command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_workflow.sh'),action,'--output',str(self.root)]
        if action=='audit-td3':command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_td3_audit.sh'),'--workflow','--output',str(self.root)]
        if action=='factory-td3':command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_factory_smoke.sh'),'--output',str(self.root)]
        if action in ('sim-baselines','sim-train','sim-evaluate'):
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_sim_pilot.sh'),action,'--output',str(self.root)]
        if action.startswith('sim-v2-'):
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_sim_task.sh'),action,'--output',str(self.root)]
        if action in ('sim-bias-clear','sim-guidance-contract'):
            script='residual_clear_bias.sh' if action=='sim-bias-clear' else 'residual_guidance_check.sh'
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts'/script),'--output',str(self.root)]
        if action=='sim-v3-baselines':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_guided_baseline.sh'),'--output',str(self.root)]
        if action=='sim-guided-contact':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_guided_contact.sh'),'--output',str(self.root)]
        if action in ('sim-v3-contract','sim-v3-train','sim-v3-evaluate'):
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_guided_td3.sh'),action,'--output',str(self.root)]
        if action=='sim-axis-ablation':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_axis_ablation.sh'),'--output',str(self.root)]
        if action=='sim-classical-common':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_classical_common.sh'),'--output',str(self.root)]
        if action=='sim-stop-transfer':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_stop_transfer.sh'),'--output',str(self.root)]
        if action=='sim-equal-contract':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_equal_information.sh'),'--output',str(self.root)]
        if action in ('sim-joint-reliability-fixture','sim-joint-reliability-gazebo'):
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_joint_reliability.sh'),action,'--output',str(self.root)]
        if action=='sim-joint-boundary':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_joint_boundary.sh'),'--output',str(self.root)]
        if action=='sim-reliable-eval-only':
            from nino_rl.residual_reliable_eval_only import parent
            parent(check_runtime=False)
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_reliable_eval_only.sh'),'--output',str(self.root)]
        if action=='sim-reliable-td3':
            from nino_rl.residual_reliable_td3 import parent
            parent(check_runtime=False)
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_reliable_td3.sh'),'--output',str(self.root)]
        if action=='sim-common-td3':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_common_td3.sh'),'--output',str(self.root)]
        if action=='sim-equal-gazebo':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_equal_gazebo.sh'),'--output',str(self.root)]
        if action in ('sim-coverage-preflight','sim-coverage-study'):
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_coverage_study.sh'),action,'--output',str(self.root)]
        if action in ('sim-coverage-v2-preflight','sim-coverage-v2-study'):
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_coverage_study_v2.sh'),action,'--output',str(self.root)]
        if action=='sim-ready-eval-only':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_ready_eval_only.sh'),'--output',str(self.root)]
        if action=='sim-drive-readiness':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/residual_drive_readiness.sh'),'--output',str(self.root)]
        if action=='sim-gain-baselines':
            command=['/usr/bin/setsid','/bin/bash',str(repository()/'src/nino_rl/scripts/gain_baseline_qualification.sh'),'--output',str(self.root)]
        self.action=action;self.last={};self.cancelling=False;self.buffer=b''
        p=C.QProcess(self);self.process=p;p.setProcessChannelMode(C.QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self.read);p.finished.connect(self.finished);p.errorOccurred.connect(self.error)
        p.start(command[0],command[1:]);self.update.emit(dict(state='running',action=action,message='Đang khởi động job local; không nối Pi'))
        return True
    def read(self):
        if not self.process:return
        self.buffer+=bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1);line=line.decode('utf8','replace')
            try:
                if line.startswith('@@NINO_RESEARCH@@'):
                    row=json.loads(line[len('@@NINO_RESEARCH@@'):]);self.last=row;self.update.emit(dict(row,state='progress'));continue
            except ValueError:pass
            self.update.emit(dict(state='log',message=line))
    def finished(self,code=1,status=None):
        if self.process is None:return
        self.read();p=self.process;self.process=None
        if self.buffer:self.update.emit(dict(state='log',message=self.buffer.decode('utf8','replace')));self.buffer=b''
        self.update.emit(dict(self.last,state='closed',action=self.action,returncode=code,cancelled=self.cancelling))
        p.deleteLater();self.closed.emit()
    def error(self,error):
        self.update.emit(dict(state='log',message=self.process.errorString() if self.process else 'process unavailable'))
        if self.process and self.process.state()==C.QProcess.NotRunning:self.finished()
    def cancel(self):
        if self.process and self.process.processId() and not self.cancelling:
            self.cancelling=True
            try:os.kill(int(self.process.processId()),signal.SIGINT)
            except ProcessLookupError:pass
            self.update.emit(dict(state='log',message='Đã yêu cầu hủy; đợi ghi manifest và đóng process con. Không tự chạy lại.'))
