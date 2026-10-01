# CLIProxyAPI Fedora packages

GitHub Actions checks published upstream releases every day at 04:17 UTC and
submits new source RPMs to COPR. Only stable `vMAJOR.MINOR.PATCH` releases are
accepted. Drafts, prereleases, branch heads and upstream `main` are excluded.

The two packages track their releases independently:

- `cli-proxy-api` builds Go source from the commit referenced by the published
  CLIProxyAPI release. Go modules are verified and vendored before submission.
  COPR builds with network access disabled and retains dynamic-library plugins.
- `cli-proxy-api-manager` packages the published self-contained `management.html`
  release asset after checking its GitHub SHA-256 digest. It also installs a
  launcher for `http://127.0.0.1:8317/management.html`.

The target chroots are Fedora 44 and 45 on x86_64. This is a personal COPR
repository, not a submission to Fedora's official package collection. Bundled
dependencies and the manager's upstream HTML distribution are included in the
source RPMs.

## One-time setup

The GitHub repository needs:

- Variable `COPR_OWNER`: your Fedora account name.
- Optional variable `COPR_PROJECT`: defaults to `cli-proxy-api`.
- Secret `COPR_CONFIG`: the complete API configuration from
  <https://copr.fedorainfracloud.org/api/>. Keep this out of Git.

Create the COPR project with the chroots in `release-config.json` and with
network access during binary builds disabled. The credential wizard at
`scripts/configure-copr.sh` saves your API credentials privately for the initial
project setup. Run the workflow once using **Actions → Package stable upstream
releases → Run workflow**. Subsequent daily checks run automatically.

Successful builds create GitHub release markers with the SRPM, source checksums
and COPR build IDs. Failed builds leave no marker and retry on the next check.
An interrupted runner reuses a matching pending or successful COPR build.
Increase `revision` in `release-config.json` when changing the packaging of an
already released upstream version.

## Install

After the first COPR builds succeed:

```sh
sudo dnf copr enable YOUR_FEDORA_USERNAME/cli-proxy-api
sudo dnf install cli-proxy-api cli-proxy-api-manager
```

RPM updates come through normal `dnf upgrade`. The package installs the user
service without starting it. Keep account files and local API keys under your
home directory. On a new installation, copy
`/usr/share/cli-proxy-api/config.example.yaml` to
`~/.config/cli-proxy-api/config.yaml`, restrict its permissions, bind the server
to `127.0.0.1`, and set your own client and management keys before enabling
`systemctl --user enable --now cli-proxy-api`.

The packaged service reads that user configuration and serves the packaged
manager from `/usr/share/cli-proxy-api/management.html`. Existing installations
must migrate any service override that points to `~/.local/bin/cli-proxy-api`.
The dotfiles migration preserves configuration, account files and old binaries
in a private backup directory.

## Local validation

```sh
python3 -m unittest discover -s tests -v
python3 scripts/releases.py discover
python3 scripts/releases.py prepare cli-proxy-api v8.0.8
bash scripts/build-srpm.sh cli-proxy-api
```

Source preparation needs Go at least as new as the release's `go.mod` declares.
SRPM creation uses a Fedora Podman container. No host sudo access is required.
