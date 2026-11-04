"""Offline operator recipes: no remote execution or motor control in tests."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
import zipfile
from PyQt5 import QtWidgets as Q
from nino_pi.collection_recipes import RECIPES, TASK_RECIPES, render_recipe
from nino_pi.collection_deploy import INSTALL
from nino_pi.command_panel import CommandsDialog


class RecipeTests(unittest.TestCase):
    def test_every_pending_task_has_recipe_and_commands_parse_as_shell(self):
        self.assertEqual(set(TASK_RECIPES),{f'T{i:02}' for i in range(1,25)})
        for key in RECIPES:
            recipe=render_recipe(key,key="/tmp/key with ' spaces and $(not_run)")
            for step in recipe['steps']:
                subprocess.run(['bash','-n'],input=step['command'],text=True,check=True)
                self.assertNotIn('wheel_startup_verification_20261102_v1',step['command'])
                self.assertNotIn('clear_floor_repeatability_',step['command'])
        diag=render_recipe('diagnostic')
        self.assertEqual(sum(' run-trial' in shlex.split(s['command'])[-1] for s in diag['steps']),1)

    def test_host_rejects_options_and_shell_injection(self):
        for host in ('-oProxyCommand=evil','d@pi; touch /tmp/x','d@pi\nexit','d@$(evil)'):
            with self.subTest(host=host), self.assertRaises(ValueError):render_recipe('diagnostic',host=host)

    def test_install_is_copy_only_idempotent_and_does_not_reset_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as z:z.writestr('hello.txt','prepared')
            import hashlib
            blob=data.getvalue();digest=hashlib.sha256(blob).hexdigest()
            env=dict(os.environ,HOME=folder)
            command=[sys.executable,'-c',INSTALL,digest,'test_runtime']
            subprocess.run(command,input=blob,env=env,check=True,stdout=subprocess.PIPE)
            root=Path(folder)/'nino_runtime/test_runtime'
            ledger=root/'ledger.json';ledger.write_text('{"status":"stopped","attempts":[1]}')
            subprocess.run(command,input=blob,env=env,check=True,stdout=subprocess.PIPE)
            self.assertEqual(ledger.read_text(),'{"status":"stopped","attempts":[1]}')

    def test_runtime_is_prepared_with_unchanged_profile_and_no_historical_state(self):
        bundle=Path(__file__).parents[1]/'nino_pi/collection_runtime.zip'
        with zipfile.ZipFile(bundle) as z:
            names=set(z.namelist())
            self.assertFalse(names & {'ledger.json','pilot_contract.json','readiness.json','active_session.json'})
            c=json.loads(z.read('contract.template.json'))
            self.assertEqual(c['maximum_attempts'],0);self.assertFalse(c['motion_budget_released'])
            p=json.loads(z.read('motion_profile.template.json'))
            self.assertEqual([p[k] for k in ('max_forward_m_s','reference_acceleration_m_s2','requested_forward_duration_s','recording_duration_s')],[.05,.1,2.,60])
            self.assertNotIn(b'.publish(',z.read('session_cli.py'))

    def test_used_diagnostic_cannot_be_reopened_and_latest_session_is_unambiguous(self):
        bundle=Path(__file__).parents[1]/'nino_pi/collection_runtime.zip'
        with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(bundle) as z:
            root=Path(folder);z.extractall(root)
            spec=importlib.util.spec_from_file_location('diagnostic_session_cli_test',root/'session_cli.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            sys.path.insert(0,str(root))
            try:
                ready=dict(software_ready=True,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),endpoint_identity={})
                mod.freeze_diagnostic(ready)
                contract=(root/'pilot_contract.json').read_bytes()
                ledger=dict(contract_sha256=mod.hashlib.sha256(contract).hexdigest(),status='stopped',attempts=[{}])
                mod.save(root/'ledger.json',ledger)
                with self.assertRaises(RuntimeError):mod.freeze_diagnostic(ready)
                self.assertEqual((root/'pilot_contract.json').read_bytes(),contract)
                self.assertEqual(json.loads((root/'ledger.json').read_text()),ledger)
                mod.save(root/'last_session.json',dict(output='/tmp/new_stationary',closed=True))
                self.assertEqual(mod.latest_closed(),Path('/tmp/new_stationary'))
                mod.save(root/'last_session.json',dict(output=None,closed=False))
                with self.assertRaises(RuntimeError):mod.latest_closed()
            finally:
                sys.path.remove(str(root));sys.modules.pop('pilot_state',None)


class CommandGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=Q.QApplication.instance() or Q.QApplication([])

    def test_copy_uses_current_ip_and_only_selected_terminal(self):
        d=CommandsDialog('diagnostic',connection=lambda:dict(host='d@192.168.0.120',key='/tmp/test key'))
        d.steps.setCurrentRow(4)
        d.copy_selected()
        copied=self.app.clipboard().text()
        self.assertIn('192.168.0.120',copied)
        self.assertIn('run-trial',copied)
        self.assertNotIn('record-diagnostic',copied)
        self.assertIn('ENABLE',d.where.text())
        d.close()

    def test_future_recipe_never_offers_motion_and_bad_ip_disables_copy(self):
        d=CommandsDialog('repeatability')
        self.assertTrue(all('run-trial' not in s['command'] for s in d.recipe['steps']))
        d.connection=lambda:dict(host='bad host')
        d.refresh();self.assertFalse(d.copy.isEnabled());self.assertFalse(d.copy_all.isEnabled());d.close()
