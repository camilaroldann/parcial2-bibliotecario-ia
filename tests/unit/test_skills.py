"""Pruebas unitarias de cada skill, aisladas con LLMFalso y BibliotecaFalsa (sin red ni disco)."""

import pytest

from bibliotecario.api_biblioteca import Herramientas
from bibliotecario.llm import ErrorLLM
from bibliotecario.skills import CatalogarLibro, GestionarPrestamo, RecomendarLibros, buscar_libros
from conftest import ANIO_ACTUAL, CATALOGO_EJEMPLO, BibliotecaFalsa, LLMFalso


@pytest.fixture
def construir(definiciones):
    """``construir(Clase, respuestas_llm)`` -> (skill, llm, biblioteca)."""
    _, skills = definiciones

    def _construir(clase, respuestas, libros=CATALOGO_EJEMPLO):
        nombre = {CatalogarLibro: "catalogar_libro", RecomendarLibros: "recomendar_libros",
                  GestionarPrestamo: "gestionar_prestamo"}[clase]
        definicion = skills[nombre]
        llm, biblioteca = LLMFalso(respuestas), BibliotecaFalsa(libros)
        skill = clase(definicion, llm, Herramientas(biblioteca, definicion.herramientas, nombre),
                      "modelo-por-defecto", anio_actual=ANIO_ACTUAL)
        return skill, llm, biblioteca

    return _construir


FICHA_ARLT = {"titulo": "Los siete locos", "autor": "Roberto Arlt", "genero": "Novela",
              "anioPublicacion": 1929, "estado": "Disponible"}


# ===================================================================== catalogar_libro

class TestCatalogarLibro:

    def test_ficha_valida_queda_pendiente_sin_tocar_la_api(self, construir):
        # Arrange
        skill, _, biblioteca = construir(CatalogarLibro, [FICHA_ARLT])
        # Act
        resultado = skill.ejecutar("cargá Los siete locos de Roberto Arlt, novela, 1929")
        # Assert
        assert resultado.estado == "pendiente_confirmacion"
        assert resultado.accion_pendiente == {"herramienta": "crear_libro", "argumentos": {"libro": FICHA_ARLT}}
        assert biblioteca.llamadas == []

    def test_usa_modelo_parametros_y_esquema_del_md(self, construir):
        # Arrange
        skill, llm, _ = construir(CatalogarLibro, [FICHA_ARLT])
        # Act
        skill.ejecutar("cargá Los siete locos")
        # Assert
        llamada = llm.llamadas[0]
        assert llamada["modelo"] == "qwen2.5:3b"
        assert llamada["opciones"]["temperature"] == 0.1
        assert llamada["opciones"]["seed"] == 42
        assert llamada["esquema"]["required"] == ["titulo", "autor", "genero", "anioPublicacion", "estado"]
        assert "<entrada_usuario>" in llamada["usuario"] and f"Año actual: {ANIO_ACTUAL}" in llamada["usuario"]

    def test_confirmar_crea_el_libro_en_la_api(self, construir):
        # Arrange
        skill, _, biblioteca = construir(CatalogarLibro, [FICHA_ARLT])
        pendiente = skill.ejecutar("cargá Los siete locos")
        # Act
        resultado = skill.confirmar(pendiente.accion_pendiente)
        # Assert
        assert resultado.estado == "ok"
        assert resultado.datos["libro"]["id"] == len(CATALOGO_EJEMPLO) + 1
        assert biblioteca.llamadas == [("crear_libro", FICHA_ARLT)]

    def test_datos_faltantes_no_proponen_alta(self, construir):
        # Arrange
        incompleta = {"titulo": "Martín Fierro", "autor": "", "genero": "", "anioPublicacion": None, "estado": "Disponible"}
        skill, _, _ = construir(CatalogarLibro, [incompleta])
        # Act
        resultado = skill.ejecutar("agregá Martín Fierro")
        # Assert
        assert resultado.estado == "faltan_datos"
        assert resultado.accion_pendiente is None
        assert set(resultado.datos["errores"]) == {"autor", "genero", "anioPublicacion"}

    def test_anio_de_dos_cifras_del_modelo_se_completa(self, construir):
        # Arrange
        skill, _, _ = construir(CatalogarLibro, [{**FICHA_ARLT, "anioPublicacion": 29}])
        # Act
        resultado = skill.ejecutar("Los siete locos de Arlt, novela del 29")
        # Assert
        assert resultado.accion_pendiente["argumentos"]["libro"]["anioPublicacion"] == 1929

    def test_anio_futuro_inventado_por_el_modelo_es_rechazado(self, construir):
        skill, _, _ = construir(CatalogarLibro, [{**FICHA_ARLT, "anioPublicacion": 2099}])
        resultado = skill.ejecutar("Los siete locos")
        assert resultado.estado == "faltan_datos"
        assert "no puede ser mayor" in resultado.datos["errores"]["anioPublicacion"]

    def test_duplicado_devuelve_error_de_la_api(self, construir):
        # Arrange
        rayuela = {"titulo": "rayuela", "autor": "julio cortazar", "genero": "Novela",
                   "anioPublicacion": 1963, "estado": "Disponible"}
        skill, _, _ = construir(CatalogarLibro, [rayuela])
        pendiente = skill.ejecutar("cargá rayuela")
        # Act
        resultado = skill.confirmar(pendiente.accion_pendiente)
        # Assert
        assert resultado.estado == "error"
        assert "Ya existe" in resultado.mensaje

    def test_falla_del_modelo_se_traduce_a_error_legible(self, construir):
        skill, _, _ = construir(CatalogarLibro, [ErrorLLM("timeout")])
        resultado = skill.ejecutar_seguro("cargá algo")
        assert resultado.estado == "error"
        assert resultado.mensaje == "El modelo local no pudo responder: timeout"


