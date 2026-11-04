"""Pruebas integradas contra la API Node.js REAL (Express + SQLite en una base temporal).

El fixture ``api_real`` levanta el servidor en un puerto libre con ``DB_FILE`` apuntando a
``tmp_path``: cada test arranca con una base vacía y no toca la base de la demo.
"""

import pytest

from bibliotecario.api_biblioteca import ClienteBiblioteca, ErrorBiblioteca

RAYUELA = {"titulo": "Rayuela", "autor": "Julio Cortázar", "genero": "Novela", "anioPublicacion": 1963}


@pytest.fixture
def cliente(api_real):
    return ClienteBiblioteca(api_real)


def test_alta_y_listado_ordenado_por_autor(cliente):
    # Arrange
    cliente.crear_libro(RAYUELA)
    cliente.crear_libro({"titulo": "Ficciones", "autor": "Jorge Luis Borges", "genero": "Cuentos", "anioPublicacion": 1944})
    # Act
    libros = cliente.listar_libros()
    # Assert
    assert [l["autor"] for l in libros] == ["Jorge Luis Borges", "Julio Cortázar"]
    assert libros[1]["estado"] == "Disponible"       # valor por defecto de la base


def test_duplicado_con_otra_capitalizacion_devuelve_409(cliente):
    cliente.crear_libro(RAYUELA)
    with pytest.raises(ErrorBiblioteca) as error:
        cliente.crear_libro({**RAYUELA, "titulo": "  RAYUELA ", "autor": "julio cortázar"})
    assert error.value.status == 409


def test_validacion_de_la_api_devuelve_errores_por_campo(cliente):
    with pytest.raises(ErrorBiblioteca) as error:
        cliente.crear_libro({"titulo": "", "autor": "X", "genero": "Y", "anioPublicacion": 3000})
    assert error.value.status == 400
    assert set(error.value.errores) == {"titulo", "anioPublicacion"}


def test_prestamo_y_devolucion(cliente):
    # Arrange
    libro = cliente.crear_libro(RAYUELA)
    # Act
    prestado = cliente.cambiar_estado(libro["id"], "Prestado")
    devuelto = cliente.cambiar_estado(libro["id"], "Disponible")
    # Assert
    assert (prestado["estado"], devuelto["estado"]) == ("Prestado", "Disponible")


def test_prestar_dos_veces_devuelve_409(cliente):
    libro = cliente.crear_libro(RAYUELA)
    cliente.cambiar_estado(libro["id"], "Prestado")
    with pytest.raises(ErrorBiblioteca, match="ya está prestado") as error:
        cliente.cambiar_estado(libro["id"], "Prestado")
    assert error.value.status == 409


@pytest.mark.parametrize("id_libro, estado, status", [(999, "Prestado", 404), (1, "Perdido", 400)])
def test_cambio_de_estado_invalido(cliente, id_libro, estado, status):
    cliente.crear_libro(RAYUELA)
    with pytest.raises(ErrorBiblioteca) as error:
        cliente.cambiar_estado(id_libro, estado)
    assert error.value.status == status


def test_payload_de_inyeccion_sql_se_guarda_como_texto_literal(cliente):
    """La API usa consultas parametrizadas: el payload no se ejecuta, se almacena tal cual."""
    # Arrange
    malicioso = {**RAYUELA, "titulo": "x'); DROP TABLE libros; --"}
    # Act
    cliente.crear_libro(malicioso)
    # Assert
    titulos = [l["titulo"] for l in cliente.listar_libros()]
    assert titulos == ["x'); DROP TABLE libros; --"]


def test_api_caida_lanza_error_biblioteca():
    cliente = ClienteBiblioteca("http://127.0.0.1:9/api", timeout=1)
    assert cliente.disponible() is False
    with pytest.raises(ErrorBiblioteca, match="no responde"):
        cliente.listar_libros()
