import sys
import os
import urllib.request
import urllib.error

# Configuración Dinámica
# Si no hay variables de entorno, usa los defaults seguros (127.0.0.1:8000)
HOST = os.environ.get("HEALTHCHECK_HOST", "127.0.0.1")
PORT = os.environ.get("HEALTHCHECK_PORT", "8000")
URL = f"http://{HOST}:{PORT}/health"
TIMEOUT = 2  # segundos

try:
    # Intenta hacer una petición GET
    with urllib.request.urlopen(URL, timeout=TIMEOUT) as response:
        # Si el código de estado es 200, todo está bien
        if response.status == 200:
            sys.exit(0) # HEALTHY
        else:
            sys.exit(1) # UNHEALTHY

except (urllib.error.URLError, urllib.error.HTTPError):
    # Capturamos errores de red o errores HTTP (404, 500, etc.)
    sys.exit(1)