"""Pruebas unitarias del cargador declarativo (frontmatter YAML de agentes y skills)."""

import pytest

from bibliotecario.definiciones import (
    DefinicionInvalida,
    cargar_definiciones,
    parsear_agente,
    parsear_skill,
    separar_frontmatter,
    validar_opciones,
)
from conftest import RUTA_AGENTE

SKILL_MINIMA = """---
name: skill_prueba
description: "Skill de prueba"
output_schema:
  type: object
  properties:
    dato: {type: string}
---
# Instrucciones
Hacé algo.
"""


def _skill_con(**reemplazos) -> str:
    texto = SKILL_MINIMA
    for viejo, nuevo in reemplazos.items():
        texto = texto.replace(viejo, nuevo)
    return texto


# --------------------------------------------------------------------- separar_frontmatter

def test_separar_frontmatter_devuelve_metadatos_y_cuerpo():
    # Arrange
    texto = "---\nname: x\nmodel: m\n---\n# Cuerpo\nTexto"
    # Act
    metadatos, cuerpo = separar_frontmatter(texto)
    # Assert
    assert metadatos == {"name": "x", "model": "m"}
    assert cuerpo == "# Cuerpo\nTexto"


def test_separar_frontmatter_tolera_bom_y_saltos_windows():
    # Arrange
    texto = "﻿---\r\nname: x\r\n---\r\nCuerpo\r\n"
    # Act
    metadatos, cuerpo = separar_frontmatter(texto)
    # Assert
    assert metadatos == {"name": "x"}
    assert cuerpo == "Cuerpo"


@pytest.mark.parametrize("texto", ["# Sin frontmatter", "---\nname: x\n", "", "--- name: x ---"],
                         ids=["sin_guiones", "sin_cierre", "vacio", "en_una_linea"])
def test_separar_frontmatter_sin_delimitadores_lanza_excepcion(texto):
    # Arrange / Act / Assert
    with pytest.raises(DefinicionInvalida, match="frontmatter"):
        separar_frontmatter(texto)


@pytest.mark.parametrize("yaml_invalido", ["name: [sin cerrar", "- solo\n- una lista", "texto plano"],
                         ids=["yaml_roto", "lista", "escalar"])
def test_separar_frontmatter_yaml_invalido_o_no_mapa_lanza_excepcion(yaml_invalido):
    # Arrange
    texto = f"---\n{yaml_invalido}\n---\ncuerpo"
    # Act / Assert
    with pytest.raises(DefinicionInvalida):
        separar_frontmatter(texto)


def test_separar_frontmatter_bloquea_tags_python_de_yaml():
    # Arrange: payload clásico de deserialización insegura (yaml.load ejecutaría os.system)
    texto = "---\nname: !!python/object/apply:os.system ['echo hackeado']\n---\ncuerpo"
    # Act / Assert: safe_load lo rechaza
    with pytest.raises(DefinicionInvalida, match="YAML"):
        separar_frontmatter(texto)


def test_separar_frontmatter_con_contenido_no_texto_lanza_excepcion():
    with pytest.raises(DefinicionInvalida, match="texto"):
        separar_frontmatter(None)


# --------------------------------------------------------------------- validar_opciones

def test_validar_opciones_acepta_parametros_validos():
    # Arrange
    opciones = {"temperature": 0.1, "top_p": 0.9, "num_ctx": 2048, "seed": 42, "num_predict": 100}
    # Act
    resultado = validar_opciones(opciones)
    # Assert
    assert resultado == opciones


@pytest.mark.parametrize("opciones, mensaje", [
    ({"temperatura": 0.1}, "desconocida"),
    ({"temperature": 2.5}, "entre"),
    ({"temperature": -0.1}, "entre"),
    ({"num_ctx": 100}, "entre"),
    ({"seed": "42"}, "tipo"),
    ({"num_ctx": 2048.5}, "tipo"),
    ({"temperature": True}, "tipo"),
])
def test_validar_opciones_invalidas_lanza_excepcion(opciones, mensaje):
    with pytest.raises(DefinicionInvalida, match=mensaje):
        validar_opciones(opciones)


def test_validar_opciones_none_devuelve_vacio():
    assert validar_opciones(None) == {}


