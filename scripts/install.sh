#!/usr/bin/env bash
#
# Smart File Organizer - Linux & macOS One-Step Installer
#

set -e

APP_NAME="smart-organizer"
INSTALL_DIR="${HOME}/.local/share/smart-organizer"
BIN_DIR="${HOME}/.local/bin"

echo "=================================================="
echo "    Smart File Organizer - Installer (Unix/macOS)"
echo "=================================================="
echo ""

# 1. Detect Python 3
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 9 ]; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Error: Python 3.9 or newer was not found on your system." >&2
    echo "Please install Python using your package manager:" >&2
    echo "  - Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip" >&2
    echo "  - Arch Linux:    sudo pacman -S python python-pip" >&2
    echo "  - macOS:         brew install python" >&2
    exit 1
fi

echo "Found Python: $("$PYTHON_BIN" --version)"

# 2. Get repository directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 3. Create isolated virtual environment
echo "Creating application environment in ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
"$PYTHON_BIN" -m venv "${INSTALL_DIR}/venv"

# 4. Install dependencies and package
echo "Installing Smart File Organizer..."
"${INSTALL_DIR}/venv/bin/pip" install setuptools wheel >/dev/null 2>&1 || true
"${INSTALL_DIR}/venv/bin/pip" install --no-build-isolation -e "${SCRIPT_DIR}"

# 5. Create launcher in ~/.local/bin
mkdir -p "${BIN_DIR}"
LAUNCHER="${BIN_DIR}/${APP_NAME}"

cat << 'EOF' > "${LAUNCHER}"
#!/usr/bin/env bash
INSTALL_DIR="${HOME}/.local/share/smart-organizer"
exec "${INSTALL_DIR}/venv/bin/smart-organizer" "$@"
EOF

chmod +x "${LAUNCHER}"

echo ""
echo "=================================================="
echo "  ✓ Installation Successful!"
echo "=================================================="
echo ""
echo "You can now run Smart File Organizer anywhere using:"
echo ""
echo "    smart-organizer"
echo ""

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "Note: ${BIN_DIR} is not currently in your PATH."
    echo "Add it to your shell configuration (~/.bashrc or ~/.zshrc):"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo "To organize existing files directly in Downloads:"
echo "    smart-organizer --organize-existing"
echo ""
echo "To view status and configuration:"
echo "    smart-organizer --status"
echo ""
