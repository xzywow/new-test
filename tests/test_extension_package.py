import base64
import hashlib
import io
import json
import tempfile
import struct
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from extension_package import archive_entries, package_contents, prepare_extension


def fixture():
    public_key = b'test-public-key-not-real-extension'
    identity = ''.join(chr(ord('a') + int(c, 16)) for c in hashlib.sha256(public_key).hexdigest()[:32])
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({'key': base64.b64encode(public_key).decode(),
                                                    'version': '2.8.88', 'manifest_version': 3}))
        archive.writestr('script.js', '/* synthetic fixture */')
    return b'Cr24' + struct.pack('<II', 3, 0) + payload.getvalue(), identity


class PackageTests(unittest.TestCase):
    def test_unsafe_archive_paths_rejected(self):
        for name in ['../outside', '/absolute', 'C:/outside', 'folder\\outside', 'NUL.txt', 'file.']:
            with self.subTest(name=name):
                payload = io.BytesIO()
                with zipfile.ZipFile(payload, 'w') as archive:
                    archive.writestr(name, 'bad')
                with zipfile.ZipFile(io.BytesIO(payload.getvalue())) as archive:
                    with self.assertRaises(ValueError):
                        archive_entries(archive)

    def test_unknown_package_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'unknown.crx'
            path.write_bytes(b'unknown')
            with self.assertRaisesRegex(ValueError, '校验和'):
                package_contents(path, 'a' * 32)

    def test_prepare_repeat_and_modified_code_rejected(self):
        # SHA/identity pins replaced ONLY for a synthetic fixture in unit tests.
        raw, identity = fixture()
        with tempfile.TemporaryDirectory() as tmp, patch('extension_package.PACKAGE_SHA256', hashlib.sha256(raw).hexdigest()), patch('extension_package.PACKAGE_ID', identity):
            path = Path(tmp) / 'fixture.crx'
            path.write_bytes(raw)
            target, metadata = prepare_extension(path, identity, Path(tmp) / 'extensions')
            self.assertEqual(metadata['installation'], 'manual_load_unpacked_required')
            self.assertTrue((target / 'manifest.json').is_file())
            self.assertEqual(prepare_extension(path, identity, Path(tmp) / 'extensions')[0], target)
            (target / 'script.js').write_text('altered')
            with self.assertRaises(ValueError):
                prepare_extension(path, identity, Path(tmp) / 'extensions')

    def test_wrong_identity_rejected(self):
        raw, identity = fixture()
        with tempfile.TemporaryDirectory() as tmp, patch('extension_package.PACKAGE_SHA256', hashlib.sha256(raw).hexdigest()), patch('extension_package.PACKAGE_ID', identity):
            path = Path(tmp) / 'fixture.crx'
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, '身份'):
                package_contents(path, 'a' * 32)
