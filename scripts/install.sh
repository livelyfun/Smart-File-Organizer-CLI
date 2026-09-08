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

# 1. Detect Python >= 3.9
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Error: Python 3.9 or newer was not found on your system." >&2
    echo "Please install Python using your package manager:" >&2
    echo "  - Debian/Ubuntu: sudo apt update && sudo apt install python3 python3-venv python3-pip" >&2
    echo "  - Arch Linux:    sudo pacman -S python python-pip" >&2
    echo "  - macOS:         brew install python" >&2
    exit 1
fi

echo "Found Python: $("$PYTHON_BIN" --version)"

# 2. Get repository directory (parent of the scripts/ folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 3. Create isolated virtual environment
echo "Creating application environment in ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
"$PYTHON_BIN" -m venv "${INSTALL_DIR}/venv"

# 4. Upgrade pip (fail loudly if this errors)
echo "Upgrading pip..."
if ! "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip setuptools wheel; then
    echo "" >&2
    echo "Error: Failed to upgrade pip inside the virtual environment." >&2
    echo "Please check your internet connection and try again." >&2
    exit 1
fi

# 5. Install the package (--force-reinstall handles re-runs cleanly)
echo "Installing Smart File Organizer..."
if ! "${INSTALL_DIR}/venv/bin/pip" install --force-reinstall "${SCRIPT_DIR}"; then
    echo "" >&2
    echo "Error: Package installation failed." >&2
    echo "Please check the output above for details." >&2
    exit 1
fi

# 6. Create launcher wrapper in ~/.local/bin
mkdir -p "${BIN_DIR}"
LAUNCHER="${BIN_DIR}/${APP_NAME}"

# NOTE: single-quote heredoc so ${HOME} expands at launcher *runtime*, not install time.
cat << 'EOF' > "${LAUNCHER}"
#!/usr/bin/env bash
INSTALL_DIR="${HOME}/.local/share/smart-organizer"
exec "${INSTALL_DIR}/venv/bin/smart-organizer" "$@"
EOF

chmod +x "${LAUNCHER}"

# 7. Check and configure PATH in user shell rc files if needed
PATH_CONFIGURED=false
PATH_EXPORT_LINE='export PATH="$HOME/.local/bin:$PATH"'

if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
    PATH_CONFIGURED=true
else
    # Attempt to persist in active shell profile
    for rc_file in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
        if [ -f "$rc_file" ]; then
            if ! grep -q ".local/bin" "$rc_file" 2>/dev/null; then
                echo "" >> "$rc_file"
                echo "# Added by Smart File Organizer installer" >> "$rc_file"
                echo "$PATH_EXPORT_LINE" >> "$rc_file"
            fi
        fi
    done
fi

echo ""
echo "=================================================="
echo "  Installation Successful!"
echo "=================================================="
echo ""

if [ "$PATH_CONFIGURED" = true ]; then
    echo "You can now run Smart File Organizer anywhere using:"
    echo ""
    echo "    smart-organizer"
    echo ""
else
    echo "Note: ${BIN_DIR} has been added to your shell profile for future sessions."
    echo "To use 'smart-organizer' in this current terminal, run:"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Or open a fresh terminal window, then run:"
    echo ""
    echo "    smart-organizer"
    echo ""
fi

echo "To organize existing files directly in Downloads:"
echo "    smart-organizer --organize-existing"
echo ""
echo "To view configuration and directory status:"
echo "    smart-organizer --status"
echo ""
