#!/usr/bin/env bash
set -euo pipefail
package=${1:?Specify cli-proxy-api or cli-proxy-api-manager}
case "$package" in cli-proxy-api|cli-proxy-api-manager) ;; *) exit 2 ;; esac
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
podman run --rm --network=host \
    -v "$repo/build/$package:/rpmbuild:Z" \
    registry.fedoraproject.org/fedora:44 \
    bash -euc 'dnf -y install rpm-build systemd-rpm-macros >/dev/null; rpmbuild -bs --define "_topdir /rpmbuild" /rpmbuild/SPECS/*.spec'
