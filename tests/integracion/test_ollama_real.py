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


# Catálogo de `npm run db:seed` con sus ids reales y en el orden de la API (por autor).
# Acá el id 3 es "Ficciones" (cuentos), mientras que en el ejemplo few-shot del .skill.md
# el 3 era "Fahrenheit 451": con ese ejemplo, el modelo copiaba el 3 y recomendaba cuentos.
CATALOGO_SEED = [
    {"id": i, "titulo": t, "autor": a, "genero": g, "anioPublicacion": y, "estado": e}
    for i, t, a, g, y, e in sorted([
        (1, "Rayuela", "Julio Cortázar", "Novela", 1963, "Disponible"),
        (2, "Bestiario", "Julio Cortázar", "Cuentos", 1951, "Disponible"),
        (3, "Ficciones", "Jorge Luis Borges", "Cuentos", 1944, "Disponible"),
        (4, "El Aleph", "Jorge Luis Borges", "Cuentos", 1949, "Prestado"),
        (5, "La invención de Morel", "Adolfo Bioy Casares", "Ciencia ficción", 1940, "Disponible"),
        (6, "El túnel", "Ernesto Sabato", "Novela psicológica", 1948, "Disponible"),
        (7, "Cien años de soledad", "Gabriel García Márquez", "Realismo mágico", 1967, "Disponible"),
        (8, "Fahrenheit 451", "Ray Bradbury", "Ciencia ficción", 1953, "Disponible"),
        (9, "Crónicas marcianas", "Ray Bradbury", "Ciencia ficción", 1950, "Prestado"),
        (10, "1984", "George Orwell", "Distopía", 1949, "Disponible"),
        (11, "Un mundo feliz", "Aldous Huxley", "Distopía", 1932, "Disponible"),
        (12, "Las ventajas de ser invisible", "Stephen Chbosky", "Novela juvenil", 1999, "Disponible"),
        (13, "El principito", "Antoine de Saint-Exupéry", "Fábula", 1943, "Disponible"),
        (14, "Clean Code", "Robert C. Martin", "Programación", 2008, "Disponible"),
        (15, "Diseño de sistemas de datos intensivos", "Martin Kleppmann", "Programación", 2017, "Disponible"),
        (16, "Las cosas que perdimos en el fuego", "Mariana Enriquez", "Terror", 2016, "Disponible"),
    ], key=lambda libro: libro[2])
]


def test_recomendacion_real_no_copia_ids_del_ejemplo_few_shot(agente_real):
    # Arrange
    agente = crear_agente(RUTA_AGENTE, llm=agente_real.llm, cliente=BibliotecaFalsa(CATALOGO_SEED),
                          anio_actual=ANIO_ACTUAL)
    # Act
    resultado = agente.procesar("Recomendame algo de ciencia ficción", skill="recomendar_libros")
    # Assert: solo libros de ciencia ficción disponibles (La invención de Morel y Fahrenheit 451)
    assert resultado.estado == "ok"
    assert {l["genero"] for l in resultado.datos["recomendaciones"]} == {"Ciencia ficción"}
