"""Pruebas integradas del cliente de Ollama con la capa HTTP mockeada (``unittest.mock``).

Verifican el contrato con ``POST /api/chat``: que los parámetros declarados en los ``.md``
viajen en el payload y que las fallas de red/HTTP se traduzcan a ``ErrorLLM``.
"""

import json
from unittest.mock import MagicMock

import pytest
import requests

from bibliotecario.agente import crear_agente
from bibliotecario.llm import ClienteOllama, ErrorLLM
from conftest import RUTA_AGENTE, BibliotecaFalsa


def _respuesta_http(status=200, contenido=None, cuerpo=None):
    respuesta = MagicMock(status_code=status, text="detalle del error")
    respuesta.json.return_value = cuerpo if cuerpo is not None else {
        "message": {"content": json.dumps(contenido or {})},
        "total_duration": 2_500_000_000, "prompt_eval_count": 310, "eval_count": 45,
    }
    return respuesta


def test_chat_json_envia_esquema_opciones_y_keep_alive():
    # Arrange
    sesion = MagicMock()
    sesion.post.return_value = _respuesta_http(contenido={"skill": "catalogar_libro", "motivo": "alta"})
    cliente = ClienteOllama("http://ollama:11434/", sesion=sesion, keep_alive="10m")
    esquema = {"type": "object", "properties": {"skill": {"type": "string"}}}
    # Act
    respuesta = cliente.chat_json("qwen2.5:3b", "sistema", "usuario", esquema, {"temperature": 0.0, "seed": 42})
    # Assert
    url, = sesion.post.call_args.args
    payload = sesion.post.call_args.kwargs["json"]
    assert url == "http://ollama:11434/api/chat"
    assert payload["format"] == esquema
    assert payload["options"] == {"temperature": 0.0, "seed": 42}
    assert payload["stream"] is False and payload["keep_alive"] == "10m"
    assert payload["messages"] == [{"role": "system", "content": "sistema"}, {"role": "user", "content": "usuario"}]
    assert respuesta.contenido == {"skill": "catalogar_libro", "motivo": "alta"}
    assert (respuesta.duracion_s, respuesta.tokens_generados, respuesta.tokens_por_segundo) == (2.5, 45, 18.0)


def test_chat_json_error_http_lanza_error_llm():
    sesion = MagicMock()
    sesion.post.return_value = _respuesta_http(status=404)
    with pytest.raises(ErrorLLM, match="HTTP 404"):
        ClienteOllama(sesion=sesion).chat_json("modelo-inexistente", "s", "u", {}, {})


def test_chat_json_sin_conexion_lanza_error_llm():
    sesion = MagicMock()
    sesion.post.side_effect = requests.ConnectionError("conexión rechazada")
    with pytest.raises(ErrorLLM, match="No se pudo contactar a Ollama"):
        ClienteOllama(sesion=sesion).chat_json("m", "s", "u", {}, {})


def test_chat_json_contenido_no_json_lanza_error_llm():
    sesion = MagicMock()
    sesion.post.return_value = _respuesta_http(cuerpo={"message": {"content": "Hola, soy un modelo"}})
    with pytest.raises(ErrorLLM, match="no contiene un objeto JSON"):
        ClienteOllama(sesion=sesion).chat_json("m", "s", "u", {}, {})


def test_disponible_y_modelos_con_servidor_caido():
    sesion = MagicMock()
    sesion.get.side_effect = requests.ConnectionError()
    cliente = ClienteOllama(sesion=sesion)
    assert cliente.disponible() is False
    assert cliente.modelos() == []


def test_modelos_lista_los_descargados():
    sesion = MagicMock()
    sesion.get.return_value = _respuesta_http(cuerpo={"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:1b"}]})
    assert ClienteOllama(sesion=sesion).modelos() == ["qwen2.5:3b", "llama3.2:1b"]


def test_agente_completo_contra_ollama_mockeado():
    """Agente real + ClienteOllama real + HTTP mockeado: los parámetros de cada .md llegan a Ollama."""
    # Arrange: el "servidor" responde primero al enrutador y luego a la skill
    sesion = MagicMock()
    sesion.post.side_effect = [
        _respuesta_http(contenido={"skill": "gestionar_prestamo", "motivo": "préstamo"}),
        _respuesta_http(contenido={"accion": "prestar", "titulo": "Rayuela", "autor": ""}),
    ]
    agente = crear_agente(RUTA_AGENTE, llm=ClienteOllama(sesion=sesion),
                          cliente=BibliotecaFalsa([{"id": 1, "titulo": "Rayuela", "autor": "Julio Cortázar",
                                                    "genero": "Novela", "anioPublicacion": 1963,
                                                    "estado": "Disponible"}]))
    # Act
    resultado = agente.procesar("me llevo Rayuela")
    # Assert
    enrutador, skill = (c.kwargs["json"] for c in sesion.post.call_args_list)
    assert enrutador["options"]["temperature"] == 0.0 and enrutador["options"]["num_predict"] == 120
    assert skill["options"]["temperature"] == 0.0 and skill["format"]["required"] == ["accion", "titulo", "autor"]
    assert resultado.estado == "pendiente_confirmacion"
