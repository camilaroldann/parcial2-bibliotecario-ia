"""Cliente mínimo de Ollama (``/api/chat``) con salida JSON estructurada."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import requests

from bibliotecario import config


class ErrorLLM(RuntimeError):
    """El modelo no respondió o su respuesta no se pudo interpretar."""


@dataclass
class RespuestaLLM:
    """Respuesta parseada del modelo junto con su telemetría."""

    contenido: dict
    texto_crudo: str
    modelo: str
    opciones: dict = field(default_factory=dict)
    duracion_s: float = 0.0
    tokens_prompt: int = 0
    tokens_generados: int = 0

    @property
    def tokens_por_segundo(self) -> float:
        """Velocidad de generación aproximada (tokens / segundo)."""
        return round(self.tokens_generados / self.duracion_s, 2) if self.duracion_s else 0.0


def extraer_json(texto: str) -> dict:
    """Extrae el primer objeto JSON de la respuesta del modelo.

    Tolera bloques de código Markdown y texto alrededor del objeto.

    Raises:
        ErrorLLM: si no hay un objeto JSON válido.
    """
    if not isinstance(texto, str) or not texto.strip():
        raise ErrorLLM("El modelo devolvió una respuesta vacía.")
    limpio = re.sub(r"```(?:json)?", "", texto).strip()
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError:
        pass  # puede haber texto alrededor: se busca el objeto más abajo
    else:
        if not isinstance(datos, dict):
            raise ErrorLLM("La respuesta del modelo no es un objeto JSON.")
        return datos
    inicio, fin = limpio.find("{"), limpio.rfind("}")
    if inicio == -1 or fin <= inicio:
        raise ErrorLLM("La respuesta del modelo no contiene un objeto JSON.")
    try:
        datos = json.loads(limpio[inicio:fin + 1])
    except json.JSONDecodeError as error:
        raise ErrorLLM(f"La respuesta del modelo no es JSON válido: {error.msg}.") from error
    if not isinstance(datos, dict):
        raise ErrorLLM("La respuesta del modelo no es un objeto JSON.")
    return datos


class ClienteOllama:
    """Habla con un servidor Ollama local. La sesión HTTP es inyectable para poder testear."""

    def __init__(self, url_base: str = config.OLLAMA_URL, timeout: float = config.TIMEOUT_OLLAMA_S,
                 keep_alive: str = config.KEEP_ALIVE, sesion: requests.Session | None = None):
        self.url_base = url_base.rstrip("/")
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.sesion = sesion or requests.Session()

    def disponible(self) -> bool:
        """``True`` si el servidor de Ollama responde."""
        try:
            return self.sesion.get(f"{self.url_base}/api/tags", timeout=2).status_code == 200
        except requests.RequestException:
            return False

    def modelos(self) -> list[str]:
        """Nombres de los modelos descargados localmente (vacío si Ollama no responde)."""
        try:
            respuesta = self.sesion.get(f"{self.url_base}/api/tags", timeout=2)
            respuesta.raise_for_status()
            return [m["name"] for m in respuesta.json().get("models", [])]
        except (requests.RequestException, ValueError, KeyError):
            return []

    def chat_json(self, modelo: str, sistema: str, usuario: str, esquema: dict, opciones: dict) -> RespuestaLLM:
        """Envía un chat de un turno y obliga al modelo a responder con el JSON ``esquema``.

        Raises:
            ErrorLLM: ante errores de red, HTTP o una respuesta que no es JSON.
        """
        payload = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "stream": False,
            "format": esquema,           # structured outputs: el modelo solo puede emitir este esquema
            "options": dict(opciones),
            "keep_alive": self.keep_alive,
        }
        try:
            respuesta = self.sesion.post(f"{self.url_base}/api/chat", json=payload, timeout=self.timeout)
        except requests.RequestException as error:
            raise ErrorLLM(f"No se pudo contactar a Ollama en {self.url_base}: {error.__class__.__name__}.") from error
        if respuesta.status_code != 200:
            raise ErrorLLM(f"Ollama respondió HTTP {respuesta.status_code}: {respuesta.text[:200]}")
        try:
            cuerpo = respuesta.json()
        except ValueError as error:
            raise ErrorLLM("Ollama devolvió una respuesta que no es JSON.") from error

        texto = (cuerpo.get("message") or {}).get("content", "")
        return RespuestaLLM(
            contenido=extraer_json(texto),
            texto_crudo=texto,
            modelo=modelo,
            opciones=dict(opciones),
            duracion_s=round(cuerpo.get("total_duration", 0) / 1e9, 2),
            tokens_prompt=cuerpo.get("prompt_eval_count", 0),
            tokens_generados=cuerpo.get("eval_count", 0),
        )
