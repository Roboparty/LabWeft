from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research_harness.research_tree_demo import create_research_tree_demo, FIXTURE
from research_harness.store import Store, HarnessError
from research_harness.reasoning import drift


class SavedResearchTreeTests(unittest.TestCase):
    def test_fast_replay_keeps_all_candidates_failures_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, patch('subprocess.Popen', side_effect=AssertionError('Replay must not execute programs')):
            result = create_research_tree_demo(Path(tmp) / 'demo')
            store = Store(result['workspace'])
            state = store.load()
            cells = [n for n in state['nodes'].values() if n['kind'] == 'cell']
            runs = [n for n in state['nodes'].values() if n['kind'] == 'run']
            self.assertEqual(37, len(cells))
            self.assertEqual(49, len(runs))
            self.assertEqual(4, sum(n['status'] == 'failed' for n in runs))
            self.assertTrue(all(n['attrs']['execution_during_demo_generation'] is False for n in runs))
            self.assertEqual([], drift(state))
            for n in state['nodes'].values():
                for ref in n.get('evidence', []):
                    store.read_blob(ref['sha256'])
            self.assertFalse(result['shinka_invoked'])
            self.assertEqual(0, result['new_cpu_evaluations'])
            self.assertIn('research-tree-svg', Path(result['output']).read_text(encoding='utf-8'))

    def test_repeated_generation_refreshes_view_without_rewriting_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'demo'
            first = create_research_tree_demo(root)
            before = Store(root).load()['last_hash']
            Path(first['output']).write_text('old renderer')
            second = create_research_tree_demo(root)
            self.assertTrue(second['existing'])
            self.assertEqual(before, Store(root).load()['last_hash'])
            self.assertIn('research-tree-svg', Path(second['output']).read_text(encoding='utf-8'))

    def test_existing_research_and_unrelated_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'real'
            Store(root).init('Real research')
            before = Store(root).load()
            with self.assertRaises(HarnessError):
                create_research_tree_demo(root)
            self.assertEqual(before, Store(root).load())
            folder = Path(tmp) / 'notes'; folder.mkdir(); (folder/'keep.txt').write_text('keep')
            with self.assertRaises(HarnessError):
                create_research_tree_demo(folder)
            self.assertEqual('keep', (folder/'keep.txt').read_text())

    def test_cli_generates_portable_fixture_without_local_machine_paths(self):
        raw = FIXTURE.read_text(encoding='utf-8')
        for value in ('D:\\\\embodied', 'C:\\\\Users', '/data/wqz', '73505'):
            self.assertNotIn(value, raw)
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(__file__).resolve().parents[1] / 'labweft.py'
            p = subprocess.run([sys.executable, str(cli), 'demo', str(Path(tmp)/'demo'), '--scenario', 'research-tree'],
                               capture_output=True, check=True)
            result = json.loads(p.stdout)
            self.assertEqual('saved_result_replay', result['mode'])
            self.assertEqual(37, result['candidates'])


if __name__ == '__main__':
    unittest.main()
