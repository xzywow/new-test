"""Prepare the exact user-supplied CRX locally; never claim Chrome installed it."""
import base64
import hashlib
import io
import json
import re
import shutil
import stat
import struct
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PACKAGE_SHA256 = 'd76762adb53085d44f75e53e5b54ff0db769211942521889d30583ca44e6c6ac'
PACKAGE_ID = 'ioadaikpljilagoddljnamloiebcoopb'


def archive_entries(archive):
    entries = archive.infolist()
    if len(entries) > 10000 or sum(i.file_size for i in entries) > 100 * 1024 * 1024:
        raise ValueError('扩展解包大小超出限制')
    names = set()
    for entry in entries:
        path = PurePosixPath(entry.filename)
        parts = path.parts
        if (not parts or path.is_absolute() or '\\' in entry.filename
                or any(p in {'.', '..'} or ':' in p or p.endswith((' ', '.'))
                       or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I)
                       for p in parts)
                or stat.S_ISLNK(entry.external_attr >> 16)):
            raise ValueError('扩展包包含不安全路径')
        normalized = str(path).lower()
        if normalized in names:
            raise ValueError('扩展包包含重名文件')
        names.add(normalized)
    return entries


def package_contents(path, expected_id):
    path = Path(path)
    if path.stat().st_size > 30 * 1024 * 1024:
        raise ValueError('扩展包过大')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PACKAGE_SHA256:
        raise ValueError('安装包与已检查的 2.8.88 文件校验和不一致；停止，不自动信任其他包')
    if len(raw) < 12 or raw[:4] != b'Cr24':
        raise ValueError('不是 CRX 安装包')
    version, header_size = struct.unpack_from('<II', raw, 4)
    if version != 3 or 12 + header_size >= len(raw):
        raise ValueError('不支持的 CRX 格式')
    archive = zipfile.ZipFile(io.BytesIO(raw[12 + header_size:]))
    try:
        archive_entries(archive)
        manifest = json.loads(archive.read('manifest.json'))
        key = base64.b64decode(manifest['key'], validate=True)
        identity = ''.join(chr(ord('a') + int(c, 16)) for c in hashlib.sha256(key).hexdigest()[:32])
        if identity != expected_id or identity != PACKAGE_ID or manifest.get('version') != '2.8.88' or manifest.get('manifest_version') != 3:
            raise ValueError('扩展身份或版本不匹配')
        return archive, {'extension_id': identity, 'version': manifest['version'],
                         'manifest_version': manifest['manifest_version'], 'sha256': digest,
                         'integrity': 'exact_uploaded_file_sha256_match_not_official_origin_attestation',
                         'installation': 'manual_load_unpacked_required'}
    except BaseException:
        archive.close()
        raise


def prepare_extension(path, expected_id, destination):
    archive, metadata = package_contents(path, expected_id)
    destination = Path(destination).absolute()
    try:
        if any(p.is_symlink() for p in [destination, *destination.parents]):
            raise ValueError('扩展目录不能经过符号链接')
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / metadata['sha256']
        if target.exists():
            # Never silently reuse altered unpacked executable code.
            if target.is_symlink() or not target.is_dir():
                raise ValueError('已有扩展目录不安全')
            expected = set()
            for entry in archive.infolist():
                if not entry.is_dir():
                    name = target / entry.filename
                    expected.add(name)
                    if any(p.is_symlink() for p in [name, *name.parents]) or not name.is_file() or name.read_bytes() != archive.read(entry):
                        raise ValueError('已解包文件发生变化；请移走该目录再重试')
            actual = set()
            for name in target.rglob('*'):
                if name.is_symlink():
                    raise ValueError('已解包目录包含符号链接')
                if name.is_file():
                    actual.add(name)
            if actual != expected:
                raise ValueError('已解包目录含额外文件；请移走该目录再重试')
        else:
            temporary = Path(tempfile.mkdtemp(prefix='prepare-', dir=destination))
            try:
                archive.extractall(temporary)
                temporary.rename(target)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        return target, metadata
    finally:
        archive.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='校验并解包已提供的店小秘 2.8.88 CRX（不静默安装）')
    parser.add_argument('--crx', type=Path, required=True)
    args = parser.parse_args()
    try:
        target, metadata = prepare_extension(args.crx, PACKAGE_ID, Path(__file__).parent / '.local-extensions')
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print('准备失败：', str(error))
        return 1
    print('已校验并解包，尚未安装到 Chrome。')
    print('在独立 Chrome 的 chrome://extensions 打开开发者模式，点击“加载已解压的扩展程序”，选择：')
    print(target)
    print('扩展 ID：', metadata['extension_id'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
