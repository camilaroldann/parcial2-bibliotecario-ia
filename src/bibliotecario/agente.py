"""Agente orquestador: valida la entrada, elige la skill y delega la ejecución."""

from __future__ import annotations

from pathlib import Path

from bibliotecario import config
from bibliotecario.api_biblioteca import ClienteBiblioteca, Herramientas
from bibliotecario.definiciones import DefinicionAgente, DefinicionInvalida, DefinicionSkill, cargar_definiciones
from bibliotecario.llm import ClienteOllama, ErrorLLM
from bibliotecario.skills import SKILLS_IMPLEMENTADAS, Resultado, Skill, metricas_de
from bibliotecario.validacion import EntradaRechazada, detectar_inyeccion, envolver_entrada, sanitizar_entrada

SIN_SKILL = "ninguna"
MENSAJE_FUERA_DE_ALCANCE = ("Solo puedo ayudarte con la biblioteca: cargar libros, recomendar lecturas "
                            "y registrar préstamos o devoluciones.")


class Agente:
    """Runtime del agente definido en ``bibliotecario.agent.md``."""

    def __init__(self, definicion: DefinicionAgente, skills: dict[str, DefinicionSkill], llm,
                 cliente: ClienteBiblioteca, anio_actual: int | None = None):
        self.definicion = definicion
        self.llm = llm
        self.cliente = cliente
        self.skills: dict[str, Skill] = {}
        for nombre in definicion.skills:
            if nombre not in SKILLS_IMPLEMENTADAS:
                raise DefinicionInvalida(f"La skill '{nombre}' está declarada pero no tiene implementación.")
            definicion_skill = skills[nombre]
            herramientas = Herramientas(cliente, definicion_skill.herramientas, nombre)
            self.skills[nombre] = SKILLS_IMPLEMENTADAS[nombre](
                definicion_skill, llm, herramientas, definicion.modelo, anio_actual=anio_actual)
        self.comandos = {s.definicion.comando: n for n, s in self.skills.items() if s.definicion.comando}

    @property
    def esquema_enrutamiento(self) -> dict:
        """Esquema JSON que restringe la decisión del enrutador a las skills declaradas."""
        return {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "enum": [*self.skills, SIN_SKILL]},
                "motivo": {"type": "string"},
            },
            "required": ["skill", "motivo"],
        }

    @property
    def prompt_enrutamiento(self) -> str:
        """System prompt del enrutador: instrucciones del ``.agent.md`` + catálogo de skills."""
        catalogo = "\n".join(f"- `{n}`: {s.definicion.descripcion}" for n, s in self.skills.items())
        return f"{self.definicion.instrucciones}\n\n# Skills disponibles\n{catalogo}\n- `{SIN_SKILL}`: fuera de alcance."

    def enrutar(self, texto: str) -> tuple[str, str, dict]:
        """Le pide al modelo que elija la skill. Devuelve ``(skill, motivo, metricas)``.

        Si el modelo devuelve algo fuera del esquema, se toma como ``ninguna`` (falla segura).
        """
        respuesta = self.llm.chat_json(self.definicion.modelo, self.prompt_enrutamiento, envolver_entrada(texto),
                                       self.esquema_enrutamiento, self.definicion.opciones)
        skill = respuesta.contenido.get("skill")
        motivo = str(respuesta.contenido.get("motivo", "")).strip()[:200]
        if skill not in self.skills:
            skill = SIN_SKILL
        return skill, motivo, metricas_de("enrutador", respuesta)

    def procesar(self, entrada: str, skill: str | None = None) -> Resultado:
        """Atiende un pedido del usuario de punta a punta.

        Args:
            entrada: texto del usuario. Puede empezar con un comando (``/catalogar ...``).
            skill: fuerza una skill concreta y saltea el enrutador.
        """
        try:
            texto = sanitizar_entrada(entrada)
        except EntradaRechazada as error:
            return Resultado("seguridad", "rechazado", str(error))

        traza: list[str] = []
        if texto.startswith("/"):
            comando, _, resto = texto.partition(" ")
            if comando not in self.comandos:
                disponibles = ", ".join(sorted(self.comandos))
                return Resultado("ninguna", "fuera_de_alcance", f"Comando desconocido. Disponibles: {disponibles}.")
            skill, texto = self.comandos[comando], resto.strip()
            if not texto:
                return Resultado(skill, "faltan_datos", f"Escribí tu pedido después de {comando}.")
            traza.append(f"Comando {comando} -> skill '{skill}' (sin enrutador).")

        motivo = detectar_inyeccion(texto)
        if motivo:
            return Resultado("seguridad", "rechazado", f"Pedido bloqueado por seguridad: {motivo}.",
                             traza=[f"Filtro anti prompt-injection: {motivo}. No se llamó al modelo."])

        metricas: list[dict] = []
        if skill is None:
            try:
                skill, motivo_ruta, metrica = self.enrutar(texto)
            except ErrorLLM as error:
                return Resultado("enrutador", "error", f"El modelo local no pudo responder: {error}")
            metricas.append(metrica)
            traza.append(f"Enrutador ({self.definicion.modelo}) eligió '{skill}': {motivo_ruta}")
            if skill == SIN_SKILL:
                return Resultado(SIN_SKILL, "fuera_de_alcance", MENSAJE_FUERA_DE_ALCANCE, traza=traza, metricas=metricas)
        elif skill not in self.skills:
            return Resultado(skill, "error", f"La skill '{skill}' no está habilitada en este agente.")
        elif not traza:
            traza.append(f"Skill '{skill}' elegida manualmente (sin enrutador).")

        resultado = self.skills[skill].ejecutar_seguro(texto)
        resultado.traza = traza + resultado.traza
        resultado.metricas = metricas + resultado.metricas
        return resultado

    def confirmar(self, resultado: Resultado) -> Resultado:
        """Ejecuta la acción que quedó pendiente en ``resultado``.

        Raises:
            ValueError: si el resultado no tiene una acción pendiente.
        """
        if resultado.estado != "pendiente_confirmacion" or not resultado.accion_pendiente:
            raise ValueError("El resultado no tiene una acción pendiente de confirmación.")
        return self.skills[resultado.skill].confirmar(resultado.accion_pendiente)


def crear_agente(ruta_agente: Path | str = config.RUTA_AGENTE, llm=None, cliente: ClienteBiblioteca | None = None,
                 anio_actual: int | None = None) -> Agente:
    """Construye el agente a partir de sus archivos ``.md`` y los clientes por defecto."""
    definicion, skills = cargar_definiciones(ruta_agente)
    return Agente(definicion, skills, llm or ClienteOllama(), cliente or ClienteBiblioteca(), anio_actual)
