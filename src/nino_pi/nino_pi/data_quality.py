"""Conservative evidence grading. Never changes control readiness or raw manifests."""
import json
from pathlib import Path

LEVELS = {
    "Q0": "Chưa có bằng chứng / chỉ demo",
    "Q1": "Raw có nhưng thiếu, lỗi hoặc chưa kiểm đủ",
    "Q2": "Toàn vẹn raw đạt; chưa xác nhận claim chuyển động",
    "Q3": "Đủ cho claim hẹp đã review, trong cửa sổ đã nêu",
    "Q4": "Độ lặp được đánh giá theo protocol riêng",
}


def load_catalog(path=None):
    path = Path(path) if path else Path(__file__).with_name("project_evidence.json")
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1:
        raise ValueError("Không hỗ trợ schema evidence")
    for name in ("data", "parameters", "sessions", "tasks", "corrections"):
        if not isinstance(data.get(name), list):
            raise ValueError("Thiếu danh sách " + name)
    return data


def assess_capture(result=None, manifest=None, config=None, demo=False):
    """Auto grading stops at Q2. Counts/hashes cannot establish coverage or body motion.

    manifest is the collector's closed report, not a user-entered quality score.
    Missing keys remain unknown; no numerical application gates are invented.
    """
    result, manifest, config = result or {}, manifest or {}, config or {}
    report = dict(schema_version=1, rubric="nino_claim_quality_v1", level="Q0",
                  label=LEVELS["Q0"], scope="Phiên hiện tại; kiểm raw tự động, chưa review cửa sổ",
                  checks=[], limitations=["Không tự đóng P0/E1, không cấp lượt chạy hoặc đổi giới hạn."])
    if demo or result.get("status") == "DEMO_ONLY_NO_DATA":
        report["limitations"].append("DEMO không tạo dữ liệu thật; trạng thái mô phỏng không vào inventory.")
        return report
    if not result:
        report["limitations"].append("Chưa có kết quả đóng phiên.")
        return report
    checks = report["checks"]
    def add(name, verdict, detail):
        checks.append(dict(name=name, verdict=verdict, detail=detail))
    hash_known = (type(result.get("checked_hashes")) is int and result["checked_hashes"] > 0
                  and isinstance(result.get("hash_mismatches"), list))
    hash_ok = hash_known and not result["hash_mismatches"]
    add("SHA256", "đạt" if hash_ok else "lỗi" if hash_known else "chưa biết",
        f"{result.get('checked_hashes', 0)} file đã kiểm; mismatch={result.get('hash_mismatches', 'unknown')}")
    bag = manifest.get("bag", {})
    closed = (manifest.get("status") == "captured_not_calibrated"
              and manifest.get("reason") == "duration_reached"
              and result.get("collector_exit") == 0 and manifest.get("issues") == []
              and isinstance(bag, dict) and bag.get("errors") == [])
    add("Đóng bag / SQLite / metadata", "đạt" if closed else "chưa đủ",
        "Theo kiểm tra của collector khi đóng; chưa tính lại từ raw ở màn hình này.")
    topics = bag.get("topics", {}) if isinstance(bag, dict) else {}
    required = [r["name"] for r in config.get("topics", []) if r.get("required") is True]
    counts_ok = bool(required) and all(type(topics.get(n, {}).get("count")) is int
                   and topics[n]["count"] > 0 for n in required)
    missing = [n for n in required if not topics.get(n, {}).get("count", 0)]
    add("Kênh bắt buộc", "có mẫu" if counts_ok else "chưa đủ",
        "Thiếu: " + str(missing) if required else "Chưa có config kênh bắt buộc để đối chiếu.")
    add("Clock / gap / coverage theo cửa sổ", "chưa review", "Counts không thay coverage; chưa giải mã header/window ở bước tự động này.")
    add("Workflow", str(result.get("workflow_status", "chưa biết")),
        "Workflow hoàn thành không xác nhận motor hay thân xe thực hiện đúng.")
    add("Thân xe / độ lặp / slip", "chưa xác nhận", "Cần reference độc lập và review riêng; nhãn operator không tự thành số đo.")
    level = "Q2" if hash_ok and closed and counts_ok and result.get("status") == "captured_not_calibrated" else "Q1"
    report.update(level=level, label=LEVELS[level])
    report["limitations"].extend([
        "Q2 chỉ xác nhận điều kiện raw; Q3 cần review claim, clock, cửa sổ và confound bằng nguồn cụ thể.",
        "Encoder dừng không là stopping thân xe; yaw residual không quan sát được mọi dạng trượt.",
        "Ngưỡng CV 3%, lệch 5%, stop 150 ms và cải thiện 15% trong báo cáo ngoài chưa được chấp nhận.",
    ])
    return report


def quality_text(report):
    lines = [report["level"] + " · " + report["label"], report.get("scope", "")]
    lines += [f"• {r['name']}: {r['verdict']} — {r['detail']}" for r in report.get("checks", [])]
    lines += ["Giới hạn: " + s for s in report.get("limitations", [])]
    return "\n".join(lines)
