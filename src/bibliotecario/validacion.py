"""Barreras de seguridad y validación del Bibliotecario IA.

Dos fronteras de confianza:

1. **Entrada del usuario -> LLM**: se sanea y se rechazan intentos de *prompt injection*
   antes de gastar una inferencia.
2. **Salida del LLM -> API**: la respuesta del modelo se trata como dato no confiable y se
   valida con las mismas reglas de negocio que aplica la API de la biblioteca.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

LARGO_MAXIMO_ENTRADA = 500
LARGO_MAXIMO_CAMPO = 200
ESTADOS = ("Disponible", "Prestado")
ESTADO_POR_DEFECTO = "Disponible"

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Se evalúan sobre el texto normalizado (minúsculas y sin tildes).
PATRONES_INYECCION: tuple[tuple[str, re.Pattern], ...] = (
    ("intenta anular las instrucciones del agente",
     re.compile(r"\b(ignor|olvid|omit|saltea|descart|forget|disregard)\w*\b.{0,40}"
                r"\b(instruccion|regla|indicacion|prompt|restriccion|instruction|rule)")),
    ("pide revelar o cambiar el prompt de sistema",
     re.compile(r"\b(system prompt|prompt (del|de) sistema|mensaje (del|de) sistema|tus instrucciones)\b")),
    ("intenta cambiar el rol del agente",
     re.compile(r"\b(actua|actuar|comportate|comportarte|hace de cuenta|pretend|act)\s+(como|as|que sos)\b")),
    ("contiene sentencias SQL destructivas",
     re.compile(r"\b(drop|truncate|alter)\s+(table|database)\b|\bdelete\s+from\b|;\s*--|'\s*or\s+'?1'?\s*=\s*'?1")),
    ("pide borrar datos de forma masiva",
     re.compile(r"\b(borra|elimina|vacia|destrui)\w*\s+(todo|todos|toda|la base|los libros|el catalogo|la tabla)")),
    ("intenta cerrar o falsificar las etiquetas del prompt",
     re.compile(r"<\s*/?\s*(system|sistema|entrada_usuario|catalogo|instrucciones)\s*>")),
    ("usa técnicas conocidas de jailbreak",
     re.compile(r"\b(jailbreak|modo desarrollador|developer mode|dan mode|sin restricciones)\b")),
)


class EntradaRechazada(ValueError):
    """La entrada del usuario no supera las barreras de seguridad."""


def normalizar(texto: str) -> str:
    """Devuelve el texto en minúsculas, sin tildes y con espacios colapsados (para comparar)."""
    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def sanitizar_entrada(texto: object, largo_maximo: int = LARGO_MAXIMO_ENTRADA) -> str:
    """Limpia la entrada del usuario: quita caracteres de control y espacios sobrantes.

    Raises:
        EntradaRechazada: si no es texto, queda vacía o supera ``largo_maximo``.
    """
    if not isinstance(texto, str):
        raise EntradaRechazada("La consulta debe ser texto.")
    limpio = _CONTROL.sub("", texto)
    limpio = re.sub(r"[ \t]+", " ", limpio).strip()
    if not limpio:
        raise EntradaRechazada("La consulta está vacía.")
    if len(limpio) > largo_maximo:
        raise EntradaRechazada(f"La consulta supera los {largo_maximo} caracteres permitidos.")
    return limpio


def detectar_inyeccion(texto: str) -> str | None:
    """Devuelve el motivo si el texto parece un intento de prompt injection, o ``None``."""
    normalizado = normalizar(texto)
    for motivo, patron in PATRONES_INYECCION:
        if patron.search(normalizado):
            return motivo
    return None


def envolver_entrada(texto: str) -> str:
    """Delimita la entrada del usuario para que el modelo la trate como dato y no como instrucción."""
    return f"<entrada_usuario>\n{texto}\n</entrada_usuario>"


def completar_anio(valor: int, anio_actual: int) -> int:
    """Convierte años de dos cifras a cuatro (``63 -> 1963``, ``15 -> 2015``) de forma determinista.

    Los años de 1 a 99 se interpretan en el siglo actual si no lo superan; si no, en el anterior.
    Cualquier otro valor se devuelve sin cambios.
    """
    if 0 < valor < 100:
        siglo = anio_actual // 100 * 100
        return siglo + valor if siglo + valor <= anio_actual else siglo - 100 + valor
    return valor


def _texto(valor: object) -> str:
    return re.sub(r"\s+", " ", valor).strip() if isinstance(valor, str) else ""


def validar_estado(valor: object) -> str:
    """Devuelve el estado en su forma canónica (``Disponible`` / ``Prestado``).

    Raises:
        ValueError: si el valor no es uno de los estados admitidos.
    """
    texto = _texto(valor)
    for estado in ESTADOS:
        if texto.lower() == estado.lower():
            return estado
    raise ValueError(f"El estado debe ser uno de: {' o '.join(ESTADOS)}.")


def validar_libro(datos: object, anio_actual: int | None = None) -> tuple[dict, dict]:
    """Valida una ficha de libro con las mismas reglas que la API de la biblioteca.

    Returns:
        ``(libro, errores)``: el libro normalizado y un mapa ``campo -> mensaje``
        (vacío si la ficha es válida).
    """
    anio_actual = anio_actual or date.today().year
    datos = datos if isinstance(datos, dict) else {}
    errores: dict[str, str] = {}

    campos = {"titulo": "El título", "autor": "El autor", "genero": "El género"}
    libro: dict = {}
    for campo, etiqueta in campos.items():
        valor = _texto(datos.get(campo))
        if not valor:
            errores[campo] = f"{etiqueta} es obligatorio."
        elif len(valor) > LARGO_MAXIMO_CAMPO:
            errores[campo] = f"{etiqueta} no puede superar los {LARGO_MAXIMO_CAMPO} caracteres."
        libro[campo] = valor

    anio = datos.get("anioPublicacion")
    if isinstance(anio, str) and re.fullmatch(r"-?\d+", anio.strip()):
        anio = int(anio.strip())
    if anio is None or anio == "":
        errores["anioPublicacion"] = "El año de publicación es obligatorio."
    elif isinstance(anio, bool) or not isinstance(anio, int):
        errores["anioPublicacion"] = "El año de publicación debe ser un número entero."
    else:
        anio = completar_anio(anio, anio_actual)
        if anio <= 0:
            errores["anioPublicacion"] = "El año de publicación debe ser mayor a 0."
        elif anio > anio_actual:
            errores["anioPublicacion"] = f"El año de publicación no puede ser mayor a {anio_actual}."
    libro["anioPublicacion"] = anio if isinstance(anio, int) and not isinstance(anio, bool) else None

    estado = datos.get("estado")
    if estado in (None, ""):
        libro["estado"] = ESTADO_POR_DEFECTO
    else:
        try:
            libro["estado"] = validar_estado(estado)
        except ValueError as error:
            errores["estado"] = str(error)
            libro["estado"] = None

    return libro, errores
