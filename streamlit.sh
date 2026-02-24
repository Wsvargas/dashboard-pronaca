#!/bin/bash
set -e

cd /home/site/wwwroot

# (Opcional) para que quede evidencia en Log Stream
pwd
ls -la .streamlit || true
ls -la .streamlit/config.toml || true

python3 -m streamlit run dashboard_produccion_ahora.py \
  --server.port 8000 \
  --server.address 0.0.0.0