def test_validar_opciones_no_mapa_lanza_excepcion():
    with pytest.raises(DefinicionInvalida, match="mapa"):
        validar_opciones([("temperature", 0.1)])


# --------------------------------------------------------------------- parsear_skill / parsear_agente

def test_parsear_skill_minima_aplica_valores_por_defecto():
    # Act
    skill = parsear_skill(SKILL_MINIMA)
    # Assert
    assert skill.nombre == "skill_prueba"
    assert skill.requiere_confirmacion is False
    assert skill.herramientas == ()
    assert skill.instrucciones.startswith("# Instrucciones")


@pytest.mark.parametrize("reemplazo, mensaje", [
    ({"name: skill_prueba": "name: Skill-Con-Guiones"}, "snake_case"),
    ({'description: "Skill de prueba"\n': ""}, "description"),
    ({"type: object": "type: array"}, "output_schema"),
    ({"# Instrucciones\nHacé algo.\n": ""}, "instrucciones"),
    ({"name: skill_prueba": "name: skill_prueba\ncommand: catalogar"}, "comando"),
    ({"name: skill_prueba": "name: skill_prueba\nrequires_confirmation: quizas"}, "requires_confirmation"),
    ({"name: skill_prueba": "name: skill_prueba\ntools: crear_libro"}, "tools"),
])
def test_parsear_skill_con_estructura_invalida_lanza_excepcion(reemplazo, mensaje):
    # Arrange
    texto = _skill_con(**reemplazo)
    # Act / Assert
    with pytest.raises(DefinicionInvalida, match=mensaje):
        parsear_skill(texto)


def test_parsear_agente_sin_skills_lanza_excepcion():
    texto = "---\nname: A\ndescription: d\nmodel: m\nskills: []\n---\ncuerpo"
    with pytest.raises(DefinicionInvalida, match="al menos una skill"):
        parsear_agente(texto)


def test_parsear_agente_con_skills_repetidas_lanza_excepcion():
    texto = "---\nname: A\ndescription: d\nmodel: m\nskills: [uno_a, uno_a]\n---\ncuerpo"
    with pytest.raises(DefinicionInvalida, match="repetidas"):
        parsear_agente(texto)


def test_parsear_agente_sin_modelo_lanza_excepcion():
    texto = "---\nname: A\ndescription: d\nskills: [uno_a]\n---\ncuerpo"
    with pytest.raises(DefinicionInvalida, match="model"):
        parsear_agente(texto)


# --------------------------------------------------------------------- cargar_definiciones (archivos reales)

def test_cargar_definiciones_reales_del_proyecto():
    # Act
    agente, skills = cargar_definiciones(RUTA_AGENTE)
    # Assert
    assert agente.nombre == "Bibliotecario"
    assert set(skills) == {"catalogar_libro", "recomendar_libros", "gestionar_prestamo"}
    assert agente.opciones["temperature"] == 0.0
    assert all(s.opciones["seed"] == 42 for s in skills.values())
    assert skills["recomendar_libros"].requiere_confirmacion is False
    assert skills["catalogar_libro"].herramientas == ("crear_libro",)


def test_cargar_definiciones_skill_declarada_sin_archivo_lanza_excepcion(tmp_path):
    # Arrange
    ruta = tmp_path / "a.agent.md"
    ruta.write_text("---\nname: A\ndescription: d\nmodel: m\nskills: [fantasma]\n---\ncuerpo", encoding="utf-8")
    # Act / Assert
    with pytest.raises(DefinicionInvalida, match="no existe"):
        cargar_definiciones(ruta)


def test_cargar_definiciones_nombre_de_skill_no_coincide_lanza_excepcion(tmp_path):
    # Arrange
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "otra_skill.skill.md").write_text(SKILL_MINIMA, encoding="utf-8")
    ruta = tmp_path / "a.agent.md"
    ruta.write_text("---\nname: A\ndescription: d\nmodel: m\nskills: [otra_skill]\n---\ncuerpo", encoding="utf-8")
    # Act / Assert
    with pytest.raises(DefinicionInvalida, match="en vez de"):
        cargar_definiciones(ruta)


def test_cargar_definiciones_archivo_inexistente_lanza_excepcion(tmp_path):
    with pytest.raises(DefinicionInvalida, match="No existe"):
        cargar_definiciones(tmp_path / "no_existe.agent.md")
