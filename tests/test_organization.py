import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from research_harness.organization import organization
from research_harness.scan import node
from research_harness.server import export_html, presentation
from research_harness.store import Store


class OrganizationTests(unittest.TestCase):
    def fixture(self):
        nodes = {'study': {'id': 'study', 'kind': 'module', 'parent_id': 'project', 'attrs': {}}}
        for i in range(6):
            nodes[f'c{i}'] = {'id': f'c{i}', 'kind': 'cell', 'parent_id': 'study', 'attrs': {}}
            nodes[f'r{i}'] = {'id': f'r{i}', 'kind': 'run', 'parent_id': f'c{i}', 'attrs': {}}
        return {'nodes': nodes, 'edges': {}}

    def test_flat_list_is_readonly_review_hint(self):
        state = self.fixture(); before = copy.deepcopy(state)
        report = organization(state)
        self.assertEqual({w['code'] for w in report['warnings']}, {'missing_study_synthesis', 'unexplained_condition_list'})
        self.assertEqual(state, before)

    def test_independent_design_needs_no_invented_lineage(self):
        state = self.fixture()
        state['nodes']['study']['attrs'] = {'design': {'factor': 'independent conditions'}, 'study_summary': {'en': {'intro': 'Independent design'}}}
        self.assertFalse(organization(state)['needs_review'])

    def test_run_lineage_counts_as_recorded_comparison(self):
        state = self.fixture()
        state['edges']['edge'] = {'source': 'r1', 'target': 'r0', 'relation': 'derived_from'}
        report = organization(state)
        self.assertEqual(report['run_lineage_edges'], 1)
        self.assertNotIn('unexplained_condition_list', {w['code'] for w in report['warnings']})

    def test_archived_origins_are_not_current_comparisons(self):
        state = self.fixture(); state['nodes']['r0']['status'] = 'archived'
        state['edges']['edge'] = {'source': 'r1', 'target': 'r0', 'relation': 'derived_from'}
        self.assertEqual(organization(state)['run_lineage_edges'], 0)

    def test_invalid_focus_and_wide_sections(self):
        state = self.fixture(); state['nodes']['study']['attrs']['current_focus'] = ['invalid']
        for i in range(8):
            state['nodes'][f'm{i}'] = {'id': f'm{i}', 'kind': 'module', 'parent_id': 'study', 'attrs': {}}
        codes = {w['code'] for w in organization(state)['warnings']}
        self.assertIn('invalid_current_focus', codes); self.assertIn('wide_research_outline', codes)

    def test_run_focus_requires_visible_owning_cell(self):
        state = self.fixture()
        state['nodes']['study']['attrs']['current_focus'] = 'r1'
        self.assertEqual(organization(state)['current_focus_ids'], ['r1'])
        state['nodes']['c1']['status'] = 'archived'
        self.assertIn('invalid_current_focus', {w['code'] for w in organization(state)['warnings']})

    def test_nonrenderable_focus_is_reported(self):
        state = self.fixture()
        state['nodes']['eval'] = {'id': 'eval', 'kind': 'evaluation', 'parent_id': 'r1', 'attrs': {}}
        state['nodes']['study']['attrs']['current_focus'] = 'eval'
        self.assertIn('invalid_current_focus', {w['code'] for w in organization(state)['warnings']})

    def test_cli_live_and_export_share_readonly_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root)
            state = store.init('Synthetic organization regression')
            nodes = [node('study', 'module', 'Independent conditions', state['project']['id'])]
            nodes.extend(node(f'c{i}', 'cell', f'Condition {i}', 'study') for i in range(6))
            store.commit({'base_revision': state['revision'], 'reason': 'Synthetic flat list', 'nodes': nodes})
            before = store.load()
            expected = organization(before)
            self.assertTrue(expected['needs_review'])
            cli = Path(__file__).resolve().parents[1] / 'labweft.py'
            for command in ['context', 'validate']:
                result = subprocess.run([sys.executable, str(cli), command, str(root)],
                                        capture_output=True, check=True)
                payload = json.loads(result.stdout.decode('utf-8'))
                self.assertEqual(payload['organization'], expected)
                if command == 'validate':
                    self.assertTrue(payload['valid'])
            self.assertEqual(presentation(store)['organization'], expected)
            output = root / 'snapshot.html'
            export_html(store, output)
            packed = re.search(r'<script id="snapshot-data" type="application/json">(.*?)</script>',
                               output.read_text(encoding='utf-8'), re.DOTALL)
            self.assertIsNotNone(packed)
            self.assertEqual(json.loads(packed.group(1))['organization'], expected)
            self.assertEqual(store.load(), before)
