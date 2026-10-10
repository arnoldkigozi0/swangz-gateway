"""The optional staging entrypoint must refuse a live database before migrations."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

spec=importlib.util.spec_from_file_location('hub_staging',Path(__file__).resolve().parents[1]/'deploy/railway/staging.py')
staging=importlib.util.module_from_spec(spec);spec.loader.exec_module(staging)

class StagingGuards(unittest.TestCase):
    def test_existing_unmarked_database_is_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/'gateway.db'
            with sqlite3.connect(file) as db:
                db.execute('CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)');db.execute("INSERT INTO settings VALUES('production','1')")
            before=file.read_bytes()
            with mock.patch.dict(os.environ,{'GATEWAY_STAGING':'synthetic','GATEWAY_DATA':root,'GATEWAY_PUBLIC_URL':'https://fixture.up.railway.app'},clear=True):
                with self.assertRaisesRegex(ValueError,'before opening or migrating'):staging.settings()
            self.assertEqual(file.read_bytes(),before)

    def test_staging_has_no_production_hostname_or_provider_shortcut(self):
        with tempfile.TemporaryDirectory() as root:
            env={'GATEWAY_STAGING':'synthetic','GATEWAY_DATA':root,'GATEWAY_PUBLIC_URL':'https://fixture.up.railway.app','PORT':'12345'}
            with mock.patch.dict(os.environ,env,clear=True):
                cfg=staging.settings();self.assertEqual((cfg.host,cfg.port,cfg.bootstrap_admin),('0.0.0.0',12345,''))
                os.environ['OPENAI_API_KEY']='synthetic-forbidden-key'
                with self.assertRaisesRegex(ValueError,'refuses production'):staging.settings()
                del os.environ['OPENAI_API_KEY'];os.environ['GATEWAY_PUBLIC_URL']='https://ai.swangzavenue.com'
                with self.assertRaisesRegex(ValueError,'production hosts are refused'):staging.settings()

class ImportArtifactGuards(unittest.TestCase):
    def test_existing_summary_refuses_apply_before_database_access(self):
        from gateway import hub_import
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/'existing.json';file.write_text('prior reconciliation')
            args=['hub_import','--database',str(Path(root)/'live.db'),'--file',str(Path(root)/'source.json'),'--apply','--backup',str(Path(root)/'backup.db'),'--summary',str(file)]
            with mock.patch('sys.argv',args),mock.patch.object(hub_import,'backup') as backup,mock.patch.object(hub_import,'DB') as db:
                with self.assertRaises(FileExistsError):hub_import.main()
            backup.assert_not_called();db.assert_not_called();self.assertEqual(file.read_text(),'prior reconciliation')
