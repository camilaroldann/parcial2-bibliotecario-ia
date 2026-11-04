"""Implementación de las skills declaradas en ``agente/skills/*.skill.md``.

Cada skill combina una inferencia acotada (el LLM solo extrae o elige datos con un
esquema JSON fijo) con lógica determinista en Python (validación, búsqueda en el
catálogo y llamadas a la API con permisos explícitos).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date

from bibliotecario.api_biblioteca import ErrorBiblioteca, Herramientas, PermisoDenegado
from bibliotecario.definiciones import DefinicionSkill
from bibliotecario.llm import ErrorLLM, RespuestaLLM
from bibliotecario.validacion import envolver_entrada, normalizar, validar_libro

MAX_RECOMENDACIONES = 3
MAX_LIBROS_EN_PROMPT = 60      # acota los tokens del catálogo dentro de num_ctx
LARGO_MAXIMO_MENSAJE = 300


@dataclass
class Resultado:
    """Lo que devuelve una skill (o el agente) al usuario.

    ``estado`` es uno de: ``ok``, ``pendiente_confirmacion``, ``faltan_datos``,
    ``sin_resultados``, ``error``, ``rechazado`` o ``fuera_de_alcance``.
    """

    skill: str
    estado: str
    mensaje: str
    datos: dict = field(default_factory=dict)
    salida_llm: dict | None = None
    accion_pendiente: dict | None = None
    traza: list[str] = field(default_factory=list)
    metricas: list[dict] = field(default_factory=list)


def metricas_de(etapa: str, respuesta: RespuestaLLM) -> dict:
    """Resume la telemetría de una inferencia para mostrarla en la interfaz."""
    return {
        "etapa": etapa,
        "modelo": respuesta.modelo,
        "temperature": respuesta.opciones.get("temperature"),
        "seed": respuesta.opciones.get("seed"),
        "num_ctx": respuesta.opciones.get("num_ctx"),
        "duracion_s": respuesta.duracion_s,
        "tokens_prompt": respuesta.tokens_prompt,
        "tokens_generados": respuesta.tokens_generados,
        "tokens_por_segundo": respuesta.tokens_por_segundo,
    }


def _texto(valor: object, largo: int = LARGO_MAXIMO_MENSAJE) -> str:
    return re.sub(r"\s+", " ", valor).strip()[:largo] if isinstance(valor, str) else ""


_ARTICULOS = re.compile(r"^(el|la|los|las|un|una|lo)\s+")


def _clave_titulo(titulo: str) -> str:
    return _ARTICULOS.sub("", normalizar(titulo))


def buscar_libros(libros: list[dict], titulo: str, autor: str = "") -> list[dict]:
    """Ubica libros del catálogo por título (tolerante a tildes, artículos y erratas) y opcionalmente por autor.

    Orden de búsqueda: coincidencia exacta -> contenida -> parecida (difflib, 80 %).
    Si el autor filtra todos los candidatos, se ignora el autor (el usuario confirma igual).
    """
    clave = _clave_titulo(titulo)
    if not clave:
        return []
    por_clave = [(l, _clave_titulo(l.get("titulo", ""))) for l in libros]

    candidatos = [l for l, c in por_clave if c == clave]
    if not candidatos:
        candidatos = [l for l, c in por_clave if c and (clave in c or c in clave)]
    if not candidatos:
        parecidos = set(difflib.get_close_matches(clave, [c for _, c in por_clave], n=3, cutoff=0.8))
        candidatos = [l for l, c in por_clave if c in parecidos]

    tokens_autor = [t for t in normalizar(autor).split() if len(t) > 2]
    if tokens_autor and len(candidatos) > 1:
        filtrados = [l for l in candidatos if any(t in normalizar(l.get("autor", "")) for t in tokens_autor)]
        candidatos = filtrados or candidatos
    return candidatos


class Skill:
    """Base de las skills: arma el prompt desde el ``.skill.md`` y ejecuta acciones con permisos."""

    def __init__(self, definicion: DefinicionSkill, llm, herramientas: Herramientas,
                 modelo_por_defecto: str, opciones_base: dict | None = None, anio_actual: int | None = None):
        self.definicion = definicion
        self.llm = llm
        self.herramientas = herramientas
        self.modelo = definicion.modelo or modelo_por_defecto
        self.opciones = {**(opciones_base or {}), **definicion.opciones}
        self.anio_actual = anio_actual or date.today().year

    @property
    def nombre(self) -> str:
        return self.definicion.nombre

    def _resultado(self, estado: str, mensaje: str, **kwargs) -> Resultado:
        return Resultado(skill=self.nombre, estado=estado, mensaje=mensaje, **kwargs)

    def _consultar(self, mensaje_usuario: str, resultado: Resultado) -> dict:
        """Ejecuta la inferencia con el system prompt, el esquema y los parámetros declarados en el ``.md``."""
        respuesta = self.llm.chat_json(self.modelo, self.definicion.instrucciones, mensaje_usuario,
                                       self.definicion.esquema_salida, self.opciones)
        resultado.salida_llm = respuesta.contenido
        resultado.metricas.append(metricas_de(self.nombre, respuesta))
        resultado.traza.append(f"Skill '{self.nombre}' consultó {self.modelo} "
                               f"(temperature={self.opciones.get('temperature')}, seed={self.opciones.get('seed')}).")
        return respuesta.contenido

    def ejecutar(self, entrada: str) -> Resultado:  # pragma: no cover - lo implementan las subclases
        raise NotImplementedError

    def ejecutar_seguro(self, entrada: str) -> Resultado:
        """Ejecuta la skill traduciendo las fallas de infraestructura a un ``Resultado`` legible."""
        try:
            return self.ejecutar(entrada)
        except ErrorLLM as error:
            return self._resultado("error", f"El modelo local no pudo responder: {error}")
        except ErrorBiblioteca as error:
            return self._resultado("error", error.mensaje, datos={"errores": error.errores})
        except PermisoDenegado as error:
            return self._resultado("rechazado", str(error))

    def _proponer(self, resultado: Resultado, accion: dict, pregunta: str) -> Resultado:
        """Deja la acción pendiente de confirmación o la ejecuta, según ``requires_confirmation``."""
        if not self.definicion.requiere_confirmacion:
            confirmado = self.confirmar(accion)
            confirmado.salida_llm, confirmado.metricas = resultado.salida_llm, resultado.metricas
            confirmado.traza = resultado.traza + confirmado.traza
            return confirmado
        resultado.estado = "pendiente_confirmacion"
        resultado.mensaje = pregunta
        resultado.accion_pendiente = accion
        return resultado

    def confirmar(self, accion: dict) -> Resultado:
        """Ejecuta una acción pendiente pasando por el control de permisos de ``Herramientas``."""
        herramienta = accion.get("herramienta", "")
        try:
            dato = self.herramientas.usar(herramienta, **accion.get("argumentos", {}))
        except ErrorBiblioteca as error:
            return self._resultado("error", error.mensaje, datos={"errores": error.errores})
        except PermisoDenegado as error:
            return self._resultado("rechazado", str(error))
        return self._resultado("ok", self.mensaje_exito(dato), datos={"libro": dato},
                               traza=[f"Herramienta '{herramienta}' ejecutada sobre la API."])

    def mensaje_exito(self, libro: dict) -> str:
        return "Operación realizada."


class CatalogarLibro(Skill):
    """Texto libre -> ficha validada -> ``POST /api/libros``."""

    def ejecutar(self, entrada: str) -> Resultado:
        resultado = self._resultado("ok", "")
        salida = self._consultar(f"Año actual: {self.anio_actual}\n{envolver_entrada(entrada)}", resultado)

        libro, errores = validar_libro(salida, self.anio_actual)
        resultado.datos["libro"] = libro
        if errores:
            resultado.estado = "faltan_datos"
            resultado.datos["errores"] = errores
            resultado.mensaje = "Para cargar el libro me falta: " + " ".join(errores.values())
            resultado.traza.append(f"Validación local rechazó la ficha: {sorted(errores)}.")
            return resultado

        resultado.traza.append("Validación local OK (mismas reglas que la API).")
        pregunta = (f"¿Confirmás el alta de «{libro['titulo']}» de {libro['autor']} "
                    f"({libro['genero']}, {libro['anioPublicacion']}, {libro['estado']})?")
        return self._proponer(resultado, {"herramienta": "crear_libro", "argumentos": {"libro": libro}}, pregunta)

    def mensaje_exito(self, libro: dict) -> str:
        return f"Listo: cargué «{libro['titulo']}» de {libro['autor']} en el catálogo (id {libro['id']})."


class RecomendarLibros(Skill):
    """Catálogo real + preferencias -> hasta 3 libros disponibles, descartando ids inventados."""

    def ejecutar(self, entrada: str) -> Resultado:
        resultado = self._resultado("ok", "")
        disponibles = [l for l in self.herramientas.usar("listar_libros") if l.get("estado") == "Disponible"]
        disponibles = disponibles[:MAX_LIBROS_EN_PROMPT]
        if not disponibles:
            resultado.estado = "sin_resultados"
            resultado.mensaje = "No hay libros disponibles para recomendar en este momento."
            return resultado

        catalogo = "\n".join(f"{l['id']} | {l['titulo']} | {l['autor']} | {l['genero']} | {l['anioPublicacion']}"
                             for l in disponibles)
        salida = self._consultar(f"<catalogo>\n{catalogo}\n</catalogo>\n{envolver_entrada(entrada)}", resultado)

        por_id = {l["id"]: l for l in disponibles}
        elegidos: list[dict] = []
        for recomendacion in salida.get("recomendaciones") or []:
            if not isinstance(recomendacion, dict):
                continue
            id_libro = recomendacion.get("id")
            if isinstance(id_libro, str) and id_libro.strip().isdigit():
                id_libro = int(id_libro)
            if id_libro not in por_id:
                resultado.traza.append(f"Descarté el id {id_libro!r}: no existe entre los libros disponibles.")
                continue
            if any(e["id"] == id_libro for e in elegidos):
                continue
            motivo = _texto(recomendacion.get("motivo")) or "Coincide con lo que buscás."
            elegidos.append({**por_id[id_libro], "motivo": motivo})
            if len(elegidos) == MAX_RECOMENDACIONES:
                break

        if not elegidos:
            resultado.estado = "sin_resultados"
            resultado.mensaje = "No encontré en el catálogo libros disponibles que coincidan con lo que buscás."
            return resultado

        resultado.datos["recomendaciones"] = elegidos
        resultado.mensaje = _texto(salida.get("mensaje")) or "Estos libros disponibles te pueden interesar:"
        return resultado


class GestionarPrestamo(Skill):
    """Pedido de préstamo/devolución -> libro del catálogo -> ``PATCH /api/libros/:id/estado``."""

    ACCIONES = {"prestar": ("Prestado", "el préstamo"), "devolver": ("Disponible", "la devolución")}

    def ejecutar(self, entrada: str) -> Resultado:
        resultado = self._resultado("ok", "")
        salida = self._consultar(envolver_entrada(entrada), resultado)

        accion = normalizar(_texto(salida.get("accion")))
        if accion not in self.ACCIONES:
            resultado.estado = "faltan_datos"
            resultado.mensaje = "No entendí si querés prestar o devolver un libro."
            return resultado
        titulo, autor = _texto(salida.get("titulo"), 200), _texto(salida.get("autor"), 200)
        if not titulo:
            resultado.estado = "faltan_datos"
            resultado.mensaje = f"¿Qué libro querés {accion}?"
            return resultado

        candidatos = buscar_libros(self.herramientas.usar("listar_libros"), titulo, autor)
        if not candidatos:
            resultado.estado = "sin_resultados"
            resultado.mensaje = f"No encontré «{titulo}» en el catálogo."
            return resultado
        if len(candidatos) > 1:
            resultado.estado = "faltan_datos"
            resultado.datos["candidatos"] = candidatos
            opciones = "; ".join(f"«{l['titulo']}» de {l['autor']}" for l in candidatos)
            resultado.mensaje = f"Encontré varios libros parecidos: {opciones}. ¿Cuál es?"
            return resultado

        libro = candidatos[0]
        estado_objetivo, nombre_operacion = self.ACCIONES[accion]
        resultado.datos["libro"] = libro
        resultado.traza.append(f"Libro ubicado en el catálogo: id {libro['id']} ({libro['estado']}).")
        if libro["estado"] == estado_objetivo:
            resultado.estado = "error"
            resultado.mensaje = f"No se puede registrar {nombre_operacion}: «{libro['titulo']}» ya está {estado_objetivo.lower()}."
            return resultado

        pregunta = f"¿Confirmás {nombre_operacion} de «{libro['titulo']}» de {libro['autor']}?"
        accion_api = {"herramienta": "cambiar_estado", "argumentos": {"id_libro": libro["id"], "estado": estado_objetivo}}
        return self._proponer(resultado, accion_api, pregunta)

    def mensaje_exito(self, libro: dict) -> str:
        if libro["estado"] == "Prestado":
            return f"Registré el préstamo de «{libro['titulo']}»."
        return f"Registré la devolución de «{libro['titulo']}»: vuelve a estar disponible."


SKILLS_IMPLEMENTADAS: dict[str, type[Skill]] = {
    "catalogar_libro": CatalogarLibro,
    "recomendar_libros": RecomendarLibros,
    "gestionar_prestamo": GestionarPrestamo,
}
