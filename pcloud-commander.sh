#!/bin/bash
# pcloud-commander.sh — Startet den pCloud Commander im richtigen venv

# === Pfade definieren ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PCLOUD_TOOLS_DIR="/opt/apps/pcloud-tools"
VENV_PATH="$PCLOUD_TOOLS_DIR/venv"

# === Farben ===
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# === Check: venv vorhanden? ===
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}Error: Virtual Environment not found at $VENV_PATH${NC}"
    echo "Please run setup_venv.sh in $PCLOUD_TOOLS_DIR first."
    exit 1
fi

# === venv aktivieren ===
source "$VENV_PATH/bin/activate"

# === Check: textual installiert? ===
if ! python3 -c "import textual" &> /dev/null; then
    echo -e "${RED}Error: 'textual' not installed in venv.${NC}"
    echo "Updating dependencies..."
    pip install -r "$PCLOUD_TOOLS_DIR/main/requirements.txt"
fi

# === Check: PyYAML installiert? (needed for scripts.yaml catalog) ===
if ! python3 -c "import yaml" &> /dev/null; then
    echo -e "${RED}Warning: 'PyYAML' not installed in venv.${NC}"
    echo "Installing PyYAML..."
    pip install pyyaml
fi

# === App starten ===
echo -e "${GREEN}Starting pCloud Commander...${NC}"
COLORTERM="${COLORTERM:-truecolor}" TERM="${TERM:-xterm-256color}" python3 "$SCRIPT_DIR/pcloud_commander.py" "$@"
