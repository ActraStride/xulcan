#!/bin/bash
# scripts/setup_dev_secrets.sh

# 1. Detectar ubicación
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/.."
SECRETS_DIR="$PROJECT_ROOT/.secrets"

echo "📍 Script ubicado en: $SCRIPT_DIR"
echo "🔐 Generando secretos en: $SECRETS_DIR"

mkdir -p "$SECRETS_DIR"

# Función helper MEJORADA (Usa Python, cero dependencias de SO raras)
gen_secret() {
    filename=$1
    filepath="$SECRETS_DIR/$filename"
    
    # Si el archivo no existe O está vacío (0 bytes), lo regeneramos
    if [ ! -s "$filepath" ]; then
        if [ "$filename" = "pgadmin_password" ]; then
            echo "admin" > "$filepath"
        else
            # USAMOS PYTHON: Genera un token hexadecimal seguro de 32 bytes
            # Esto funciona en cualquier máquina que tenga Python 3 instalado.
            if ! command -v python3 &> /dev/null; then
                echo "❌ Error: python3 no está instalado o no está en el PATH. Instálalo para continuar." >&2
                exit 1
            fi
            python3 -c "import secrets; print(secrets.token_hex(32), end='')" > "$filepath"
        fi
        echo "   ✅ Creado/Regenerado: $filename"
    else
        echo "   ⏭️  Existe y tiene contenido: $filename (Saltando)"
    fi
}

# Generar los 3 secretos
gen_secret postgres_password
gen_secret redis_password
gen_secret pgadmin_password

echo "✨ Secretos listos y verificados."