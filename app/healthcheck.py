"""HTTP health check probe for container orchestration.

Execute a lightweight HTTP GET request against the application's /health
endpoint. Return appropriate exit codes for container runtime health probes.

Exit Codes:
    0: Healthy - Endpoint returned HTTP 200.
    1: Unhealthy - Connection failed or non-200 response.

Environment Variables:
    HEALTHCHECK_HOST: Target host address (default: 127.0.0.1).
    HEALTHCHECK_PORT: Target port number (default: 8000).
"""

import sys
import os
import urllib.request
import urllib.error

# --- Configuration ---
# Load target endpoint from environment variables with secure defaults.
HOST = os.environ.get("HEALTHCHECK_HOST", "127.0.0.1")
PORT = os.environ.get("HEALTHCHECK_PORT", "8000")
URL = f"http://{HOST}:{PORT}/health"
TIMEOUT = 2  # seconds

# --- Health Probe Execution ---
try:
    with urllib.request.urlopen(URL, timeout=TIMEOUT) as response:
        if response.status == 200:
            sys.exit(0)  # HEALTHY
        else:
            sys.exit(1)  # UNHEALTHY

except (urllib.error.URLError, urllib.error.HTTPError):
    # Handle network errors and non-success HTTP responses (4xx, 5xx).
    sys.exit(1)