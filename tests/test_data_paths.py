import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from data_paths import default_data_dir, ensure_data_dir, resolve_default_file


class DataPathTests(unittest.TestCase):
    def test_windows_default(self):
        with patch('data_paths.sys.platform', 'win32'):
            self.assertEqual(str(default_data_dir()), r'D:\店小秘数据')

    def test_migration_preserves_records_and_repeat_keeps_new_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'old', Path(tmp) / 'new'
            source.mkdir()
            connection = sqlite3.connect(source / 'desktop-attempts.sqlite3')
            connection.execute('CREATE TABLE attempts(id TEXT)')
            connection.execute("INSERT INTO attempts VALUES ('old')")
            connection.commit()
            connection.close()
            (source / 'report.json').write_text('{}')
            ensure_data_dir(target, source)
            self.assertTrue((source / 'desktop-attempts.sqlite3').exists())
            connection = sqlite3.connect(target / 'desktop-attempts.sqlite3')
            self.assertEqual(connection.execute('SELECT id FROM attempts').fetchone()[0], 'old')
            connection.execute("INSERT INTO attempts VALUES ('new')")
            connection.commit()
            connection.close()
            ensure_data_dir(target, source)
            connection = sqlite3.connect(target / 'desktop-attempts.sqlite3')
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 2)
            connection.close()
            (source / 'later.txt').write_text('old process still writing')
            with self.assertRaises(OSError):
                ensure_data_dir(target, source)

    def test_conflict_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'old', Path(tmp) / 'new'
            source.mkdir()
            target.mkdir()
            (source / 'data').write_text('old')
            (target / 'data').write_text('new')
            with self.assertRaises(OSError):
                ensure_data_dir(target, source)
            self.assertEqual((target / 'data').read_text(), 'new')

    def test_explicit_override_creates_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'custom' / 'db.sqlite3'
            self.assertEqual(resolve_default_file(path, 'ignored'), path)
            self.assertTrue(path.parent.is_dir())
