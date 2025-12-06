#!/bin/bash
# =============================================================================
# setup_dev_secrets.sh
# =============================================================================
# Description: Generate cryptographically secure secrets for local development.
# Usage:       ./scripts/setup_dev_secrets.sh
#
# This script creates secret files in the .secrets/ directory for use with
# Docker Compose. Existing secrets with content are preserved to maintain
# data persistence across restarts.
#
# Dependencies: Python 3 (for secure token generation via the secrets module)
# =============================================================================

set -euo pipefail

# === PATH RESOLUTION ===
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."
SECRETS_DIR="$PROJECT_ROOT/.secrets"

echo "📍 Script location: $SCRIPT_DIR"
echo "🔐 Generating secrets in: $SECRETS_DIR"

mkdir -p "$SECRETS_DIR"

# === SECRET GENERATION ===
# Generate a secret file if it does not exist or is empty.
# Use Python's secrets module for cryptographically strong random tokens.
gen_secret() {
    local filename="$1"
    local filepath="$SECRETS_DIR/$filename"

    # Skip generation if the file exists and has content (non-zero size).
    if [ ! -s "$filepath" ]; then
        if [ "$filename" = "pgadmin_password" ]; then
            # pgAdmin uses a default password for local development convenience.
            echo "admin" > "$filepath"
        else
            # Generate a 32-byte (256-bit) hexadecimal token.
            if ! command -v python3 &> /dev/null; then
                echo "❌ Error: python3 is required but not found in PATH." >&2
                exit 1
            fi
            python3 -c "import secrets; print(secrets.token_hex(32), end='')" > "$filepath"
        fi
        echo "   ✅ Created: $filename"
    else
        echo "   ⏭️  Exists: $filename (skipped)"
    fi
}

# === MAIN ===
gen_secret postgres_password
gen_secret redis_password
gen_secret pgadmin_password

echo "✨ Secrets ready."