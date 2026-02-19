# Internal Scripts

This directory contains internal logic used by the project's `Makefile`.

**Do not run these scripts directly.**
Use the `make` commands in the root directory instead.

- `setup_dev_secrets.sh`: Generates cryptographic secrets. Invoked by `make setup`.

## Exception

- `test_core_connection.py`: Standalone smoke test for core provider connectivity
  and tool-calling behavior. This script is meant to be run directly:
  `python scripts/test_core_connection.py`
