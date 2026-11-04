"""Render copyable operator commands. Rendering never executes SSH or ROS."""
from pathlib import Path
import re
import shlex

RUNTIME = 'collection_guided_20261103_v2'
RECIPES = {
    'inventory': ('Kiểm kê cảm biến / backend', 'Chỉ đọc; không phát enable/vận tốc.'),
    'stationary': ('Đứng yên · thu 60 giây', 'Chỉ recorder; không ARM/tiến. Không cần lặp nếu chỉ muốn kiểm lại IMU sign.'),
    'diagnostic': ('Tiến–dừng + video · 1 lượt', 'Firmware RC hiện có: RC AUTO. 0,05 m/s; ramp 0,10 m/s²; source 2 s; bag 60 s. Một lượt mới, không dùng slot cũ.'),
    'review': ('Kiểm dữ liệu lượt vừa thu', 'Chỉ đọc raw; kết quả derived riêng. Không tự kết luận thân tiến hoặc tự mở lượt tiếp.'),
    'repeatability': ('Độ lặp · chuẩn bị sau diagnostic', 'Chỉ tạo draft tối đa 3 lượt. Chưa có lệnh motion repeatability trước review diagnostic/protocol mới.'),
    'body_reference': ('Body reference / geometry · chuẩn bị', 'Chỉ tạo draft đo định lượng; chưa tự tăng tốc hoặc tính slip.'),
    'gui_authority': ('Backend GUI không RC · chuẩn bị', 'Bản firmware authority chưa được xác nhận nạp. Copy bridge không biến firmware RC thành GUI authority.'),
    'future': ('Navigation / vật cản / learning · kế hoạch', 'Chỉ chuẩn bị kế hoạch. Chưa có protocol/limits cho chuyển động hoặc vật cản ở bước này.'),
}
TASK_RECIPES = {
    'T01': 'inventory', 'T02': 'inventory', 'T03': 'inventory', 'T04': 'gui_authority',
    'T05': 'diagnostic', 'T06': 'diagnostic', 'T07': 'diagnostic', 'T08': 'review',
    'T09': 'review', 'T10': 'repeatability', 'T11': 'review', 'T12': 'body_reference',
    'T13': 'inventory', 'T14': 'body_reference',
    'T19': 'diagnostic', 'T20': 'body_reference', 'T21': 'future',
    'T22': 'future', 'T23': 'future', 'T24': 'future',
    'T15': 'future', 'T16': 'future', 'T17': 'future', 'T18': 'future',
}


def validate_connection(host, key):
    # SSH destination is an argv, and is also validated before rendering a shell snippet.
    if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9][A-Za-z0-9_.-]*', host):
        raise ValueError('Địa chỉ cần có dạng user@IP hoặc user@hostname')
    if not key or any(c in key for c in '\r\n\x00'):
        raise ValueError('SSH key path không hợp lệ')


def render_recipe(name, host='d@192.168.0.109', key=None):
    if name not in RECIPES:
        raise ValueError('Không có recipe cho bước này; cần protocol riêng trước khi chạy')
    key = key or str(Path.home()/'.ssh/nino_pi_flash_ed25519')
    validate_connection(host, key)
    package_parent = str(Path(__file__).resolve().parents[1])
    local = 'env PYTHONPATH=' + shlex.quote(package_parent) + ' /usr/bin/python3 -m nino_pi.collection_deploy'
    flags = ' --host ' + shlex.quote(host) + ' --key ' + shlex.quote(key)
    ssh = 'ssh -tt -o BatchMode=yes -o ConnectTimeout=5 -i ' + shlex.quote(key) + ' ' + shlex.quote(host)
    def remote(action):
        return ssh + ' ' + shlex.quote('bash "$HOME/nino_runtime/' + RUNTIME + '/session.sh" ' + action)
    def step(title, terminal, command, effect, note=''):
        return dict(title=title, terminal=terminal, command=command, effect=effect, note=note)
    deploy = step('0 · Cài bộ lệnh vào Pi (một lần)', 'Laptop', local + ' deploy' + flags,
                  'Chỉ copy', 'Không sửa firmware, không chạy stack. Cài lại cùng phiên bản không reset ledger.')
    inspect = step('1 · Kiểm driver / topic', 'Laptop', remote('inventory'), 'Chỉ đọc',
                   'Agent, bridge và LiDAR cần đang chạy như sensor stage trước đó. Nếu thiếu, giữ output lỗi để sửa; không tự flash.')
    review = step('Đọc raw + hash + kết quả', 'Laptop, sau khi recorder kết thúc', remote('review'), 'Chỉ đọc / derived',
                  'Báo cáo chưa tự xác nhận video/body hoặc hoàn tất review người vận hành.')
    fetch = step('Copy dữ liệu về laptop', 'Laptop, sau khi recorder kết thúc', local + ' fetch' + flags,
                 'Chỉ copy', 'Copy nguyên thư mục raw/sidecar; không xóa dữ liệu trên Pi.')
    if name == 'inventory':
        steps = [deploy, inspect]
    elif name == 'stationary':
        steps = [deploy, inspect, step('2 · Thu đứng yên 60 s', 'Laptop', remote('stationary'),
                 'Chỉ thu', 'Giữ xe yên; không enable/teleop. Chờ FINISHED, không reboot trong lúc đóng bag.'), fetch]
    elif name == 'diagnostic':
        steps = [deploy, inspect,
            step('2 · Chạy command stack ở ZERO', 'Terminal 1 · Laptop', remote('start-stack'),
                 'Phát zero qua stack', 'Chờ READY và giữ terminal này mở. Không ARM motor từ bước này.'),
            step('3 · Thu bag 60 s + bật quay video', 'Terminal 2 · Laptop', remote('record-diagnostic'),
                 'Chỉ thu / cấp đúng 1 slot khi người vận hành bắt đầu',
                 'RC AUTO, vùng trống. Nhập AUTO và ghi pose/caster/video. Video thấy bánh, thân, mốc sàn; chạy bước 4 ngay khi báo Recorder only.'),
            step('4 · Một lần tiến–zero–disable', 'Terminal 3 · Laptop', remote('run-trial'),
                 'ENABLE + tiến 0,05 m/s trong 2 s, rồi zero/disable',
                 'Đây là bước duy nhất yêu cầu chuyển động. Giữ vùng trống; STOP/fault/stale hủy lượt, không auto retry. Chờ terminal 2 FINISHED trước tắt nguồn.'),
            review, fetch]
    elif name == 'review':
        steps = [review, fetch]
    elif name in ('repeatability', 'body_reference', 'future'):
        steps = [deploy, step('Tạo draft, không chạy robot', 'Laptop', remote('plan ' + name), 'Chỉ tạo kế hoạch',
                 'Draft ghi prerequisites/unknown; không mở lại pilot đã đóng, không tự cấp thêm lượt.')]
    else:
        script = Path(__file__).resolve().parents[1]/'scripts/deploy_mode_bridge.sh'
        steps = [step('Copy bridge hỗ trợ GUI', 'Laptop', 'env NINO_SSH_KEY=' + shlex.quote(key) + ' bash ' + shlex.quote(str(script)) + ' ' + shlex.quote(host),
                 'Chỉ copy', 'Cần firmware tương thích và kiểm authority riêng. Không có lệnh flash tự động trong recipe này.')]
    return dict(id=name, title=RECIPES[name][0], note=RECIPES[name][1], steps=steps,
                copy_only=True, no_automatic_execution=True)
