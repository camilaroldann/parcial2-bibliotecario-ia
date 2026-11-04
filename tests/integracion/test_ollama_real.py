"""Pruebas contra el modelo REAL de Ollama (lentas, ~1 min). Ejecutar con:  pytest -m ollama -v

Comprueban que, con los parámetros declarados (temperature baja + seed fija), el agente
elige la skill correcta y responde lo mismo ante la misma entrada.
"""

import pytest

from bibliotecario.agente import crear_agente
from bibliotecario.llm import ClienteOllama
from conftest import ANIO_ACTUAL, CATALOGO_EJEMPLO, RUTA_AGENTE, BibliotecaFalsa

pytestmark = pytest.mark.ollama


@pytest.fixture(scope="module")
def agente_real():
    llm = ClienteOllama()
    if not llm.disponible():
        pytest.skip("Ollama no está corriendo en localhost:11434.")
    agente = crear_agente(RUTA_AGENTE, llm=llm, cliente=BibliotecaFalsa(CATALOGO_EJEMPLO), anio_actual=ANIO_ACTUAL)
    if agente.definicion.modelo not in llm.modelos():
        pytest.skip(f"Falta el modelo: ollama pull {agente.definicion.modelo}")
    return agente


@pytest.mark.parametrize("pedido, skill_esperada", [
    ("Cargá Los siete locos de Roberto Arlt, novela, 1929", "catalogar_libro"),
    ("Recomendame algo de ciencia ficción", "recomendar_libros"),
    ("Me llevo Rayuela", "gestionar_prestamo"),
    ("Devolvieron El Aleph", "gestionar_prestamo"),
    ("¿Qué hora es en Tokio?", "ninguna"),
])
def test_enrutador_real_elige_la_skill_correcta(agente_real, pedido, skill_esperada):
    # Act
    skill, _, _ = agente_real.enrutar(pedido)
    # Assert
    assert skill == skill_esperada


def test_extraccion_real_es_determinista(agente_real):
    # Arrange
    pedido = "Cargá Los siete locos de Roberto Arlt, novela, 1929"
    # Act
    primera = agente_real.procesar(pedido, skill="catalogar_libro")
    segunda = agente_real.procesar(pedido, skill="catalogar_libro")
    # Assert
    assert primera.salida_llm == segunda.salida_llm
    assert primera.accion_pendiente["argumentos"]["libro"] == {
        "titulo": "Los siete locos", "autor": "Roberto Arlt", "genero": "Novela",
        "anioPublicacion": 1929, "estado": "Disponible"}


def test_recomendacion_real_solo_usa_ids_del_catalogo(agente_real):
    resultado = agente_real.procesar("quiero ciencia ficción", skill="recomendar_libros")
    ids_catalogo = {l["id"] for l in CATALOGO_EJEMPLO if l["estado"] == "Disponible"}
    assert resultado.estado == "ok"
    assert {l["id"] for l in resultado.datos["recomendaciones"]} <= ids_catalogo
