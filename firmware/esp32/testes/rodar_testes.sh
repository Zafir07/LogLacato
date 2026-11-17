#!/bin/sh
# Compila e roda os testes do firmware no PC e confere o JSON contra o backend.
#   ./rodar_testes.sh [pasta do ArduinoJson/src]
# Padrão: a biblioteca instalada pela Arduino IDE (~/Arduino/libraries/ArduinoJson/src).
set -e
cd "$(dirname "$0")"
AJ="${1:-$HOME/Arduino/libraries/ArduinoJson/src}"
g++ -std=c++17 -Wall -Wextra -O1 -I"$AJ" teste_firmware.cpp ../loglacto_tbeam/fila.cpp -o teste_firmware
./teste_firmware
# O JSON gerado passa na validação do backend? (precisa do Python com as dependências do backend)
if python -c "import pydantic, sqlalchemy" 2>/dev/null; then
  PYTHONPATH=../../../backend python valida_no_backend.py
else
  echo "(pulei a validação no backend: rode dentro do container ou com o venv do backend)"
fi
