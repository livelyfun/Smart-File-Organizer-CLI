#!/usr/bin/env bash
#
# Smart File Organizer - one-step installer for Linux and macOS.
#
# By default this downloads a prebuilt, self-contained executable. Python is
# NOT required. Use --from-source to install from a git checkout instead,
# which does require Python 3.9 or newer.
#
# The downloaded archive is verified against the SHA-256 checksum published
# alongside it before anything is installed. Nothing is written to a
# system-wide location unless you ask for it with --system.
#
# Usage:
#   ./scripts/install.sh                  install the latest release
#   ./scripts/install.sh --version 1.2.0  install a specific release
#   ./scripts/install.sh --from-source    install from this checkout
#   ./scripts/install.sh --system         install into /usr/local (needs sudo)
#   ./scripts/install.sh --help

set -euo pipefail

APP_NAME="smart-organizer"
REPO="livelyfun/Smart-File-Organizer-CLI"
RELEASES_API="https://api.github.com/repos/${REPO}/releases/latest"

# Interpreter used by --from-source. The prebuilt path below never needs one.
PYTHON="${PYTHON_BIN:-python3}"

# The macOS DMG mounts a directory at the root of its volume, and the
# executable sits inside it. The build stages the image from that directory,
# so this name has to match packaging/build.py's DMG_VOLUME_NAME; see
# tests/test_packaging_layout.py.
DMG_VOLUME_DIR="Smart File Organizer"

# Per-user install locations. Chosen to match the convention a user's shell
# profile already has on PATH, so no rc file has to be edited.
INSTALL_ROOT="${HOME}/.local/share/smart-organizer"
BIN_DIR="${HOME}/.local/bin"

VERSION=""
FROM_SOURCE=false
SYSTEM=false

log()  { printf '%s\n' "$*"; }
info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

# Run a command with sudo only when the destination is not already writable.
# Keeps the common case free of a password prompt and a root shell.
as_root() {
    if [ -w "$1" ]; then
        shift
        "$@"
    else
        if command -v sudo >/dev/null 2>&1; then
            sudo "$@"
        else
            die "$1 is not writable and sudo is unavailable. Re-run with --help for options."
        fi
    fi
}

require() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

# ---------------------------------------------------------------- source mode

install_from_source() {
    require "${PYTHON}"
    # Match the floor install.ps1 enforces and pyproject's requires-python, so
    # an old interpreter fails here with a usable message rather than part way
    # through creating a virtual environment.
    if ! "${PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
        die "Python 3.9 or newer is required for this mode. Install a newer
Python, or drop --from-source to install the prebuilt release, which needs
no Python at all."
    fi

    info "Installing from source into ${INSTALL_ROOT}"

    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

    mkdir -p "${INSTALL_ROOT}"
    "${PYTHON}" -m venv "${INSTALL_ROOT}/venv"
    "${INSTALL_ROOT}/venv/bin/pip" install --quiet --upgrade pip
    "${INSTALL_ROOT}/venv/bin/pip" install --quiet "${script_dir}"

    mkdir -p "${BIN_DIR}"
    cat > "${BIN_DIR}/${APP_NAME}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_ROOT}/venv/bin/${APP_NAME}" "\$@"
EOF
    chmod +x "${BIN_DIR}/${APP_NAME}"

    log ""
    info "Installed from source. Python 3.9+ is required for this mode."
    log "Run: ${APP_NAME} --version"
}

# ------------------------------------------------------------- download mode

fetch_url() {
    # $1 url, $2 destination. Verified TLS only; the bundled macOS curl has
    # no option to disable verification, so no such option is offered.
    local url="$1" dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 \
             --output "${dest}" "${url}"
    elif command -v wget >/dev/null 2>&1; then
        wget --quiet --https-only --output-document "${dest}" "${url}"
    else
        die "neither curl nor wget is available to download the release"
    fi
}

sha256_of() {
    # shasum ships with macOS and Perl; sha256sum with coreutils; openssl is
    # the last resort. Not all three exist on every system, so try each.
    local file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${file}" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${file}" | awk '{print $1}'
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "${file}" | awk '{print $NF}'
    else
        die "no SHA-256 tool found (looked for sha256sum, shasum and openssl).
The download cannot be verified, so it will not be installed."
    fi
}

verify_checksum() {
    # $1 file, $2 expected sha256. Compares in a pipeline-safe way.
    local file="$1" expected="$2" actual
    actual="$(sha256_of "${file}")"
    if [ "${actual}" != "${expected}" ]; then
        rm -f "${file}"
        die "checksum mismatch for $(basename "${file}").
  expected: ${expected}
  actual:   ${actual}
The download has been discarded. If this persists, the release may have
been tampered with; please report it on the project's issue tracker."
    fi
    info "Checksum verified"
}

