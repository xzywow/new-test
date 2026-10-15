"""Stage A: inspect UI, manually collect ONE product, verify a visible source link.
No private APIs, extension popup assumptions, automatic business actions or credentials.
"""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from chrome_diagnostics import find_chrome, inspect_extension, validate_endpoint, EXTENSION_ID
from dianxiaomi_reader import source_identity
from extension_package import prepare_extension


def exact_source_matches(rows, expected_id):
    matches = 0
    for row in rows:
        for href in row:
            _, product_id = source_identity(href)
            if product_id == expected_id:
                matches += 1
                break
    return matches


def verify_visible(page, selector, product_id):
    host = (urlsplit(page.url).hostname or '').lower()
    if host != 'dianxiaomi.com' and not host.endswith('.dianxiaomi.com'):
        raise ValueError('核验标签页必须是店小秘网页')
    rows = page.locator(selector)
    if not rows.count():
        return {'status': 'pending_verification', 'reason': 'no_rows_matched', 'matched_rows': 0}
    links = rows.evaluate_all('''rows => rows.filter(r => r.getClientRects().length && getComputedStyle(r).visibility !== 'hidden')
        .map(r => Array.from(r.querySelectorAll('a[href]')).filter(a => a.getClientRects().length && getComputedStyle(a).visibility !== 'hidden').map(a => a.href))''')
    matches = exact_source_matches(links, product_id)
    return {'status': 'verified_present' if matches else 'pending_verification',
            'matched_rows': matches, 'reason': 'exact_aliexpress_source_id' if matches else 'no_unique_source_match',
            'scope': 'visible_rows_only_not_entire_collection_box'}


def choose_page(context, purpose):
    # Do not print URLs: tabs can contain OAuth codes or other credentials.
    pages = [p for p in context.pages if not p.is_closed()]
    print(f'当前有 {len(pages)} 个标签页。请按浏览器标签页从左到右的编号选择{purpose}（0 开始）。')
    index = int(input('标签页编号：'))
    if index < 0 or index >= len(pages):
        raise ValueError('无效标签页编号')
    return pages[index]


def ui_candidates(page):
    # Capture only a bounded list of generic operation words, not page text or HTML.
    return page.locator('button, a, [role=button]').evaluate_all('''nodes => [...new Set(nodes
        .filter(n => n.getClientRects().length && getComputedStyle(n).visibility !== 'hidden')
        .map(n => (n.innerText || n.getAttribute('aria-label') || ''))
        .flatMap(t => t.match(/批量采集|单品采集|采集到店小秘|店小秘采集|采集/g) || []))].slice(0,20)''')


def run_session(context, args, report):
    input('请打开 chrome://extensions，核对官方来源、ID、版本及启用状态；完成后按 Enter。')
    if input('已核对所填 ID 属于官方店小秘扩展且已启用？输入 YES：') != 'YES':
        report['reason'] = 'extension_not_confirmed'
        return
    report['extension_enabled'] = 'user_confirmed_not_programmatically_verified'
    input('请手动登录店小秘和速卖通，完成验证；打开目标商品详情页与店小秘采集箱。不要执行采集，按 Enter。')
    product_page = choose_page(context, '商品详情页')
    _, current_id = source_identity(product_page.url)
    if current_id != report['product_id']:
        raise ValueError('所选标签页不是目标速卖通商品')
    report['ui_candidates'] = ui_candidates(product_page)
    report['extension_runtime_seen'] = any(
        worker.url.startswith('chrome-extension://' + args.extension_id + '/')
        for worker in context.service_workers)
    report['runtime_note'] = 'worker absence does not prove disabled; popup/content scripts require manual inspection'
    print('可见采集词：', report['ui_candidates'])
    print('请手动检查扩展工具栏弹窗/页面入口。程序不会点击未知控件。')
    report['entry_observation'] = {
        '1': 'user_observed_detail_entry', '2': 'user_observed_list_batch_entry',
        '3': 'user_observed_both',
    }.get(input('观察到入口：1 详情采集，2 列表批量，3 两者，其他 未知：'), 'unknown')
    box = choose_page(context, '采集箱')
    input('请在采集箱搜索该商品的来源 ID，确认结果已加载；按 Enter 读取基线。')
    report['before'] = verify_visible(box, args.rows, report['product_id'])
    if report['before']['status'] == 'verified_present':
        report.update(status='skipped', reason='already_present_before_attempt')
        print('采集箱已存在此商品，不重复采集；请换一个未采集商品再诊断。')
        return
    if input('确认仅采集该一个商品，且基线搜索正确？输入 COLLECT 继续人工采集：') != 'COLLECT':
        report.update(status='manual_required', reason='manual_collection_not_authorized')
        return
    report['attempt_time'] = datetime.now(timezone.utc).isoformat()
    report['status'] = 'pending_verification'
    input('请仅通过官方插件人工采集这一个商品。遇验证码/异常弹窗就停止；完成或停止后按 Enter。')
    if input('插件操作是否正常完成？输入 YES；其他表示异常：') != 'YES':
        report.update(status='manual_required', reason='plugin_interaction_unconfirmed')
        return
    input('请手动刷新采集箱并按来源 ID 搜索，等待加载完成，按 Enter 核验。')
    report['after'] = verify_visible(box, args.rows, report['product_id'])
    report['status'] = report['after']['status']
    report['reason'] = ('single_product_present_after_manual_plugin_action_not_automation_validation'
                        if report['status'] == 'verified_present' else 'no_unique_match_keep_pending_do_not_retry')
    report['automation_feasibility'] = 'not_validated_manual_probe_only'


