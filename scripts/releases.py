#!/usr/bin/env python3
"""Discover stable published releases and prepare offline source RPM inputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'release-config.json').read_text())
VERSION = re.compile(r'^v?(\d+\.\d+\.\d+)$')


def request(url, *, api=False):
    headers = {'User-Agent': 'cli-proxy-api-rpm', 'Accept': 'application/vnd.github+json' if api else '*/*'}
    if api and os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def github(path):
    return json.loads(request('https://api.github.com/' + path, api=True))


def stable_version(release):
    match = VERSION.fullmatch(release.get('tag_name', ''))
    if release.get('draft') or release.get('prerelease') or not release.get('published_at') or not match:
        raise ValueError('Only published stable vMAJOR.MINOR.PATCH releases are accepted.')
    return match[1]


def select_latest(releases):
    eligible = []
    for release in releases:
        try:
            version = stable_version(release)
        except ValueError:
            continue
        eligible.append((tuple(map(int, version.split('.'))), release))
    if not eligible:
        raise ValueError('No published stable release found.')
    return max(eligible, key=lambda entry: entry[0])[1]


def latest(repo):
    # The list excludes draft releases for the Actions token and still lets us
    # explicitly exclude prereleases and out-of-order maintenance releases.
    return select_latest(github(f'repos/{repo}/releases?per_page=100'))


def marker(package, version):
    return f'{package}-v{version}-r{CONFIG["revision"]}'


def discover():
    include = []
    packaging_repo = os.environ.get('GITHUB_REPOSITORY', 'julienkellerhals/cli-proxy-api-rpm')
    for package, upstream in CONFIG['packages'].items():
        release = latest(upstream)
        version = stable_version(release)
        name = marker(package, version)
        try:
            existing = github(f'repos/{packaging_repo}/releases/tags/{name}')
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        else:
            if not existing.get('draft'):
                continue
        include.append({'package': package, 'tag': release['tag_name'], 'version': version, 'marker': name})
    return {'include': include}


def source_commit(repo, tag):
    obj = github(f'repos/{repo}/git/ref/tags/{tag}')['object']
    for _ in range(8):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag':
            break
        obj = github(f'repos/{repo}/git/tags/{obj["sha"]}')['object']
    raise ValueError('Release tag does not resolve to a commit.')


def source_tree(repo, tag, destination):
    commit = source_commit(repo, tag)
    archive = request(f'https://api.github.com/repos/{repo}/tarball/{commit}', api=True)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        names = tar.getnames()
        root = names[0].split('/')[0]
        tar.extractall(destination.parent, filter='data')
        extracted = destination.parent / root
        extracted.rename(destination)
    return commit


def write_tar(source, output, arcname):
    with tarfile.open(output, 'w:gz') as tar:
        tar.add(source, arcname=arcname)


def verify_asset(asset, content):
    digest = asset.get('digest')
    if not digest or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('The published asset must provide a GitHub SHA-256 digest.')
    if hashlib.sha256(content).hexdigest() != digest[7:]:
        raise ValueError('Release asset checksum differs.')


def prepare(package, tag):
    repo = CONFIG['packages'][package]
    release = github(f'repos/{repo}/releases/tags/{tag}')
    version = stable_version(release)
    top = ROOT / 'build' / package
    if top.exists():
        shutil.rmtree(top)
    sources = top / 'SOURCES'
    sources.mkdir(parents=True)
    for directory in ['SPECS', 'SRPMS', 'RPMS', 'BUILD', 'BUILDROOT']:
        (top / directory).mkdir()
    variables = {'VERSION': version, 'REVISION': str(CONFIG['revision']),
                 'CHANGELOG_DATE': datetime.now(timezone.utc).strftime('%a %b %d %Y')}
    provenance = {'package': package, 'version': version, 'upstream': repo,
                  'release_id': release['id'], 'tag': tag, 'published_at': release['published_at']}
    if package == 'cli-proxy-api':
        work = top / 'work'
        work.mkdir()
        source = work / f'{package}-{version}'
        commit = source_tree(repo, tag, source)
        go = re.search(r'^go\s+(\d+\.\d+\.\d+)', (source / 'go.mod').read_text(), re.M)
        if not go:
            raise ValueError('Release go.mod must declare its required Go version.')
        subprocess.run(['go', 'mod', 'download'], cwd=source, check=True)
        subprocess.run(['go', 'mod', 'verify'], cwd=source, check=True)
        subprocess.run(['go', 'mod', 'vendor'], cwd=source, check=True)
        for license_file in (source / 'vendor').rglob('*'):
            if license_file.is_file() and license_file.name.lower().startswith(('license', 'licence', 'copying', 'notice')):
                target = source / 'bundled-licenses' / license_file.relative_to(source / 'vendor')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(license_file, target)
        write_tar(source / 'vendor', sources / f'{package}-{version}-vendor.tar.gz', 'vendor')
        shutil.rmtree(source / 'vendor')
        write_tar(source, sources / f'{package}-{version}.tar.gz', source.name)
        shutil.copy2(ROOT / 'packaging/cli-proxy-api.service', sources)
        variables.update({'COMMIT': commit, 'GO_VERSION': go[1], 'BUILD_DATE': release['published_at']})
        provenance['source_commit'] = commit
    else:
        asset = next(a for a in release['assets'] if a['name'] == 'management.html')
        content = request(asset['browser_download_url'])
        verify_asset(asset, content)
        (sources / f'management-{version}.html').write_bytes(content)
        commit = source_commit(repo, tag)
        (sources / 'manager-LICENSE').write_bytes(request(f'https://raw.githubusercontent.com/{repo}/{commit}/LICENSE'))
        shutil.copy2(ROOT / 'packaging/cli-proxy-api-manager.desktop', sources)
        provenance.update({'source_commit': commit, 'asset_digest': asset['digest']})
    template = (ROOT / f'packaging/{package}.spec.in').read_text()
    for name, value in variables.items():
        template = template.replace('@' + name + '@', value)
    if re.search(r'@[A-Z_]+@', template):
        raise ValueError('Spec template has unexpanded fields.')
    (top / 'SPECS' / f'{package}.spec').write_text(template)
    provenance['sources_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.iterdir()}
    (top / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(top)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('discover')
    build = sub.add_parser('prepare')
    build.add_argument('package', choices=CONFIG['packages'])
    build.add_argument('tag', help='A published stable release tag, never a branch name')
    args = parser.parse_args()
    if args.command == 'discover':
        print(json.dumps(discover(), separators=(',', ':')))
    else:
        if not VERSION.fullmatch(args.tag):
            parser.error('Use a stable release tag such as v8.0.8, never main.')
        prepare(args.package, args.tag)


if __name__ == '__main__':
    main()
