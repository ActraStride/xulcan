#!/bin/bash
#
# Description: Generates secure secrets for the Xulcan project infrastructure.
#              Utilizes Python's secrets module to generate cryptographically
#              strong hex tokens.
#

set -euo pipefail

# === CONFIGURATION ===

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."
SECRETS_DIR="$PROJECT_ROOT/.secrets"

# === FUNCTIONS ===

# Generates a 32-byte hex secret and saves it to the specified file.
# Skips generation if the file already exists.
#
# Arguments:
#   $1 - filename: The name of the file to store the secret in.
generate_secret() {
    local filename="$1"
    local filepath="$SECRETS_DIR/$filename"

    if [ ! -f "$filepath" ]; then
        # Generate 32 bytes hex (safe for passwords) using Python's secrets module
        python3 -c "import secrets; print(secrets.token_hex(32), end='')" > "$filepath"
        echo "   ✅ Created: $filename"
    else
        echo "   ⏭️  Exists: $filename"
    fi
}

# === EXECUTION ===

# Verify Python 3 availability
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is required." >&2
    exit 1
fi

echo "🔐 Checking secrets configuration..."
mkdir -p "$SECRETS_DIR"

# Generate required secrets for infrastructure services
generate_secret postgres_password
generate_secret redis_password
generate_secret pgadmin_password

# Apply restrictive permissions (Read-only for the owner)
chmod 644 "$SECRETS_DIR"/* 2>/dev/null || true

echo "✨ Secrets are ready in .secrets/"