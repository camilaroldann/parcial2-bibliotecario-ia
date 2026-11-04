"""Configuración del runtime, sobreescribible por variables de entorno."""

import os
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
BIBLIOTECA_URL = os.environ.get("BIBLIOTECA_URL", "http://localhost:3000/api")
RUTA_AGENTE = Path(os.environ.get("RUTA_AGENTE", RAIZ_PROYECTO / "agente" / "bibliotecario.agent.md"))

TIMEOUT_OLLAMA_S = float(os.environ.get("TIMEOUT_OLLAMA_S", "180"))
TIMEOUT_BIBLIOTECA_S = float(os.environ.get("TIMEOUT_BIBLIOTECA_S", "10"))

# Mantiene el modelo cargado en RAM entre pedidos para evitar el cold start.
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "10m")
