#!/usr/bin/env python3
"""Create the authorized personal COPR project using private local credentials."""
import configparser
import json
from pathlib import Path

from copr.v3 import Client

from releases import CONFIG


def main():
    config = configparser.ConfigParser()
    if not config.read(Path.home() / '.config/copr'):
        raise SystemExit('Sign into COPR and run scripts/configure-copr.sh first.')
    owner = config['copr-cli']['username']
    project = CONFIG['copr_project']
    client = Client.create_from_config_file()
    description = ('Stable published CLIProxyAPI and CLI Proxy Manager releases. '
        'Go source is compiled offline with vendored dependencies. '
        'GitHub Actions checks daily; no branch-head or prerelease builds.')
    instructions = (f'sudo dnf copr enable {owner}/{project}\n'
        'sudo dnf install cli-proxy-api cli-proxy-api-manager\n\n'
        'Configure your private user gateway before enabling the user service. '
        'See https://github.com/julienkellerhals/cli-proxy-api-rpm for migration details.')
    client.project_proxy.add(owner, project, CONFIG['chroots'], description=description,
        instructions=instructions, homepage='https://github.com/julienkellerhals/cli-proxy-api-rpm',
        enable_net=False, exist_ok=True)
    # An existing project must also have the exact intended build targets.
    client.project_proxy.edit(owner, project, chroots=CONFIG['chroots'], enable_net=False,
        description=description, instructions=instructions)
    print(json.dumps({'owner': owner, 'project': project, 'chroots': CONFIG['chroots'],
        'url': f'https://copr.fedorainfracloud.org/coprs/{owner}/{project}/'}))


if __name__ == '__main__':
    main()
