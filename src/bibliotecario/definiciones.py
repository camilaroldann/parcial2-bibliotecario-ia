"""Carga declarativa del agente y sus skills desde Markdown con frontmatter YAML.

El comportamiento del agente (modelo, parámetros de muestreo, skills habilitadas,
herramientas permitidas y esquema de salida) se define en archivos ``.md``; este
módulo los lee, valida su estructura y los convierte en objetos inmutables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Parámetros de inferencia de Ollama que aceptamos en el frontmatter, con su rango válido.
OPCIONES_PERMITIDAS: dict[str, tuple[type | tuple[type, ...], float, float]] = {
    "temperature": ((int, float), 0.0, 2.0),
    "top_p": ((int, float), 0.0, 1.0),
    "top_k": (int, 1, 500),
    "num_ctx": (int, 256, 32768),
    "num_predict": (int, 1, 4096),
    "seed": (int, 0, 2**31 - 1),
    "repeat_penalty": ((int, float), 0.0, 3.0),
}

_PATRON_FRONTMATTER = re.compile(r"\A---[ \t]*\n(?P<yaml>.*?)\n---[ \t]*(?:\n(?P<cuerpo>.*))?\Z", re.DOTALL)
_PATRON_NOMBRE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


class DefinicionInvalida(ValueError):
    """El archivo de definición no respeta la estructura esperada."""


@dataclass(frozen=True)
class DefinicionSkill:
    """Contrato de una skill: qué hace, con qué modelo, qué puede tocar y qué devuelve."""

    nombre: str
    descripcion: str
    instrucciones: str
    esquema_salida: dict
    modelo: str | None = None
    opciones: dict = field(default_factory=dict)
    herramientas: tuple[str, ...] = ()
    comando: str | None = None
    requiere_confirmacion: bool = False
    entradas: dict = field(default_factory=dict)
    version: str = "1.0.0"
    ruta: Path | None = None


@dataclass(frozen=True)
class DefinicionAgente:
    """Contrato del agente orquestador: rol, modelo por defecto y skills habilitadas."""

    nombre: str
    descripcion: str
    instrucciones: str
    modelo: str
    skills: tuple[str, ...]
    opciones: dict = field(default_factory=dict)
    herramientas: tuple[str, ...] = ()
    version: str = "1.0.0"
    ruta: Path | None = None


def separar_frontmatter(texto: str) -> tuple[dict, str]:
    """Separa el frontmatter YAML del cuerpo Markdown.

    Usa ``yaml.safe_load`` (nunca ``yaml.load``) para que un archivo de definición
    no pueda instanciar objetos de Python arbitrarios.

    Raises:
        DefinicionInvalida: si no hay frontmatter, el YAML es inválido o no es un mapa.
    """
    if not isinstance(texto, str):
        raise DefinicionInvalida("El contenido de la definición debe ser texto.")
    normalizado = texto.lstrip("﻿").replace("\r\n", "\n")
    coincidencia = _PATRON_FRONTMATTER.match(normalizado)
    if not coincidencia:
        raise DefinicionInvalida("El archivo no tiene frontmatter YAML delimitado por '---'.")
    try:
        metadatos = yaml.safe_load(coincidencia.group("yaml"))
    except yaml.YAMLError as error:
        raise DefinicionInvalida(f"El frontmatter no es YAML válido: {error}") from error
    if not isinstance(metadatos, dict):
        raise DefinicionInvalida("El frontmatter debe ser un mapa clave: valor.")
    return metadatos, (coincidencia.group("cuerpo") or "").strip()


def validar_opciones(opciones: object, origen: str = "definición") -> dict:
    """Valida los parámetros de muestreo contra ``OPCIONES_PERMITIDAS``.

    Raises:
        DefinicionInvalida: si hay claves desconocidas, tipos incorrectos o valores fuera de rango.
    """
    if opciones is None:
        return {}
    if not isinstance(opciones, dict):
        raise DefinicionInvalida(f"'options' de {origen} debe ser un mapa.")
    validadas = {}
    for clave, valor in opciones.items():
        if clave not in OPCIONES_PERMITIDAS:
            raise DefinicionInvalida(f"Opción desconocida '{clave}' en {origen}.")
        tipos, minimo, maximo = OPCIONES_PERMITIDAS[clave]
        if isinstance(valor, bool) or not isinstance(valor, tipos):
            raise DefinicionInvalida(f"La opción '{clave}' de {origen} tiene un tipo inválido.")
        if not minimo <= valor <= maximo:
            raise DefinicionInvalida(f"La opción '{clave}' de {origen} debe estar entre {minimo} y {maximo}.")
        validadas[clave] = valor
    return validadas


def _texto_obligatorio(metadatos: dict, clave: str, origen: str) -> str:
    valor = metadatos.get(clave)
    if not isinstance(valor, str) or not valor.strip():
        raise DefinicionInvalida(f"Falta el campo obligatorio '{clave}' en {origen}.")
    return valor.strip()


def _lista_de_textos(metadatos: dict, clave: str, origen: str) -> tuple[str, ...]:
    valor = metadatos.get(clave) or []
    if not isinstance(valor, list) or not all(isinstance(v, str) and v.strip() for v in valor):
        raise DefinicionInvalida(f"'{clave}' de {origen} debe ser una lista de textos.")
    return tuple(v.strip() for v in valor)


def parsear_skill(texto: str, ruta: Path | None = None) -> DefinicionSkill:
    """Convierte el contenido de un ``.skill.md`` en una ``DefinicionSkill`` validada."""
    origen = str(ruta) if ruta else "la skill"
    metadatos, cuerpo = separar_frontmatter(texto)

    nombre = _texto_obligatorio(metadatos, "name", origen)
    if not _PATRON_NOMBRE.match(nombre):
        raise DefinicionInvalida(f"El nombre de skill '{nombre}' debe ser snake_case (a-z, 0-9, _).")
    if not cuerpo:
        raise DefinicionInvalida(f"La skill '{nombre}' no tiene instrucciones en el cuerpo Markdown.")

    esquema = metadatos.get("output_schema")
    if not isinstance(esquema, dict) or esquema.get("type") != "object" or "properties" not in esquema:
        raise DefinicionInvalida(f"La skill '{nombre}' necesita un 'output_schema' de tipo object con properties.")

    comando = metadatos.get("command")
    if comando is not None and (not isinstance(comando, str) or not re.fullmatch(r"/[a-z]{2,20}", comando)):
        raise DefinicionInvalida(f"El comando de '{nombre}' debe tener la forma /palabra.")

    confirmacion = metadatos.get("requires_confirmation", False)
    if not isinstance(confirmacion, bool):
        raise DefinicionInvalida(f"'requires_confirmation' de '{nombre}' debe ser true o false.")

    return DefinicionSkill(
        nombre=nombre,
        descripcion=_texto_obligatorio(metadatos, "description", origen),
        instrucciones=cuerpo,
        esquema_salida=esquema,
        modelo=metadatos.get("model"),
        opciones=validar_opciones(metadatos.get("options"), origen),
        herramientas=_lista_de_textos(metadatos, "tools", origen),
        comando=comando,
        requiere_confirmacion=confirmacion,
        entradas=metadatos.get("inputs") or {},
        version=str(metadatos.get("version", "1.0.0")),
        ruta=ruta,
    )


def parsear_agente(texto: str, ruta: Path | None = None) -> DefinicionAgente:
    """Convierte el contenido de un ``.agent.md`` en una ``DefinicionAgente`` validada."""
    origen = str(ruta) if ruta else "el agente"
    metadatos, cuerpo = separar_frontmatter(texto)

    skills = _lista_de_textos(metadatos, "skills", origen)
    if not skills:
        raise DefinicionInvalida(f"El agente de {origen} debe declarar al menos una skill.")
    if len(set(skills)) != len(skills):
        raise DefinicionInvalida(f"El agente de {origen} declara skills repetidas.")

    return DefinicionAgente(
        nombre=_texto_obligatorio(metadatos, "name", origen),
        descripcion=_texto_obligatorio(metadatos, "description", origen),
        instrucciones=cuerpo,
        modelo=_texto_obligatorio(metadatos, "model", origen),
        skills=skills,
        opciones=validar_opciones(metadatos.get("options"), origen),
        herramientas=_lista_de_textos(metadatos, "tools", origen),
        version=str(metadatos.get("version", "1.0.0")),
        ruta=ruta,
    )


def cargar_definiciones(ruta_agente: Path | str) -> tuple[DefinicionAgente, dict[str, DefinicionSkill]]:
    """Lee el agente y cada skill declarada desde ``<carpeta del agente>/skills/<nombre>.skill.md``.

    Raises:
        DefinicionInvalida: si falta un archivo o su contenido no es válido.
    """
    ruta_agente = Path(ruta_agente)
    if not ruta_agente.is_file():
        raise DefinicionInvalida(f"No existe el archivo del agente: {ruta_agente}")
    agente = parsear_agente(ruta_agente.read_text(encoding="utf-8"), ruta_agente)

    skills: dict[str, DefinicionSkill] = {}
    for nombre in agente.skills:
        ruta_skill = ruta_agente.parent / "skills" / f"{nombre}.skill.md"
        if not ruta_skill.is_file():
            raise DefinicionInvalida(f"El agente declara la skill '{nombre}' pero no existe {ruta_skill}.")
        skill = parsear_skill(ruta_skill.read_text(encoding="utf-8"), ruta_skill)
        if skill.nombre != nombre:
            raise DefinicionInvalida(f"El archivo {ruta_skill.name} declara name '{skill.nombre}' en vez de '{nombre}'.")
        skills[nombre] = skill
    return agente, skills
