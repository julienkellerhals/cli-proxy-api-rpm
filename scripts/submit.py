#!/usr/bin/env python3
"""Reuse an existing matching COPR build or submit and wait for a new one."""
import argparse
import json
import time

from copr.v3 import Client

from releases import CONFIG, ROOT

FAILED = {'failed', 'canceled', 'skipped'}
ACTIVE = {'pending', 'starting', 'running', 'importing', 'waiting', 'forked'}


def reusable(build, package, version, revision, chroots):
    data = build.get('source_package') or {}
    expected = f'{version}-{revision}'
    actual = data.get('version', '')
    return (data.get('name') == package
        and (actual == expected or actual.startswith(expected + '.'))
        and set(chroots).issubset(build.get('chroots', []))
        and (build['state'] == 'succeeded' or build['state'] in ACTIVE))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', choices=CONFIG['packages'])
    parser.add_argument('owner')
    parser.add_argument('project')
    args = parser.parse_args()
    top = ROOT / 'build' / args.package
    provenance = json.loads((top / 'provenance.json').read_text())
    version = provenance['version']
    client = Client.create_from_config_file()
    # Reuse pending/successful builds if a prior Actions job was interrupted
    # before recording its success marker. Revisions belong to the RPM release.
    candidate = None
    for build in client.build_proxy.get_list(ownername=args.owner, projectname=args.project,
            packagename=args.package, pagination={'limit': 100, 'order': 'id', 'order_type': 'DESC'}):
        source = client.build_proxy.get(build.id)
        # COPR exposes source versions as VERSION-RELEASE, including the dist
        # suffix, rather than separate version and release fields.
        if reusable(source, args.package, version, CONFIG['revision'], CONFIG['chroots']):
            candidate = source
            break
    if candidate is None:
        srpm, = (top / 'SRPMS').glob('*.src.rpm')
        candidate = client.build_proxy.create_from_file(args.owner, args.project, str(srpm),
            buildopts={'chroots': CONFIG['chroots'], 'enable_net': False})
    build_id = candidate.id
    print(f'COPR build {build_id}: https://copr.fedorainfracloud.org/coprs/{args.owner}/{args.project}/build/{build_id}/', flush=True)
    deadline = time.monotonic() + 35 * 60
    previous = None
    while time.monotonic() < deadline:
        build = client.build_proxy.get(build_id)
        if build.state != previous:
            print('COPR state:', build.state, flush=True)
            previous = build.state
        if build.state == 'succeeded':
            (top / 'copr-build.json').write_text(json.dumps({'build_id': build_id, 'state': build.state,
                'owner': args.owner, 'project': args.project, 'chroots': CONFIG['chroots']}, indent=2) + '\n')
            return
        if build.state in FAILED:
            raise SystemExit(f'COPR build {build_id} {build.state}. Check the linked builder logs.')
        time.sleep(20)
    raise SystemExit(f'COPR build {build_id} is still {previous}; no success marker was recorded.')


if __name__ == '__main__':
    main()