def main():
    parser = argparse.ArgumentParser(description='阶段 A：Windows Chrome 官方插件本地诊断（人工单商品采集）')
    parser.add_argument('--extension-id', required=True)
    parser.add_argument('--crx', type=Path, help='本地 dxm_crawl_2.8.88.crx；校验解包后首次需要人工加载')
    parser.add_argument('--product-url', required=True)
    parser.add_argument('--rows', default='table tbody tr', help='实际采集箱商品行 CSS 选择器')
    parser.add_argument('--endpoint', help='明确授权复用的本机 Chrome CDP 地址；不会读取或复制个人浏览器目录')
    parser.add_argument('--report', type=Path, default=Path('output/plugin-probe.json'))
    args = parser.parse_args()
    source, product_id = source_identity(args.product_url)
    if not product_id or urlsplit(source).scheme != 'https':
        parser.error('需要 https://www.aliexpress.com/item/数字.html 商品地址')
    if not EXTENSION_ID.fullmatch(args.extension_id):
        parser.error('无效扩展 ID')
    report = {'stage': 'A', 'status': 'manual_required', 'product_url': source,
              'product_id': product_id, 'extension_id': args.extension_id,
              'automation_feasibility': 'not_validated',
              'created_at': datetime.now(timezone.utc).isoformat()}
    process = None
    profile = None
    try:
        if args.crx:
            extension_path, metadata = prepare_extension(
                args.crx, args.extension_id, Path(__file__).parent / '.local-extensions')
            report['extension_package'] = metadata
            print('CRX 已校验并解包，未静默安装。')
            print('首次：在 chrome://extensions 启用开发者模式 → 加载已解压的扩展程序，选择：')
            print(extension_path)
        if args.endpoint:
            endpoint = validate_endpoint(args.endpoint)
        else:
            chrome = find_chrome()
            if not chrome:
                raise RuntimeError('Windows Chrome 未找到；请安装 Chrome 或提供已授权的本机 CDP endpoint')
            # A dedicated profile is deliberately NOT a copy of a personal profile.
            profile = (Path(__file__).parent / '.diagnostic-chrome').resolve()
            profile.mkdir(exist_ok=True)
            report['extension_files'] = inspect_extension(profile, args.extension_id)
            endpoint = 'http://127.0.0.1:9223'
            # Refuse attaching accidentally to an unrelated process occupying this port.
            import socket
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 9223))
            process = subprocess.Popen([str(chrome), '--user-data-dir=' + str(profile),
                                        '--remote-debugging-port=9223', '--remote-debugging-address=127.0.0.1',
                                        '--no-first-run', 'chrome://extensions/'])
            input('独立 Chrome 已启动。首次使用请从店小秘官网指向的官方来源安装扩展，再按 Enter 连接诊断。')
        with sync_playwright() as runtime:
            browser = runtime.chromium.connect_over_cdp(endpoint, timeout=15000)
            # Stop Playwright only; never browser.close() on an authorized reused browser.
            run_session(browser.contexts[0], args, report)
    except (Exception, KeyboardInterrupt) as error:
        # No raw exceptions/URLs/HTML: these may carry session credentials.
        report.update(status='manual_required', reason='diagnostic_interrupted_or_browser_unavailable',
                      error_type=type(error).__name__)
        print('诊断未完成：检查安装包是否为原始 2.8.88、扩展 ID、Chrome、端口、页面选择和 CSS；未知结果请先人工核验，不要重复采集。')
    finally:
        if profile is not None:
            report['extension_files'] = inspect_extension(profile, args.extension_id)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('本地报告：', args.report)
        if process:
            print('独立 Chrome 保持打开；完成后请手动关闭。会话由 Chrome 本地保存，工具不读取/复制凭据。')
    return 0 if report['status'] in {'verified_present', 'skipped'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
