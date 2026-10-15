import unittest
from pathlib import Path
from unittest.mock import patch
from open_chrome import open_existing_chrome


class OpenChromeTests(unittest.TestCase):
    @patch('open_chrome.subprocess.Popen')
    @patch('open_chrome.find_chrome', return_value=Path('chrome.exe'))
    def test_normal_profile_without_debugging_or_new_data_directory(self, find, launch):
        open_existing_chrome('https://www.aliexpress.com/item/123.html?tracking=test')
        self.assertEqual(launch.call_args.args[0], ['chrome.exe', 'https://www.aliexpress.com/item/123.html'])

    @patch('open_chrome.subprocess.Popen')
    @patch('open_chrome.find_chrome', return_value=Path('chrome.exe'))
    def test_explicit_existing_profile(self, find, launch):
        open_existing_chrome(profile='Profile 2')
        self.assertIn('--profile-directory=Profile 2', launch.call_args.args[0])

    @patch('open_chrome.subprocess.Popen')
    @patch('open_chrome.find_chrome', return_value=Path('chrome.exe'))
    def test_invalid_input_does_not_launch(self, find, launch):
        for profile in ['../Default', '--guest', 'C:\\Users\\test']:
            with self.assertRaises(ValueError):
                open_existing_chrome(profile=profile)
        with self.assertRaises(ValueError):
            open_existing_chrome('https://evil.test/item/123.html')
        launch.assert_not_called()

    @patch('open_chrome.find_chrome', return_value=None)
    def test_chrome_not_found(self, find):
        with self.assertRaises(RuntimeError):
            open_existing_chrome()
