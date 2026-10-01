import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('releases', Path(__file__).parents[1] / 'scripts/releases.py')
releases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(releases)


def release(tag, **changes):
    return dict(tag_name=tag, draft=False, prerelease=False, published_at='2026-10-01T00:00:00Z', **changes)


class ReleasesTest(unittest.TestCase):
    def test_selection_ignores_branches_drafts_and_prereleases(self):
        candidates = [release('v8.0.8'), release('main'), release('v9.0.0-rc1'),
                      {**release('v9.0.0'), 'draft': True},
                      {**release('v10.0.0'), 'prerelease': True},
                      {**release('v11.0.0'), 'published_at': None}]
        self.assertEqual(releases.select_latest(candidates)['tag_name'], 'v8.0.8')

    def test_selection_uses_version_order_not_api_order(self):
        self.assertEqual(releases.select_latest([release('v8.0.9'), release('v8.0.10'), release('v7.9.99')])['tag_name'], 'v8.0.10')

    def test_asset_must_match_a_published_digest(self):
        data = b'<html>release</html>'
        asset = {'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}
        releases.verify_asset(asset, data)
        with self.assertRaises(ValueError):
            releases.verify_asset(asset, data + b'changed')
        with self.assertRaises(ValueError):
            releases.verify_asset({}, data)

    def test_success_marker_skips_a_release_but_draft_marker_retries(self):
        with patch.object(releases, 'latest', return_value=release('v8.0.8')):
            with patch.object(releases, 'github', return_value={'draft': False}):
                self.assertEqual(releases.discover(), {'include': []})
            with patch.object(releases, 'github', return_value={'draft': True}):
                self.assertEqual(len(releases.discover()['include']), 2)

    def test_auth_failure_does_not_masquerade_as_unbuilt_release(self):
        with patch.object(releases, 'latest', return_value=release('v8.0.8')):
            with patch.object(releases, 'github', side_effect=urllib.error.HTTPError('url', 403, 'Forbidden', {}, None)):
                with self.assertRaises(urllib.error.HTTPError):
                    releases.discover()


if __name__ == '__main__':
    unittest.main()