# ===================================================================== recomendar_libros

class TestRecomendarLibros:

    def test_recomienda_libros_disponibles_del_catalogo(self, construir):
        # Arrange
        salida = {"recomendaciones": [{"id": 3, "motivo": "Distopía"}, {"id": 4, "motivo": "Bioy"}], "mensaje": "Mirá:"}
        skill, llm, _ = construir(RecomendarLibros, [salida])
        # Act
        resultado = skill.ejecutar("ciencia ficción")
        # Assert
        assert resultado.estado == "ok"
        assert [l["titulo"] for l in resultado.datos["recomendaciones"]] == ["Fahrenheit 451", "La invención de Morel"]
        assert "2 | El Aleph" not in llm.llamadas[0]["usuario"]   # prestado: no viaja al prompt

    def test_descarta_ids_inventados_por_el_modelo(self, construir):
        # Arrange: 99 no existe y 2 está prestado
        salida = {"recomendaciones": [{"id": 99, "motivo": "inventado"}, {"id": 2, "motivo": "prestado"},
                                      {"id": 6, "motivo": "Borges"}], "mensaje": "Mirá:"}
        skill, _, _ = construir(RecomendarLibros, [salida])
        # Act
        resultado = skill.ejecutar("cuentos")
        # Assert
        assert [l["id"] for l in resultado.datos["recomendaciones"]] == [6]
        assert any("99" in paso for paso in resultado.traza)

    def test_limita_a_tres_y_elimina_repetidos(self, construir):
        salida = {"recomendaciones": [{"id": i, "motivo": "m"} for i in (1, 1, 3, 4, 5, 6)], "mensaje": "m"}
        skill, _, _ = construir(RecomendarLibros, [salida])
        resultado = skill.ejecutar("lo que sea")
        assert [l["id"] for l in resultado.datos["recomendaciones"]] == [1, 3, 4]

    def test_id_como_texto_numerico_se_acepta(self, construir):
        skill, _, _ = construir(RecomendarLibros, [{"recomendaciones": [{"id": "5", "motivo": "m"}], "mensaje": "m"}])
        resultado = skill.ejecutar("algo psicológico")
        assert resultado.datos["recomendaciones"][0]["titulo"] == "El túnel"

    def test_sin_coincidencias_validas_devuelve_sin_resultados(self, construir):
        skill, _, _ = construir(RecomendarLibros, [{"recomendaciones": [{"id": 42, "motivo": "m"}], "mensaje": "m"}])
        resultado = skill.ejecutar("poesía japonesa")
        assert resultado.estado == "sin_resultados"

    def test_catalogo_sin_disponibles_no_consulta_al_modelo(self, construir):
        # Arrange
        prestados = [{**l, "estado": "Prestado"} for l in CATALOGO_EJEMPLO]
        skill, llm, _ = construir(RecomendarLibros, [], libros=prestados)
        # Act
        resultado = skill.ejecutar("lo que sea")
        # Assert
        assert resultado.estado == "sin_resultados"
        assert llm.llamadas == []

    def test_no_requiere_confirmacion_y_no_modifica_datos(self, construir):
        skill, _, biblioteca = construir(RecomendarLibros, [{"recomendaciones": [], "mensaje": "m"}])
        skill.ejecutar("algo")
        assert biblioteca.llamadas == [("listar_libros",)]


