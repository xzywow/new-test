"""Local metadata only. Never reads Cookies, Login Data or Chrome Preferences."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

EXTENSION_ID = re.compile(r'^[a-p]{32}$')


def find_chrome():
    if sys.platform != 'win32':
        return None
    for base in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        candidate = Path(os.environ.get(base, '')) / 'Google/Chrome/Application/chrome.exe'
        if candidate.is_file():
            return candidate
    return None


def validate_endpoint(endpoint):
    parsed = urlsplit(endpoint)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'}
            or not parsed.port or parsed.username or parsed.password
            or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
        raise ValueError('只允许本机 http://127.0.0.1:端口 CDP 地址')
    return endpoint


def inspect_extension(profile, extension_id):
    if not EXTENSION_ID.fullmatch(extension_id):
        raise ValueError('扩展 ID 应为 chrome://extensions 中的 32 位 a-p 字母')
    versions = []
    root = Path(profile) / 'Default' / 'Extensions' / extension_id
    if root.is_dir():
        for manifest in sorted(root.glob('*/manifest.json')):
            try:
                data = json.loads(manifest.read_text(encoding='utf-8'))
                versions.append({'version': str(data.get('version', 'unknown')),
                                 'manifest_version': data.get('manifest_version')})
            except (OSError, ValueError):
                versions.append({'error': 'manifest_unreadable'})
    return {'extension_id': extension_id, 'installed_files_found': bool(versions),
            'versions': versions, 'enabled': 'requires_manual_check',
            'official_identity': 'requires_user_check_against_official_install_source'}
