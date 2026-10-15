"""Business data paths; Chrome profiles and credentials are deliberately untouched."""
import json
from contextlib import closing
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
MARKER = '.dxm-migration.json'


def default_data_dir():
    return Path(r'E:\店小秘数据') if sys.platform == 'win32' else PROJECT / 'output'


def fingerprint(source):
    return {str(p.relative_to(source)): [p.stat().st_size, p.stat().st_mtime_ns]
            for p in source.rglob('*') if p.is_file()}


def ensure_data_dir(destination=None, source=None):
    destination = Path(destination) if destination is not None else default_data_dir()
    source = Path(source) if source is not None else PROJECT / 'output'
    if source.resolve() == destination.resolve():
        destination.mkdir(parents=True, exist_ok=True)
        return destination
    if sys.platform == 'win32' and not Path(destination.anchor).is_dir():
        raise OSError('数据盘不可用，请检查 E 盘或使用 --db/--output 指定已有磁盘。')
    if source.is_symlink() or (source.exists() and not source.is_dir()):
        raise OSError('旧 output 不是普通目录，停止迁移。')
    if source.exists() and source.is_dir() and any(source.iterdir()):
        before = fingerprint(source)
        marker = destination / MARKER
        if marker.exists():
            previous = json.loads(marker.read_text(encoding='utf-8'))
            if previous.get('source') != str(source.resolve()) or previous.get('files') != before:
                raise OSError('旧 output 数据在迁移后发生变化，停止以避免遗漏记录；请先停止旧版程序并人工合并数据。')
        else:
            # Never silently replace an existing database with a different history.
            if destination.exists() and any(destination.iterdir()):
                raise OSError('E 盘目标目录与旧 output 同时有数据，停止迁移；请先人工核对，不能覆盖合并。')
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix='.dxm-migrate-', dir=destination.parent))
            try:
                for path in source.rglob('*'):
                    if path.is_symlink():
                        raise OSError('旧数据含符号链接，停止迁移。')
                    target = staging / path.relative_to(source)
                    if path.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif path.is_file():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        # SQLite backup includes committed WAL contents. Do not copy sidecars.
                        if path.name.endswith(('-wal', '-shm', '-journal')):
                            continue
                        if path.suffix == '.sqlite3':
                            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as old:
                                with closing(sqlite3.connect(target)) as new:
                                    old.backup(new)
                                    if new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                                        raise OSError('数据库完整性检查失败，停止迁移。')
                        else:
                            shutil.copy2(path, target)
                if fingerprint(source) != before:
                    raise OSError('迁移时旧数据正在变化；请关闭全部旧程序再重试。')
                (staging / MARKER).write_text(json.dumps({'source': str(source.resolve()), 'files': before}, ensure_ascii=False), encoding='utf-8')
                if destination.exists():
                    # An empty pre-existing directory is safe; never remove its contents.
                    destination.rmdir()
                staging.rename(destination)
                print('旧 output 数据已复制到新数据目录，原文件保留备份：', destination)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def resolve_default_file(explicit, filename):
    if explicit is not None:
        explicit = Path(explicit)
        explicit.parent.mkdir(parents=True, exist_ok=True)
        return explicit
    return ensure_data_dir() / filename


if __name__ == '__main__':
    try:
        print('业务数据目录：', ensure_data_dir())
    except (OSError, ValueError, sqlite3.Error) as error:
        print('数据目录准备失败：', error)
        raise SystemExit(1)
