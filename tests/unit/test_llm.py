"""Pruebas unitarias del parseo de respuestas del modelo."""

import pytest

from bibliotecario.llm import ErrorLLM, RespuestaLLM, extraer_json


@pytest.mark.parametrize("texto", [
    '{"skill": "catalogar_libro"}',
    '```json\n{"skill": "catalogar_libro"}\n```',
    'Claro, acá está: {"skill": "catalogar_libro"} ¡Saludos!',
    '  \n{"skill":\n "catalogar_libro"}  ',
], ids=["json_puro", "bloque_markdown", "texto_alrededor", "saltos_de_linea"])
def test_extraer_json_tolera_formatos_habituales_del_modelo(texto):
    # Act
    datos = extraer_json(texto)
    # Assert
    assert datos == {"skill": "catalogar_libro"}


@pytest.mark.parametrize("texto, mensaje", [
    ("", "vacía"),
    (None, "vacía"),
    ("no hay json acá", "no contiene"),
    ('{"skill": "x",}', "no es JSON válido"),
    ('[{"skill": "x"}]', "objeto JSON"),
])
def test_extraer_json_respuestas_invalidas_lanzan_error(texto, mensaje):
    with pytest.raises(ErrorLLM, match=mensaje):
        extraer_json(texto)


def test_tokens_por_segundo_calcula_velocidad():
    respuesta = RespuestaLLM(contenido={}, texto_crudo="{}", modelo="m", duracion_s=2.0, tokens_generados=37)
    assert respuesta.tokens_por_segundo == 18.5


def test_tokens_por_segundo_sin_duracion_es_cero():
    assert RespuestaLLM(contenido={}, texto_crudo="{}", modelo="m").tokens_por_segundo == 0.0
