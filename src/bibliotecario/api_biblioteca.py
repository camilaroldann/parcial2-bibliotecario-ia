"""Cliente de la API REST de la Biblioteca Virtual y control de permisos por skill."""

from __future__ import annotations

import requests

from bibliotecario import config


class ErrorBiblioteca(RuntimeError):
    """La API respondió con error o no está disponible."""

    def __init__(self, mensaje: str, status: int | None = None, errores: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.errores = errores or {}


class PermisoDenegado(PermissionError):
    """Una skill intentó usar una herramienta que no declaró en su archivo ``.skill.md``."""


class ClienteBiblioteca:
    """Envuelve los endpoints de la biblioteca. Es la única vía de acceso a los datos."""

    OPERACIONES = frozenset({"listar_libros", "crear_libro", "cambiar_estado"})

    def __init__(self, url_base: str = config.BIBLIOTECA_URL, timeout: float = config.TIMEOUT_BIBLIOTECA_S,
                 sesion: requests.Session | None = None):
        self.url_base = url_base.rstrip("/")
        self.timeout = timeout
        self.sesion = sesion or requests.Session()

    def disponible(self) -> bool:
        """``True`` si ``GET /health`` responde 200."""
        try:
            return self.sesion.get(f"{self.url_base}/health", timeout=2).status_code == 200
        except requests.RequestException:
            return False

    def _pedir(self, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
        try:
            respuesta = self.sesion.request(metodo, f"{self.url_base}{ruta}", json=cuerpo, timeout=self.timeout)
        except requests.RequestException as error:
            raise ErrorBiblioteca(f"La API de la biblioteca no responde en {self.url_base}.") from error
        try:
            datos = respuesta.json()
        except ValueError:
            datos = {}
        if not respuesta.ok:
            raise ErrorBiblioteca(datos.get("mensaje", f"Error HTTP {respuesta.status_code}."),
                                  respuesta.status_code, datos.get("errores"))
        return datos

    def listar_libros(self) -> list[dict]:
        """``GET /libros``: todos los libros ordenados por autor y título."""
        return self._pedir("GET", "/libros").get("datos", [])

    def crear_libro(self, libro: dict) -> dict:
        """``POST /libros``: da de alta un libro y devuelve el registro persistido."""
        return self._pedir("POST", "/libros", libro)["dato"]

    def cambiar_estado(self, id_libro: int, estado: str) -> dict:
        """``PATCH /libros/:id/estado``: registra un préstamo o una devolución."""
        return self._pedir("PATCH", f"/libros/{int(id_libro)}/estado", {"estado": estado})["dato"]


class Herramientas:
    """Expone a una skill únicamente las operaciones que declaró en ``tools`` (principio de mínimo privilegio)."""

    def __init__(self, cliente: ClienteBiblioteca, permitidas: tuple[str, ...] | list[str], skill: str = ""):
        self._cliente = cliente
        self._permitidas = frozenset(permitidas)
        self._skill = skill
        self.registro: list[str] = []

    def usar(self, nombre: str, *args, **kwargs):
        """Ejecuta la herramienta ``nombre`` si la skill tiene permiso.

        Raises:
            PermisoDenegado: si la herramienta no existe o no fue declarada por la skill.
        """
        if nombre not in ClienteBiblioteca.OPERACIONES:
            raise PermisoDenegado(f"La herramienta '{nombre}' no existe.")
        if nombre not in self._permitidas:
            raise PermisoDenegado(f"La skill '{self._skill}' no tiene permiso para usar '{nombre}'.")
        self.registro.append(nombre)
        return getattr(self._cliente, nombre)(*args, **kwargs)
