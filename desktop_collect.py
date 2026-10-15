"""Conservative single-product UI Automation for an existing Windows Chrome.
No CDP, clipboard, credential access, fixed coordinates or hidden APIs.
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from dianxiaomi_reader import source_identity
from data_paths import resolve_default_file

SUCCESS = '采集成功'
BLOCKERS = ('验证码', '人机验证', '安全验证', 'captcha', 'verify you are human', '采集失败', '登录失效')
ADDRESS_NAMES = {'地址和搜索栏', '地址栏和搜索栏', 'Address and search bar', 'Address and Search Bar'}


class StopOperation(RuntimeError):
    pass


class AttemptLedger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS attempts (product_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP)')

    def claim(self, product_id):
        try:
            self.db.execute('BEGIN IMMEDIATE')
            existing = self.db.execute('SELECT status FROM attempts WHERE product_id=?', (product_id,)).fetchone()
            if existing and existing[0] != 'confirmed_no_click':
                raise StopOperation('该商品已有操作记录；请使用 --verify-only 先核验，不自动重复点击。')
            self.db.execute('INSERT INTO attempts(product_id,status) VALUES (?,?) ON CONFLICT(product_id) DO UPDATE SET status=excluded.status, updated=CURRENT_TIMESTAMP', (product_id, 'pending_verification'))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def clear_confirmed_no_click(self, product_id):
        # Explicit operator attestation only for legacy preflight failures.
        # Preserve the record rather than erase all attempt history.
        with self.db:
            row = self.db.execute('SELECT status FROM attempts WHERE product_id=?', (product_id,)).fetchone()
            if not row or row[0] != 'pending_verification':
                raise StopOperation('只能解除已确认未点击的旧待核验记录；不会解除成功或其他状态。')
            self.db.execute('UPDATE attempts SET status=?, updated=CURRENT_TIMESTAMP WHERE product_id=?',
                            ('confirmed_no_click', product_id))

    def status(self, product_id, status):
        self.db.execute('INSERT INTO attempts(product_id,status) VALUES (?,?) ON CONFLICT(product_id) DO UPDATE SET status=excluded.status, updated=CURRENT_TIMESTAMP', (product_id, status))
        self.db.commit()

    def note_duplicate(self, product_id):
        self.db.execute("INSERT INTO attempts(product_id,status) VALUES (?, 'skipped_duplicate') "
                        "ON CONFLICT(product_id) DO UPDATE SET "
                        "status=CASE WHEN attempts.status='verified_present' THEN attempts.status ELSE excluded.status END, "
                        "updated=CURRENT_TIMESTAMP", (product_id,))
        self.db.commit()

    def close(self):
        self.db.close()


def normalized_address(value):
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    return value


def exact_product(value, product_id):
    return source_identity(normalized_address(value))[1] == product_id


def inspect_texts(texts):
    lowered = '\n'.join(texts).lower()
    if any(word.lower() in lowered for word in BLOCKERS):
        raise StopOperation('检测到验证或失败提示，已停止；请人工处理，不重复采集。')
    return SUCCESS in lowered


def has_duplicate_button(controls, texts):
    return (any('采集到店小秘' in text for text in texts)
            and any(c.element_info.control_type in {'Button', 'Hyperlink', 'Text'}
                    and c.window_text().strip() == '重复采集' for c in controls))


class WindowsChrome:
    def __init__(self):
        if sys.platform != 'win32':
            raise StopOperation('本模块只能在 Windows 桌面运行。')
        from pywinauto import Desktop
        import psutil
        import win32gui
        self.desktop = Desktop(backend='uia')
        self.psutil = psutil
        self.win32gui = win32gui

    def foreground(self):
        handle = self.win32gui.GetForegroundWindow()
        root = self.desktop.window(handle=handle).wrapper_object()
        if root.class_name() != 'Chrome_WidgetWin_1':
            raise StopOperation('前台不是 Chrome，停止操作。')
        if Path(self.psutil.Process(root.process_id()).exe()).name.lower() != 'chrome.exe':
            raise StopOperation('前台程序不是 Google Chrome，停止操作。')
        return root

    def controls(self, root):
        # UIA may be unavailable on some Chrome versions. Never fall back to guessing.
        controls = root.descendants()
        if len(controls) > 10000:
            raise StopOperation('页面控件过多，停止自动操作。')
        return [control for control in controls if control.is_visible()]

    def native_toolbar_control(self, root, control):
        """Reject page-created fields even if they imitate the omnibox label."""
        root_id = root.element_info.runtime_id
        current = control
        toolbar = False
        for _ in range(20):
            if current is None:
                return False, False
            if current.element_info.runtime_id == root_id:
                return True, toolbar
            kind = current.element_info.control_type
            if kind == 'Document':
                return False, False
            toolbar = toolbar or kind == 'ToolBar'
            current = current.parent()
        return False, False

    def address(self, root, controls):
        preferred, fallback = set(), set()
        for control in controls:
            if control.element_info.control_type not in {'Edit', 'ComboBox'}:
                continue
            native, toolbar = self.native_toolbar_control(root, control)
            if not native:
                continue
            named = control.window_text().strip() in ADDRESS_NAMES
            if not named and not toolbar:
                continue
            try:
                # Some UIA ComboBox wrappers expose ValuePattern but not get_value.
                value = control.iface_value.CurrentValue
                address = normalized_address(value)
                parsed = urlsplit(address)
                if parsed.scheme not in {'http', 'https'} or not parsed.hostname or '.' not in parsed.hostname:
                    continue
                (preferred if named else fallback).add(address)
            except Exception:
                continue
        addresses = preferred or fallback
        if len(addresses) != 1:
            raise StopOperation('无法唯一读取 Chrome 地址栏；请先运行 --diagnose，不进行点击。')
        return addresses.pop()

    def diagnose(self):
        root = self.foreground()
        controls = self.controls(root)
        edits = []
        for control in controls:
            if control.element_info.control_type not in {'Edit', 'ComboBox'}:
                continue
            native, toolbar = self.native_toolbar_control(root, control)
            if native:
                edits.append({'type': control.element_info.control_type,
                              'known_address_label': control.window_text().strip() in ADDRESS_NAMES,
                              'in_toolbar': toolbar})
        plugin_controls = []
        for control in controls:
            label = control.window_text().strip()
            if label in {'开始采集', '重复采集', '采集到店小秘'}:
                plugin_controls.append({'label': label, 'type': control.element_info.control_type,
                                        'enabled': bool(control.is_enabled())})
        result = {'diagnostic_version': 2, 'visible_control_count': len(controls),
                  'native_edit_controls': edits, 'plugin_controls': plugin_controls}
        try:
            address = self.address(root, controls)
            host = (urlsplit(address).hostname or '').lower()
            result['address_readable'] = True
            result['page_family'] = ('dianxiaomi' if host == 'dianxiaomi.com' or host.endswith('.dianxiaomi.com')
                                     else 'aliexpress' if host == 'aliexpress.com' or host.endswith('.aliexpress.com') else 'other')
        except StopOperation:
            result['address_readable'] = False
        # Only booleans/counts/fixed categories. No URLs, titles, form values or account data.
        return result

    def snapshot(self):
        root = self.foreground()
        controls = self.controls(root)
        address = self.address(root, controls)
        # Values are inspected in memory only, never printed, uploaded or persisted.
        texts = [control.window_text() for control in controls
                 if control.element_info.control_type in {'Text', 'Button', 'Hyperlink', 'Document'}]
        if any(control.element_info.control_type == 'Window' for control in controls):
            raise StopOperation('检测到子窗口或弹窗，停止自动操作。')
        return root, controls, address, texts

    def click_once(self, product_id, before_click=None):
        root, controls, address, texts = self.snapshot()
        if not exact_product(address, product_id):
            raise StopOperation('前台地址栏不是指定速卖通商品，不进行点击。')
        success = inspect_texts(texts)
        if has_duplicate_button(controls, texts):
            return 'duplicate'
        if success:
            raise StopOperation('已有采集成功提示，可能是旧结果；请先核验，不能重复点击。')
        if not any('采集到店小秘' in text for text in texts):
            raise StopOperation('未找到店小秘浮窗标识，不进行点击。')
        matching = [c for c in controls if c.window_text().strip() == '开始采集' and c.is_enabled()]
        candidates = [c for c in matching if c.element_info.control_type in {'Button', 'Hyperlink'}]
        if not candidates:
            # Some extension DOM controls are exposed as Text, not Button.
            # Still require one exact visible label and the live hit test below.
            candidates = [c for c in matching if c.element_info.control_type == 'Text']
        if len(candidates) != 1:
            raise StopOperation('无法唯一定位“开始采集”；请运行新版 --diagnose 并查看 plugin_controls，不会猜测坐标。')
        button = candidates[0]
        bounds = button.rectangle()
        if bounds.width() <= 0 or bounds.height() <= 0:
            raise StopOperation('按钮区域无效。')
        # UIA locator + live hit test, rather than a stored screen coordinate.
        point = (bounds.left + bounds.width() // 2, bounds.top + bounds.height() // 2)
        hit = self.desktop.from_point(*point)
        if hit.element_info.runtime_id != button.element_info.runtime_id:
            raise StopOperation('按钮被其他元素覆盖，停止点击。')
        if self.win32gui.GetForegroundWindow() != root.handle:
            raise StopOperation('窗口焦点发生变化，停止点击。')
        if before_click is not None:
            before_click()
        button.click_input()
        return 'clicked'

    def wait_success(self, product_id, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _, controls, address, texts = self.snapshot()
            if not exact_product(address, product_id):
                raise StopOperation('等待期间离开目标商品页，结果未知，先核验。')
            success = inspect_texts(texts)
            if has_duplicate_button(controls, texts):
                return 'duplicate'
            if success:
                return 'success'
            time.sleep(0.5)
        raise StopOperation('未在时限内读到成功提示；结果未知，先核验，不重试点击。')

    def verify_source(self, product_id):
        _, controls, address, texts = self.snapshot()
        host = (urlsplit(address).hostname or '').lower()
        if host != 'dianxiaomi.com' and not host.endswith('.dianxiaomi.com'):
            raise StopOperation('前台不是店小秘页面，无法核验。')
        inspect_texts(texts)
        # Explicit source label guards against treating an unrelated URL as evidence.
        if not any('来源URL' in text.replace(' ', '') for text in texts):
            raise StopOperation('未识别来源URL字段，请打开采集商品详情页后重试核验。')
        for control in controls:
            if control.element_info.control_type not in {'Edit', 'Hyperlink', 'Text'}:
                continue
            value = control.window_text().strip()
            if control.element_info.control_type == 'Edit':
                try:
                    value = control.get_value().strip()
                except Exception:
                    continue
            if exact_product(value, product_id):
                return True
        return False


def main():
    parser = argparse.ArgumentParser(description='Windows 当前 Chrome 单商品采集试验；首次只处理一个商品')
    parser.add_argument('--product-url')
    parser.add_argument('--diagnose', action='store_true', help='只读检查当前 Chrome 可访问性，不点击或写入任务')
    parser.add_argument('--switch-seconds', type=int, default=5, help='切换窗口等待秒数，默认5')
    parser.add_argument('--skip-source-verification', action='store_true', help='插件成功提示后结束，保留待核验状态')
    parser.add_argument('--clear-confirmed-no-click', action='store_true', help='仅解除人工确认从未点击的旧待核验记录，不执行采集')
    parser.add_argument('--verify-only', action='store_true', help='未知结果先核验，不点击插件')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--db', type=Path, help='数据库路径，Windows 默认 E:\\店小秘数据\\desktop-attempts.sqlite3')
    args = parser.parse_args()
    _, product_id = source_identity(args.product_url or '')
    if not args.diagnose and (not product_id or not args.product_url.startswith('https://')):
        parser.error('需要 HTTPS 速卖通商品详情 URL')
    if not 3 <= args.switch_seconds <= 60:
        parser.error('--switch-seconds 必须在 3 到 60 秒之间')
    if not 1 <= args.timeout <= 120:
        parser.error('--timeout 必须在 1 到 120 秒之间')
    if args.skip_source_verification and args.verify_only:
        parser.error('--skip-source-verification 不能与 --verify-only 同用')
    if args.clear_confirmed_no_click and (args.verify_only or args.diagnose or args.skip_source_verification):
        parser.error('--clear-confirmed-no-click 必须单独使用，只处理记录，不采集')
    ledger = None
    attempt_started = False
    try:
        chrome = WindowsChrome()
        if args.diagnose:
            import json
            print(f'请在 {args.switch_seconds} 秒内切到目标 Chrome 页面。只检查，不点击。')
            time.sleep(args.switch_seconds)
            print(json.dumps(chrome.diagnose(), ensure_ascii=False, indent=2))
            return 0
        args.db = resolve_default_file(args.db, 'desktop-attempts.sqlite3')
        ledger = AttemptLedger(args.db)
        if args.clear_confirmed_no_click:
            ledger.clear_confirmed_no_click(product_id)
            print('已标记为人工确认未点击，允许重新检查；本命令未执行采集。')
            return 0
        if not args.verify_only:
            print('插件显示“重复采集”时跳过，不点击、不要求入箱核验。')
            print('本命令将直接尝试采集一次，不再要求输入 COLLECT。')
            print(f'请在 {args.switch_seconds} 秒内切换到目标商品的 Chrome 标签页；倒计时后不要操作鼠标键盘。')
            time.sleep(args.switch_seconds)
            # Reserve only after preflight checks, immediately BEFORE the actual click.
            def reserve_attempt():
                nonlocal attempt_started
                ledger.claim(product_id)
                attempt_started = True
            outcome = chrome.click_once(product_id, before_click=reserve_attempt)
            if outcome != 'duplicate':
                outcome = chrome.wait_success(product_id, args.timeout)
            if outcome == 'duplicate':
                ledger.note_duplicate(product_id)
                print('已跳过：插件显示“重复采集”，不点击该按钮；未进行来源核验。')
                print('当前单商品任务结束，批量队列可按此状态继续下一件商品。')
                return 0
            print('已读取插件成功提示，尚未核验入箱。')
            if args.skip_source_verification:
                ledger.status(product_id, 'plugin_success_unverified')
                print('已按要求跳过来源核验：插件提示成功，入箱未核验。此商品不会自动重复点击。')
                return 0
        print('请在原 Chrome 中手动进入店小秘采集箱，按来源 ID 搜索并打开该商品详情。不要保存或认领。')
        print('待核验来源 ID：', product_id)
        input(f'准备好后回终端按 Enter，再在 {args.switch_seconds} 秒内切回该店小秘详情页：')
        time.sleep(args.switch_seconds)
        if not chrome.verify_source(product_id):
            raise StopOperation('未找到精确来源 ID，保持待核验；不要重复采集。')
        ledger.status(product_id, 'verified_present')
        print('核验通过：当前店小秘页面的可见来源链接与目标 ID 匹配。仅证明存在，不证明此次新建或整店采集成功。')
        return 0
    except StopOperation as error:
        print(str(error))
        if not attempt_started and not args.verify_only and not args.clear_confirmed_no_click:
            print('本次未发出点击；检查失败不会新建采集记录。已有的旧记录不自动清除。')
        else:
            print('未完成时先人工检查；未知结果请使用 --verify-only，不自动重试。')
        return 1
    except (Exception, KeyboardInterrupt) as error:
        print('已停止；异常类型：', type(error).__name__, '。不输出页面或账号内容；请先人工核验。')
        return 1
    finally:
        if ledger:
            ledger.close()


if __name__ == '__main__':
    raise SystemExit(main())
