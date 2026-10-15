import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, ANY
from desktop_collect import AttemptLedger, WindowsChrome, StopOperation, exact_product, inspect_texts


def control(name, kind='Button'):
    result = Mock()
    result.window_text.return_value = name
    result.element_info.control_type = kind
    result.element_info.runtime_id = [1, 2, 3]
    result.is_enabled.return_value = True
    result.rectangle.return_value = Mock(left=10, top=20, width=lambda: 100, height=lambda: 30)
    return result


class DesktopTests(unittest.TestCase):
    def test_exact_source_and_blockers(self):
        self.assertTrue(exact_product('www.aliexpress.com/item/123.html', '123'))
        self.assertFalse(exact_product('https://aliexpress.com.evil.test/item/123.html', '123'))
        self.assertFalse(exact_product('https://www.aliexpress.com/item/1234.html', '123'))
        self.assertTrue(inspect_texts(['采集成功，可继续采集']))
        with self.assertRaises(StopOperation):
            inspect_texts(['验证码'])

    def test_crash_or_repeat_never_reclicks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'attempts.sqlite3'
            ledger = AttemptLedger(path)
            ledger.claim('123')
            ledger.close()
            ledger = AttemptLedger(path)
            with self.assertRaises(StopOperation):
                ledger.claim('123')
            ledger.status('123', 'verified_present')
            with self.assertRaises(StopOperation):
                ledger.claim('123')
            ledger.close()

    def make_chrome(self, candidates, url='https://www.aliexpress.com/item/123.html', texts=None):
        chrome = object.__new__(WindowsChrome)
        chrome.snapshot = Mock(return_value=(Mock(handle=42), candidates, url, texts or ['采集到店小秘']))
        chrome.desktop = Mock()
        chrome.win32gui = Mock()
        chrome.win32gui.GetForegroundWindow.return_value = 42
        return chrome

    def test_one_click_after_live_hit_check(self):
        button = control('开始采集')
        chrome = self.make_chrome([button])
        chrome.desktop.from_point.return_value = button
        chrome.click_once('123')
        button.click_input.assert_called_once_with()

    def test_duplicate_wrong_page_stale_success_and_overlay_stop(self):
        button = control('开始采集')
        scenarios = [self.make_chrome([button, button]),
                     self.make_chrome([button], url='https://example.com/'),
                     self.make_chrome([button], texts=['采集到店小秘', '采集成功']),
                     self.make_chrome([button])]
        scenarios[-1].desktop.from_point.return_value = control('overlay')
        scenarios[-1].desktop.from_point.return_value.element_info.runtime_id = [99]
        for chrome in scenarios:
            with self.assertRaises(StopOperation):
                chrome.click_once('123')
        button.click_input.assert_not_called()

    def test_source_verification_not_just_success_toast(self):
        field = control('', 'Edit')
        field.get_value.return_value = 'https://www.aliexpress.com/item/123.html'
        chrome = self.make_chrome([field], url='https://www.dianxiaomi.com/edit', texts=['来源URL：'])
        self.assertTrue(chrome.verify_source('123'))
        self.assertFalse(chrome.verify_source('456'))
        chrome.snapshot.return_value = (Mock(), [field], 'https://example.com/', ['来源URL：'])
        with self.assertRaises(StopOperation):
            chrome.verify_source('123')

    def test_native_address_fallback_and_page_field_rejection(self):
        chrome = object.__new__(WindowsChrome)
        root = Mock()
        root.element_info.runtime_id = [1]
        root.element_info.control_type = 'Window'
        toolbar = Mock()
        toolbar.element_info.runtime_id = [2]
        toolbar.element_info.control_type = 'ToolBar'
        toolbar.parent.return_value = root
        address = control('localized unknown label', 'Edit')
        address.element_info.runtime_id = [3]
        address.parent.return_value = toolbar
        address.iface_value.CurrentValue = 'www.dianxiaomi.com/edit'
        document = Mock()
        document.element_info.runtime_id = [4]
        document.element_info.control_type = 'Document'
        spoof = control('Address and search bar', 'Edit')
        spoof.element_info.runtime_id = [5]
        spoof.parent.return_value = document
        spoof.iface_value.CurrentValue = 'www.aliexpress.com/item/123.html'
        self.assertEqual(chrome.address(root, [address, spoof]), 'https://www.dianxiaomi.com/edit')
        with self.assertRaises(StopOperation):
            chrome.address(root, [spoof])

    def test_skip_source_verification_keeps_unverified(self):
        import sys
        from desktop_collect import main
        with tempfile.TemporaryDirectory() as tmp, patch('desktop_collect.WindowsChrome') as cls, patch('builtins.input', side_effect=AssertionError('不得要求输入确认')) as prompt, patch('desktop_collect.time.sleep') as sleep:
            path = Path(tmp) / 'attempts.sqlite3'
            with patch.object(sys, 'argv', ['desktop_collect.py', '--product-url', 'https://www.aliexpress.com/item/123.html', '--skip-source-verification', '--db', str(path)]):
                self.assertEqual(main(), 0)
            prompt.assert_not_called()
            sleep.assert_called_once_with(5)
            cls.return_value.click_once.assert_called_once_with('123', before_click=ANY)
            cls.return_value.verify_source.assert_not_called()
            ledger = AttemptLedger(path)
            self.assertEqual(ledger.db.execute('SELECT status FROM attempts').fetchone()[0], 'plugin_success_unverified')
            with self.assertRaises(StopOperation):
                ledger.claim('123')
            ledger.close()

    def test_preflight_failure_does_not_reserve_attempt(self):
        button = control('开始采集')
        chrome = self.make_chrome([button], url='https://example.com/')
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / 'db.sqlite3')
            with self.assertRaises(StopOperation):
                chrome.click_once('123', before_click=lambda: ledger.claim('123'))
            self.assertIsNone(ledger.db.execute('SELECT status FROM attempts').fetchone())
            button.click_input.assert_not_called()
            ledger.close()

    def test_reservation_precedes_click(self):
        button = control('开始采集')
        chrome = self.make_chrome([button])
        chrome.desktop.from_point.return_value = button
        events = []
        button.click_input.side_effect = lambda: events.append('click')
        chrome.click_once('123', before_click=lambda: events.append('reserve'))
        self.assertEqual(events, ['reserve', 'click'])

    def test_only_explicit_no_click_attestation_can_release_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AttemptLedger(Path(tmp) / 'db.sqlite3')
            ledger.claim('123')
            ledger.clear_confirmed_no_click('123')
            ledger.claim('123')
            ledger.status('123', 'plugin_success_unverified')
            with self.assertRaises(StopOperation):
                ledger.clear_confirmed_no_click('123')
            ledger.status('123', 'verified_present')
            with self.assertRaises(StopOperation):
                ledger.clear_confirmed_no_click('123')
            ledger.close()

    def test_duplicate_button_skips_without_click_or_reservation(self):
        button = control('重复采集')
        chrome = self.make_chrome([button])
        reserve = Mock()
        self.assertEqual(chrome.click_once('123', before_click=reserve), 'duplicate')
        button.click_input.assert_not_called()
        reserve.assert_not_called()
        chrome.snapshot.return_value = (Mock(), [button], 'https://example.com/', ['采集到店小秘'])
        with self.assertRaises(StopOperation):
            chrome.click_once('123', before_click=reserve)

    def test_duplicate_after_attempt_is_distinct_from_success(self):
        chrome = self.make_chrome([control('重复采集')])
        self.assertEqual(chrome.wait_success('123', 1), 'duplicate')

    def test_duplicate_cli_exits_without_waiting_or_source_check(self):
        import sys
        from desktop_collect import main
        with tempfile.TemporaryDirectory() as tmp, patch('desktop_collect.WindowsChrome') as cls, patch('builtins.input', side_effect=AssertionError('不得要求核验')), patch('desktop_collect.time.sleep'):
            cls.return_value.click_once.return_value = 'duplicate'
            path = Path(tmp) / 'db.sqlite3'
            with patch.object(sys, 'argv', ['desktop_collect.py', '--product-url', 'https://www.aliexpress.com/item/123.html', '--db', str(path)]):
                self.assertEqual(main(), 0)
            cls.return_value.wait_success.assert_not_called()
            cls.return_value.verify_source.assert_not_called()
            ledger = AttemptLedger(path)
            self.assertEqual(ledger.db.execute('SELECT status FROM attempts').fetchone()[0], 'skipped_duplicate')
            ledger.status('123', 'verified_present')
            ledger.note_duplicate('123')
            self.assertEqual(ledger.db.execute('SELECT status FROM attempts').fetchone()[0], 'verified_present')
            ledger.close()

    def test_text_only_plugin_label_can_be_clicked_with_hit_check(self):
        text = control('开始采集', 'Text')
        chrome = self.make_chrome([text])
        chrome.desktop.from_point.return_value = text
        self.assertEqual(chrome.click_once('123'), 'clicked')
        text.click_input.assert_called_once()
        duplicate = control('重复采集', 'Text')
        chrome = self.make_chrome([duplicate])
        self.assertEqual(chrome.click_once('123'), 'duplicate')
        duplicate.click_input.assert_not_called()

    def test_button_is_preferred_to_its_text_label(self):
        button, text = control('开始采集'), control('开始采集', 'Text')
        chrome = self.make_chrome([button, text])
        chrome.desktop.from_point.return_value = button
        chrome.click_once('123')
        button.click_input.assert_called_once()
        text.click_input.assert_not_called()

    def test_diagnostic_only_reports_fixed_plugin_labels(self):
        chrome = object.__new__(WindowsChrome)
        root = Mock()
        chrome.foreground = Mock(return_value=root)
        chrome.controls = Mock(return_value=[control('开始采集', 'Text'), control('private account text', 'Text')])
        chrome.address = Mock(return_value='https://www.aliexpress.com/item/123.html?secret=hidden')
        result = chrome.diagnose()
        self.assertEqual(result['diagnostic_version'], 2)
        self.assertEqual(result['plugin_controls'], [{'label': '开始采集', 'type': 'Text', 'enabled': True}])
        self.assertNotIn('secret', str(result))
        self.assertNotIn('private account', str(result))
