#!/bin/bash
# =============================================================================
# setup_dev_secrets.sh
# =============================================================================
# Description: Generate cryptographically secure secrets for local development.
# Usage:       ./scripts/setup_dev_secrets.sh [--show-password]
#
# This script creates 256-bit secret files in the .secrets/ directory.
#
# Dependencies: Python 3 (for secure token generation)
# =============================================================================

set -euo pipefail

# === PRE-FLIGHT CHECKS ===
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: 'python3' is required but not found in PATH." >&2
    exit 1
fi

# === PATH RESOLUTION ===
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."
SECRETS_DIR="$PROJECT_ROOT/.secrets"

echo "🔐 Generating secrets in: $SECRETS_DIR"
mkdir -p "$SECRETS_DIR"

# === SECRET GENERATION ===
gen_secret() {
    local filename="$1"
    local filepath="$SECRETS_DIR/$filename"

    if [ ! -s "$filepath" ]; then
        # Generate a 32-byte (256-bit) hexadecimal token for production-grade security.
        python3 -c "import secrets; print(secrets.token_hex(32), end='')" > "$filepath"
        echo "   ✅ Created: $filename"
    else
        echo "   ⏭️  Exists: $filename (skipped)"
    fi
}

# === MAIN EXECUTION ===
gen_secret postgres_password
gen_secret redis_password
gen_secret pgadmin_password

echo "✨ Secrets ready."

# === OPTIONAL PASSWORD DISPLAY (with confirmation prompt) ===
if [ "${1:-}" = "--show-password" ]; then
    echo "⚠️  WARNING: Displaying secrets can expose them in logs and history."
    printf "Are you sure you want to display the pgAdmin password? (y/N): "
    read -r confirm

    # Use POSIX-compliant case statement instead of bash-specific regex
    case "$confirm" in
        [yY]|[yY][eE][sS])
            echo "🔑 pgAdmin Password: $(cat "$SECRETS_DIR/pgadmin_password")"
            ;;
        *)
            echo "❌ Password display aborted by user."
            ;;
    esac
else
    echo "🔑 The pgAdmin password is stored securely in:"
    echo "   $SECRETS_DIR/pgadmin_password"
fi