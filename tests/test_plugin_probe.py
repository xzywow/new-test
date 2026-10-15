import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from playwright.sync_api import sync_playwright
from chrome_diagnostics import inspect_extension, validate_endpoint, find_chrome
from plugin_probe import exact_source_matches, verify_visible, ui_candidates, run_session


class ProbeTests(unittest.TestCase):
    def test_endpoint_rejects_remote_or_credentials(self):
        for endpoint in ['https://127.0.0.1:9222', 'http://evil.test:9222',
                         'http://user:password@localhost:9222', 'http://localhost:9222/?token=secret']:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_endpoint(endpoint)
        self.assertEqual(validate_endpoint('http://127.0.0.1:9223'), 'http://127.0.0.1:9223')

    def test_metadata_not_proof_of_enabled_or_official(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Default/Extensions' / ('a' * 32) / '1.0'
            root.mkdir(parents=True)
            (root / 'manifest.json').write_text(json.dumps({'version': '1.0', 'manifest_version': 3}))
            result = inspect_extension(tmp, 'a' * 32)
            self.assertTrue(result['installed_files_found'])
            self.assertEqual(result['enabled'], 'requires_manual_check')
            self.assertIn('requires_user_check', result['official_identity'])
            self.assertFalse(inspect_extension(tmp, 'b' * 32)['installed_files_found'])

    def test_windows_chrome_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / 'Google/Chrome/Application/chrome.exe'
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch('chrome_diagnostics.sys.platform', 'win32'), patch.dict(os.environ, {'PROGRAMFILES': tmp}):
                self.assertEqual(find_chrome(), executable)

    def test_match_requires_exact_source_not_count_or_internal_id(self):
        self.assertEqual(exact_source_matches([['https://www.aliexpress.com/item/123.html?x=y']], '123'), 1)
        for url in ['https://evil.test/item/123.html', 'https://aliexpress.com.evil.test/item/123.html',
                    'https://www.aliexpress.com/item/1234.html', 'https://www.dianxiaomi.com/?id=123']:
            self.assertEqual(exact_source_matches([[url]], '123'), 0)

    def test_existing_product_never_prompts_collection(self):
        context = Mock(service_workers=[])
        product = Mock(url='https://www.aliexpress.com/item/123.html')
        args = Mock(extension_id='a' * 32, rows='tr')
        report = {'product_id': '123'}
        replies = ['', 'YES', '', '1', '']
        with patch('builtins.input', side_effect=replies), patch('plugin_probe.choose_page', side_effect=[product, Mock()]), patch('plugin_probe.ui_candidates', return_value=[]), patch('plugin_probe.verify_visible', return_value={'status': 'verified_present'}):
            run_session(context, args, report)
        self.assertEqual(report['status'], 'skipped')
        self.assertNotIn('attempt_time', report)

    def test_unmatched_after_manual_action_stays_pending(self):
        context = Mock(service_workers=[])
        product = Mock(url='https://www.aliexpress.com/item/123.html')
        args = Mock(extension_id='a' * 32, rows='tr')
        report = {'product_id': '123'}
        replies = ['', 'YES', '', '1', '', 'COLLECT', '', 'YES', '']
        with patch('builtins.input', side_effect=replies), patch('plugin_probe.choose_page', side_effect=[product, Mock()]), patch('plugin_probe.ui_candidates', return_value=[]), patch('plugin_probe.verify_visible', return_value={'status': 'pending_verification'}):
            run_session(context, args, report)
        self.assertEqual(report['status'], 'pending_verification')
        self.assertIn('attempt_time', report)

    def test_local_browser_visible_verification_and_candidates(self):
        # Synthetic local HTML, NOT the real plugin or Dianxiaomi website.
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True, executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH'))
            try:
                page = browser.new_page()
                page.route('https://www.dianxiaomi.com/**', lambda r: r.fulfill(body='''
                    <button>店小秘采集 secret-account-name</button>
                    <table><tbody><tr><td><a href="https://www.aliexpress.com/item/123.html">来源</a></td></tr>
                    <tr style="display:none"><td><a href="https://www.aliexpress.com/item/456.html">隐藏</a></td></tr>
                    </tbody></table>''', content_type='text/html'))
                page.goto('https://www.dianxiaomi.com/mock')
                self.assertEqual(verify_visible(page, 'tbody tr', '123')['status'], 'verified_present')
                self.assertEqual(verify_visible(page, 'tbody tr', '456')['status'], 'pending_verification')
                self.assertEqual(verify_visible(page, '.missing', '123')['status'], 'pending_verification')
                self.assertNotIn('secret-account-name', str(ui_candidates(page)))
                page.goto('about:blank')
                with self.assertRaises(ValueError):
                    verify_visible(page, 'tr', '123')
            finally:
                browser.close()
