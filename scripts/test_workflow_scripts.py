"""Regression checks for missing CI scripts and working-directory resolution."""

from pathlib import Path
import tempfile
import unittest

import yaml

from check_workflow_scripts import check


class WorkflowScriptsTests(unittest.TestCase):
    def test_missing_installer_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflows = root / '.github/workflows'
            workflows.mkdir(parents=True)
            (workflows / 'integration.yml').write_text(yaml.safe_dump({
                'jobs': {'convert': {'steps': [
                    {'run': './scripts/install_texlive_ci.ps1'}
                ]}}
            }), encoding='utf-8')
            self.assertEqual(len(check(root)), 1)
            (root / 'scripts').mkdir()
            (root / 'scripts/install_texlive_ci.ps1').touch()
            self.assertEqual(check(root), [])

    def test_working_directory_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflows = root / '.github/workflows'
            workflows.mkdir(parents=True)
            for directory in ('workflow', 'job', 'step'):
                (root / directory).mkdir()
                (root / directory / 'check.py').touch()
            (workflows / 'quality.yaml').write_text(yaml.safe_dump({
                'defaults': {'run': {'working-directory': 'workflow'}},
                'jobs': {
                    'inherited': {'steps': [{'run': 'python ./check.py'}]},
                    'override': {
                        'defaults': {'run': {'working-directory': 'job'}},
                        'steps': [
                            {'run': 'python ./check.py'},
                            {'working-directory': 'step', 'run': r'python .\check.py'},
                            {'run': 'python ../workflow/check.py'},
                        ],
                    },
                },
            }), encoding='utf-8')
            self.assertEqual(check(root), [])
            (root / 'step/check.py').unlink()
            self.assertEqual(len(check(root)), 1)


if __name__ == '__main__':
    unittest.main()