resolve_latest_version() {
    require curl
    local body
    body="$(curl --fail --location --silent --show-error --proto '=https' \
                 -H 'Accept: application/vnd.github+json' \
                 -H 'User-Agent: smart-file-organizer-installer' \
                 "${RELEASES_API}")" \
        || die "could not query the latest release from GitHub"

    # Prefer parsing the JSON properly; fall back to a narrow match so the
    # installer still works if python/jq are both unavailable.
    local version=""
    if command -v python3 >/dev/null 2>&1; then
        version="$(printf '%s' "${body}" | python3 -c \
            'import json,sys; print(json.load(sys.stdin).get("tag_name","").lstrip("vV"))' \
            2>/dev/null || true)"
    fi
    if [ -z "${version}" ]; then
        version="$(printf '%s' "${body}" | grep -o '"tag_name"[[:space:]]*:[[:space:]]*"v\?[0-9][^"]*"' \
            | head -1 | sed -e 's/.*"v\?\([0-9][^"]*\)".*/\1/')"
    fi
    [ -n "${version}" ] || die "could not determine the latest release version"
    printf '%s' "${version}"
}

install_linux() {
    local version="$1" tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "${tmp}"' RETURN

    local base="${APP_NAME}-${version}-linux-x86_64"
    local archive="${base}.tar.xz"

    info "Downloading ${APP_NAME} ${version} (linux-x86_64)"
    fetch_url "https://github.com/${REPO}/releases/download/v${version}/${archive}" "${tmp}/${archive}"
    fetch_url "https://github.com/${REPO}/releases/download/v${version}/${archive}.sha256" "${tmp}/${archive}.sha256"

    local expected
    expected="$(awk '{print $1; exit}' "${tmp}/${archive}.sha256")"
    [ -n "${expected}" ] || die "checksum file for ${archive} was empty or malformed"
    verify_checksum "${tmp}/${archive}" "${expected}"

    require tar
    tar -xJf "${tmp}/${archive}" -C "${tmp}"

    as_root "${INSTALL_ROOT}" mkdir -p "${INSTALL_ROOT}"
    as_root "${INSTALL_ROOT}" rm -rf "${INSTALL_ROOT}/${APP_NAME}"
    as_root "${INSTALL_ROOT}" cp -R "${tmp}/${base}/${APP_NAME}" "${INSTALL_ROOT}/${APP_NAME}"

    install_launcher_shim
}

# Reads hdiutil attach output on stdin and prints the mount point it reported.
#
# hdiutil prints one line per mounted volume: the device, the filesystem type,
# then the mount point in the last column, padded out to align the columns.
# That padding is whitespace, but not reliably a tab, so the path is taken
# from "/Volumes/" to the end of the line and the trailing padding trimmed.
# The volume name can contain spaces of its own, which is why this is not a
# whitespace split.
parse_mount_point() {
    grep -o '/Volumes/.*' | head -1 | sed -e 's/[[:space:]]*$//' || true
}

# Mounts an image read-only at a random unused path and prints the mount point.
#
# This is the only place the installer mounts anything, and the Build workflow
# calls it against a freshly built DMG. Keeping it separate from the install
# itself is what lets the build check the real code rather than a copy of it:
# a duplicated mount command is free to drift until a user's Mac finds out.
#
# -mountrandom takes the directory to create the random path under. Passing it
# without one is an error, so the argument is written out rather than assumed.
attach_dmg() {
    local image="$1" mount_point
    # hdiutil's own exit status is deliberately not the answer here. It can
    # fail while still printing a usable mount point, and with `set -e` a
    # non-zero pipeline would end the script before the check below could
    # explain what happened.
    mount_point=$(hdiutil attach "${image}" -nobrowse -readonly -mountrandom /Volumes \
                  | parse_mount_point || true)
    [ -n "${mount_point}" ] || die "could not mount $(basename "${image}"): hdiutil reported no mount point"
    printf '%s' "${mount_point}"
}

