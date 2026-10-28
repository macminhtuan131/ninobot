"""Validate review artifacts and collector dry-run without ROS or robot access."""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

DOCS = Path(__file__).resolve().parents[1]
REPO = DOCS.parent
PKG = REPO/'src/nino_pi'
sys.path.insert(0, str(PKG))
from nino_pi import collect_real_data as collect

profile = PKG/'config/stm32_usb_wheel_response_collection.json'
session_path = PKG/'config/wheel_response_session.template.json'
config = collect.load_config(profile)
required = {row['name'] for row in config['topics'] if row['required']}
assert required == {'/cmd_vel', '/motor_fb', '/motor_status'}
full = collect.load_config(PKG/'config/stm32_usb_collection.json')
assert {'/scan','/odom','/tf'} <= {t['name'] for t in full['topics'] if t['required']}
session = json.loads(session_path.read_text())
generic = json.loads((PKG/'config/real_session.template.json').read_text())
for section in ('firmware_integration','hardware','geometry_and_load',
                'controller','sensors_and_clocks','power','scenario'):
    assert session[section] == generic[section], section
assert session['motion_contract']['release_status'] == 'draft_not_released'
assert session['experiment_design']['accepted_total_trial_budget'] is None
assert session['motion_contract']['agreed_forward_reverse_yaw_limits_units_and_evidence'] is None
blocked = AssertionError('Process creation forbidden in offline validation')
with tempfile.TemporaryDirectory(prefix='nino_wheel_check_') as tmp:
    output = Path(tmp)/'must_not_exist'
    stdout = io.StringIO()
    with patch('subprocess.Popen', side_effect=blocked), \
         patch('subprocess.run', side_effect=blocked), \
         contextlib.redirect_stdout(stdout):
        rc = collect.main(['--config', str(profile), '--session', str(session_path),
                           '--qos', str(PKG/'config/stm32_usb_collection_qos.yaml'),
                           '--output', str(output), '--check'])
    assert rc == 0 and not output.exists()
    plan = json.loads(stdout.getvalue())
    assert plan['motion_commands_sent'] == 0
assert 'rclpy' not in sys.modules
tree = ast.parse((PKG/'setup.py').read_text())
setup_call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name) and n.func.id == 'setup')
data_files = next(k.value for k in setup_call.keywords if k.arg == 'data_files')
static_files = ast.literal_eval(data_files.elts[1].elts[1])
assert 'WHEEL_RESPONSE_PROTOCOL.md' in static_files
for name in static_files:
    assert (PKG/name).is_file(), name
source_meta = json.loads((DOCS/'external_reviews/NINO_DEEP_RESEARCH_RECEIVED_2026-10-28.provenance.json').read_text())
source = DOCS/'external_reviews'/source_meta['preserved_copy']
assert hashlib.sha256(source.read_bytes()).hexdigest() == source_meta['sha256']
checked = [profile, session_path, PKG/'WHEEL_RESPONSE_PROTOCOL.md',
           DOCS/'NINO_PROGRESS_AND_NEXT_STEPS_2026-10-28.md',
           DOCS/'NINO_RESEARCH_REPORT_SOURCE_CHECK_2026-10-28.md']
for path in checked:
    assert not any(line != line.rstrip() for line in path.read_text().splitlines()), path
result = {'status': 'offline_preparation_verified_not_hardware_ready',
          'required_topics': sorted(required), 'full_navigation_requirements_preserved': True,
          'generic_evidence_sections_preserved': True,
          'unaccepted_limits_and_trial_budget_remain_null': True,
          'collector_check_exit_code': rc, 'process_creation_blocked_during_check': True,
          'rclpy_imported': False, 'output_directory_created': False,
          'motion_commands_sent': 0, 'hardware_trials': 0, 'simulation_runs': 0,
          'package_share_protocol_entry_present': True, 'received_report_hash_matches': True,
          'artifact_sha256': {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in checked}}
(Path(__file__).parent/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