# ===================================================================== gestionar_prestamo

class TestGestionarPrestamo:

    def test_prestar_libro_disponible_queda_pendiente(self, construir):
        # Arrange
        skill, _, _ = construir(GestionarPrestamo, [{"accion": "prestar", "titulo": "rayuela", "autor": ""}])
        # Act
        resultado = skill.ejecutar("me llevo rayuela")
        # Assert
        assert resultado.estado == "pendiente_confirmacion"
        assert resultado.accion_pendiente == {"herramienta": "cambiar_estado",
                                              "argumentos": {"id_libro": 1, "estado": "Prestado"}}

    def test_confirmar_devolucion_actualiza_estado(self, construir):
        # Arrange
        skill, _, biblioteca = construir(GestionarPrestamo, [{"accion": "devolver", "titulo": "el aleph", "autor": ""}])
        pendiente = skill.ejecutar("devolvieron el aleph")
        # Act
        resultado = skill.confirmar(pendiente.accion_pendiente)
        # Assert
        assert resultado.estado == "ok"
        assert resultado.mensaje == "Registré la devolución de «El Aleph»: vuelve a estar disponible."
        assert biblioteca.llamadas[-1] == ("cambiar_estado", 2, "Disponible")

    def test_prestar_libro_ya_prestado_es_error_de_negocio(self, construir):
        skill, _, _ = construir(GestionarPrestamo, [{"accion": "prestar", "titulo": "El Aleph", "autor": ""}])
        resultado = skill.ejecutar("me llevo El Aleph")
        assert resultado.estado == "error"
        assert "ya está prestado" in resultado.mensaje
        assert resultado.accion_pendiente is None

    def test_autor_inventado_por_el_modelo_no_impide_ubicar_el_libro(self, construir):
        skill, _, _ = construir(GestionarPrestamo, [{"accion": "prestar", "titulo": "Rayuela", "autor": "Orlando Belloso"}])
        resultado = skill.ejecutar("me llevo Rayuela")
        assert resultado.datos["libro"]["id"] == 1

    def test_titulo_ambiguo_pide_precision(self, construir):
        skill, _, _ = construir(GestionarPrestamo, [{"accion": "prestar", "titulo": "Ficcion", "autor": ""}])
        resultado = skill.ejecutar("me llevo Ficciones")
        assert resultado.estado == "faltan_datos"
        assert [l["id"] for l in resultado.datos["candidatos"]] == [6, 7]

    def test_titulo_ambiguo_se_resuelve_con_el_autor(self, construir):
        skill, _, _ = construir(GestionarPrestamo, [{"accion": "prestar", "titulo": "Ficcion", "autor": "Borges"}])
        resultado = skill.ejecutar("me llevo Ficciones de Borges")
        assert resultado.accion_pendiente["argumentos"]["id_libro"] == 6

    def test_libro_inexistente_devuelve_sin_resultados(self, construir):
        skill, _, _ = construir(GestionarPrestamo, [{"accion": "prestar", "titulo": "Don Quijote", "autor": ""}])
        resultado = skill.ejecutar("me llevo el Quijote")
        assert resultado.estado == "sin_resultados"

    @pytest.mark.parametrize("salida", [
        {"accion": "vender", "titulo": "Rayuela", "autor": ""},
        {"accion": "prestar", "titulo": "", "autor": ""},
        {},
    ])
    def test_salida_incompleta_o_fuera_de_esquema_pide_datos(self, construir, salida):
        skill, _, biblioteca = construir(GestionarPrestamo, [salida])
        resultado = skill.ejecutar("quiero algo")
        assert resultado.estado == "faltan_datos"
        assert biblioteca.llamadas == []


# ===================================================================== buscar_libros

@pytest.mark.parametrize("consulta, esperado", [
    ("El túnel", [5]),
    ("el tunel", [5]),
    ("tunel", [5]),
    ("FAHRENHEIT", [3]),
    ("la invencion de morell", [4]),     # errata: difflib la encuentra
    ("Don Quijote", []),
    ("", []),
])
def test_buscar_libros_por_titulo(consulta, esperado):
    assert [l["id"] for l in buscar_libros(CATALOGO_EJEMPLO, consulta)] == esperado