install_macos() {
    local version="$1" tmp mount_point=""
    tmp="$(mktemp -d)"
    trap 'rm -rf "${tmp}"; [ -n "${mount_point}" ] && hdiutil detach "${mount_point}" -quiet 2>/dev/null || true' RETURN

    local dmg="SmartFileOrganizer-${version}-macos.dmg"

    info "Downloading ${APP_NAME} ${version} (macos)"
    fetch_url "https://github.com/${REPO}/releases/download/v${version}/${dmg}" "${tmp}/${dmg}"
    fetch_url "https://github.com/${REPO}/releases/download/v${version}/${dmg}.sha256" "${tmp}/${dmg}.sha256"

    local expected
    expected="$(awk '{print $1; exit}' "${tmp}/${dmg}.sha256")"
    [ -n "${expected}" ] || die "checksum file for ${dmg} was empty or malformed"
    verify_checksum "${tmp}/${dmg}" "${expected}"

    require hdiutil
    mount_point="$(attach_dmg "${tmp}/${dmg}")"

    # The bundle is staged inside a directory, so it is not at the volume
    # root. Getting this path wrong copies nothing and leaves the user with
    # an empty install directory, so it is checked before anything is made.
    local bundled="${mount_point}/${DMG_VOLUME_DIR}/${APP_NAME}"
    if [ ! -d "${bundled}" ]; then
        die "${dmg} does not contain ${DMG_VOLUME_DIR}/${APP_NAME}.
The image layout has changed, or the download is damaged. Re-run with
--from-source, or report this on the project's issue tracker."
    fi

    as_root "${INSTALL_ROOT}" mkdir -p "${INSTALL_ROOT}"
    as_root "${INSTALL_ROOT}" rm -rf "${INSTALL_ROOT}/${APP_NAME}"
    as_root "${INSTALL_ROOT}" cp -R "${bundled}" "${INSTALL_ROOT}/${APP_NAME}"

    hdiutil detach "${mount_point}" -quiet
    mount_point=""

    install_launcher_shim
}

install_launcher_shim() {
    as_root "${BIN_DIR}" mkdir -p "${BIN_DIR}"
    local shim="${BIN_DIR}/${APP_NAME}"
    if [ -w "${BIN_DIR}" ]; then
        cat > "${shim}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_ROOT}/${APP_NAME}/${APP_NAME}" "\$@"
EOF
    else
        as_root "${shim}" tee "${shim}" >/dev/null <<EOF
#!/usr/bin/env bash
exec "${INSTALL_ROOT}/${APP_NAME}/${APP_NAME}" "\$@"
EOF
    fi
    as_root "${shim}" chmod +x "${shim}"
    info "Installed to ${shim}"
}

main() {
    # Parsed here rather than at the top level so that sourcing this file is
    # genuinely free of side effects: a test that sources it must not have its
    # own arguments consumed and rejected as unknown options.
    while [ $# -gt 0 ]; do
        case "$1" in
            --from-source) FROM_SOURCE=true ;;
            --system)     SYSTEM=true ;;
            --version)    shift; VERSION="${1:-}" ;;
            --version=*)  VERSION="${1#*=}" ;;
            -h|--help)    usage ;;
            *)            die "unknown option: $1 (try --help)" ;;
        esac
        shift
    done

    if [ "$SYSTEM" = true ]; then
        INSTALL_ROOT="/usr/local/share/${APP_NAME}"
        BIN_DIR="/usr/local/bin"
    fi

    log "=================================================="
    log "    Smart File Organizer - Installer (Unix/macOS)"
    log "=================================================="
    log ""

    if [ "$FROM_SOURCE" = true ]; then
        install_from_source
        return 0
    fi

    local os arch
    os="$(uname -s)"
    arch="$(uname -m)"
    case "${arch}" in
        x86_64|amd64) ;;
        *) die "no prebuilt release for ${arch}. Use --from-source to build from a checkout." ;;
    esac

    if [ -z "${VERSION}" ]; then
        info "Looking up the latest release"
        VERSION="$(resolve_latest_version)"
    fi
    info "Installing ${APP_NAME} ${VERSION}"

    case "${os}" in
        Linux)  install_linux "${VERSION}" ;;
        Darwin) install_macos "${VERSION}" ;;
        *) die "unsupported operating system: ${os}. Use --from-source instead." ;;
    esac

    # A frozen build must run. Prove it here rather than leaving the user to
    # find out that the executable does not work on their machine.
    if ! "${INSTALL_ROOT}/${APP_NAME}/${APP_NAME}" --version >/dev/null 2>&1; then
        die "the installed executable failed to run. Re-run with --from-source, or
report this on the project's issue tracker."
    fi

    log ""
    log "=================================================="
    log "  Installation Successful"
    log "=================================================="
    log ""
    if [ ":${PATH}:" != *":${BIN_DIR}:"* ]; then
        log "${BIN_DIR} is not on your PATH in this shell. Add it with:"
        log "    export PATH=\"${BIN_DIR}:\$PATH\""
        log ""
    fi
    log "Then try:"
    log "    ${APP_NAME} --status"
    log "    ${APP_NAME}"
}

# Only install when executed. Sourcing this file exposes the functions above
# so the checksum and extraction logic can be tested without a network.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
