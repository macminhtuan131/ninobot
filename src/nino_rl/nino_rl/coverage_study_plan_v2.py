"""V2 metadata correction; retain the exact V1 scientific design and limits."""
import json
from pathlib import Path
from .coverage_study_plan import validate as validate_scientific_plan

PROTOCOL_ID = "nino_critic_coverage_v2_2026_11_06"
REVISION = {'previous_fingerprint': '1cd68b11dea8aee0302094294d89636276df23d6dfc2dc314af1c4a6433d89be', 'failed_manifest_sha256': '3f73d59ddfc5d3381ae202561113e864e75379e4618adba1c42e8ff965df7fab', 'correction': 'declared_condition_metadata_before_real_validator', 'budget_source': 'new_proposal_not_v1_remaining_slots'}

def default_config():
    source = Path(__file__).resolve().parents[1] / "config/residual_coverage_study_v2.json"
    if source.is_file(): return source
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("nino_rl")) / "config/residual_coverage_study_v2.json"

def validate(p):
    if p.get("protocol_id") != PROTOCOL_ID or p.get("revision") != REVISION:
        raise ValueError("V2 identity/correction lineage changed")
    return validate_scientific_plan(p)

def load(path=None):
    p = json.loads(Path(path or default_config()).read_text())
    validate(p)
    return p
