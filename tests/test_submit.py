from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
copr = ModuleType('copr')
copr_v3 = ModuleType('copr.v3')
copr_v3.Client = object
with patch.dict(sys.modules, {'copr': copr, 'copr.v3': copr_v3}):
    import submit


class SubmitTest(unittest.TestCase):
    def build(self, **changes):
        return {'source_package': {'name': 'cli-proxy-api', 'version': '8.0.8-1.fc44'},
                'chroots': ['fedora-44-x86_64', 'fedora-45-x86_64'], 'state': 'succeeded', **changes}

    def reusable(self, build):
        return submit.reusable(build, 'cli-proxy-api', '8.0.8', 1,
                               ['fedora-44-x86_64', 'fedora-45-x86_64'])

    def test_completed_and_running_builds_are_reused(self):
        self.assertTrue(self.reusable(self.build()))
        self.assertTrue(self.reusable(self.build(state='running')))

    def test_failed_or_partial_builds_are_retried(self):
        self.assertFalse(self.reusable(self.build(state='failed')))
        self.assertFalse(self.reusable(self.build(chroots=['fedora-44-x86_64'])))

    def test_new_revision_and_new_release_are_not_skipped(self):
        for version in ['8.0.8-10.fc44', '8.0.8-2.fc44', '8.0.7-1.fc44']:
            self.assertFalse(self.reusable(self.build(source_package={'name': 'cli-proxy-api', 'version': version})))

    def test_another_package_or_unresolved_source_is_not_reused(self):
        self.assertFalse(self.reusable(self.build(source_package={'name': 'cli-proxy-api-manager', 'version': '8.0.8-1.fc44'})))
        self.assertFalse(self.reusable(self.build(source_package=None)))


if __name__ == '__main__':
    unittest.main()
