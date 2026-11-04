"""Dobles de prueba y fixtures compartidos.

- ``LLMFalso``: stub del modelo; devuelve respuestas predefinidas en orden y registra cada llamada.
- ``BibliotecaFalsa``: API en memoria con las mismas reglas que la real (409 por duplicado, etc.).
- ``api_real``: levanta la API Node.js real con una base SQLite temporal (pruebas integradas).
"""

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

from bibliotecario.agente import Agente
from bibliotecario.api_biblioteca import ErrorBiblioteca
from bibliotecario.definiciones import cargar_definiciones
from bibliotecario.llm import RespuestaLLM
from bibliotecario.validacion import normalizar

RAIZ = Path(__file__).resolve().parents[1]
RUTA_AGENTE = RAIZ / "agente" / "bibliotecario.agent.md"
DIR_BIBLIOTECA = RAIZ / "biblioteca-virtual"
ANIO_ACTUAL = 2026


class LLMFalso:
    """Stub de ``ClienteOllama``: cada llamada consume la siguiente respuesta de la cola."""

    def __init__(self, respuestas=None):
        self.respuestas = list(respuestas or [])
        self.llamadas = []

    def disponible(self):
        return True

    def chat_json(self, modelo, sistema, usuario, esquema, opciones):
        self.llamadas.append({"modelo": modelo, "sistema": sistema, "usuario": usuario,
                              "esquema": esquema, "opciones": opciones})
        if not self.respuestas:
            raise AssertionError("El LLM falso recibió una llamada no prevista por el test.")
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return RespuestaLLM(contenido=respuesta, texto_crudo=json.dumps(respuesta), modelo=modelo,
                            opciones=dict(opciones), duracion_s=0.5, tokens_prompt=100, tokens_generados=20)


class BibliotecaFalsa:
    """Stub de ``ClienteBiblioteca`` con estado en memoria."""

    def __init__(self, libros=None):
        self.libros = [dict(l) for l in (libros or [])]
        self.llamadas = []

    def disponible(self):
        return True

    def listar_libros(self):
        self.llamadas.append(("listar_libros",))
        return [dict(l) for l in self.libros]

    def crear_libro(self, libro):
        self.llamadas.append(("crear_libro", libro))
        clave = (normalizar(libro["titulo"]), normalizar(libro["autor"]))
        if any((normalizar(l["titulo"]), normalizar(l["autor"])) == clave for l in self.libros):
            raise ErrorBiblioteca("Ya existe un libro con ese título y autor.", status=409)
        nuevo = {**libro, "id": len(self.libros) + 1, "creadoEn": "2026-11-04 10:00:00"}
        self.libros.append(nuevo)
        return dict(nuevo)

    def cambiar_estado(self, id_libro, estado):
        self.llamadas.append(("cambiar_estado", id_libro, estado))
        for libro in self.libros:
            if libro["id"] == id_libro:
                if libro["estado"] == estado:
                    raise ErrorBiblioteca(f"El libro \"{libro['titulo']}\" ya está {estado.lower()}.", status=409)
                libro["estado"] = estado
                return dict(libro)
        raise ErrorBiblioteca(f"No existe un libro con id {id_libro}.", status=404)


CATALOGO_EJEMPLO = [
    {"id": 1, "titulo": "Rayuela", "autor": "Julio Cortázar", "genero": "Novela", "anioPublicacion": 1963, "estado": "Disponible"},
    {"id": 2, "titulo": "El Aleph", "autor": "Jorge Luis Borges", "genero": "Cuentos", "anioPublicacion": 1949, "estado": "Prestado"},
    {"id": 3, "titulo": "Fahrenheit 451", "autor": "Ray Bradbury", "genero": "Ciencia ficción", "anioPublicacion": 1953, "estado": "Disponible"},
    {"id": 4, "titulo": "La invención de Morel", "autor": "Adolfo Bioy Casares", "genero": "Ciencia ficción", "anioPublicacion": 1940, "estado": "Disponible"},
    {"id": 5, "titulo": "El túnel", "autor": "Ernesto Sabato", "genero": "Novela psicológica", "anioPublicacion": 1948, "estado": "Disponible"},
    {"id": 6, "titulo": "Ficciones", "autor": "Jorge Luis Borges", "genero": "Cuentos", "anioPublicacion": 1944, "estado": "Disponible"},
    {"id": 7, "titulo": "Ficciones de la ciudad", "autor": "Ana Pérez", "genero": "Cuentos", "anioPublicacion": 2010, "estado": "Disponible"},
]


@pytest.fixture
def definiciones():
    """Definiciones reales leídas de ``agente/*.md``."""
    return cargar_definiciones(RUTA_AGENTE)


@pytest.fixture
def biblioteca():
    return BibliotecaFalsa(CATALOGO_EJEMPLO)


@pytest.fixture
def crear_agente_falso(definiciones):
    """Fábrica: ``crear_agente_falso(respuestas_llm, cliente=None)`` -> (agente, llm, cliente)."""

    def _crear(respuestas, cliente=None):
        llm = LLMFalso(respuestas)
        cliente = cliente if cliente is not None else BibliotecaFalsa(CATALOGO_EJEMPLO)
        agente = Agente(*definiciones, llm=llm, cliente=cliente, anio_actual=ANIO_ACTUAL)
        return agente, llm, cliente

    return _crear


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def api_real(tmp_path):
    """Levanta la API Node.js real con una base SQLite vacía y temporal; devuelve su URL base."""
    node = shutil.which("node")
    if not node or not (DIR_BIBLIOTECA / "node_modules").is_dir():
        pytest.skip("Requiere Node.js y `npm install` en biblioteca-virtual/.")
    puerto = _puerto_libre()
    entorno = {**os.environ, "PORT": str(puerto), "DB_FILE": str(tmp_path / "test.db")}
    proceso = subprocess.Popen([node, "--disable-warning=ExperimentalWarning", "src/server.js"],
                               cwd=DIR_BIBLIOTECA, env=entorno,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{puerto}/api"
    try:
        for _ in range(50):
            try:
                if requests.get(f"{url}/health", timeout=0.5).ok:
                    break
            except requests.RequestException:
                time.sleep(0.2)
        else:
            pytest.fail("La API de la biblioteca no arrancó a tiempo.")
        yield url
    finally:
        proceso.terminate()
        proceso.wait(timeout=10)
