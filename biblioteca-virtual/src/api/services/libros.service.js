import * as repo from '../../data/libros.repository.js';
import { ESTADOS, ESTADO_POR_DEFECTO } from '../../shared/config.js';
import { ValidationError, ConflictError, NotFoundError } from '../../shared/errors.js';

/**
 * CAPA DE LÓGICA DE NEGOCIO
 * Única responsabilidad: aplicar las reglas del dominio.
 * Habla con el repositorio; no conoce Express, req ni res.
 */

const LARGO_MAXIMO = 200;

const texto = (valor) => (typeof valor === 'string' ? valor.trim() : '');

/**
 * Valida y normaliza los datos de un libro.
 * Devuelve { datos, errores } donde errores es un mapa campo -> mensaje.
 */
function validarLibro(entrada = {}) {
    const errores = {};

    const titulo = texto(entrada.titulo);
    const autor = texto(entrada.autor);
    const genero = texto(entrada.genero);

    // Regla: todos los campos son obligatorios
    if (!titulo) errores.titulo = 'El título es obligatorio.';
    else if (titulo.length > LARGO_MAXIMO) errores.titulo = `El título no puede superar los ${LARGO_MAXIMO} caracteres.`;

    if (!autor) errores.autor = 'El autor es obligatorio.';
    else if (autor.length > LARGO_MAXIMO) errores.autor = `El autor no puede superar los ${LARGO_MAXIMO} caracteres.`;

    if (!genero) errores.genero = 'El género es obligatorio.';
    else if (genero.length > LARGO_MAXIMO) errores.genero = `El género no puede superar los ${LARGO_MAXIMO} caracteres.`;

    // Regla: el año debe ser numérico, mayor a 0 y no mayor al año actual
    const anioCrudo = texto(String(entrada.anioPublicacion ?? entrada.anio_publicacion ?? ''));
    const anioActual = new Date().getFullYear();
    let anioPublicacion = null;

    if (!anioCrudo) {
        errores.anioPublicacion = 'El año de publicación es obligatorio.';
    } else if (!/^-?\d+$/.test(anioCrudo)) {
        errores.anioPublicacion = 'El año de publicación debe ser un número entero.';
    } else {
        anioPublicacion = Number(anioCrudo);
        if (anioPublicacion <= 0) {
            errores.anioPublicacion = 'El año de publicación debe ser mayor a 0.';
        } else if (anioPublicacion > anioActual) {
            errores.anioPublicacion = `El año de publicación no puede ser mayor a ${anioActual}.`;
        }
    }

    // Regla: el estado sólo puede ser "Disponible" o "Prestado" (por defecto "Disponible")
    const estadoCrudo = texto(entrada.estado);
    let estado = ESTADO_POR_DEFECTO;

    if (estadoCrudo) {
        const coincidencia = ESTADOS.find((e) => e.toLowerCase() === estadoCrudo.toLowerCase());
        if (!coincidencia) {
            errores.estado = `El estado debe ser uno de: ${ESTADOS.join(' o ')}.`;
        } else {
            estado = coincidencia;
        }
    }

    return { datos: { titulo, autor, genero, anioPublicacion, estado }, errores };
}

/**
 * Alta de un libro.
 * Lanza ValidationError si algún campo incumple las reglas y
 * ConflictError si ya existe un libro con el mismo título y autor.
 */
export function crearLibro(entrada) {
    const { datos, errores } = validarLibro(entrada);

    if (Object.keys(errores).length > 0) {
        throw new ValidationError(errores);
    }

    // Regla: no permitir duplicados de título + autor
    if (repo.buscarPorTituloYAutor(datos.titulo, datos.autor)) {
        throw new ConflictError(`Ya existe un libro con el título "${datos.titulo}" del autor "${datos.autor}".`);
    }

    return repo.insertar(datos);
}

/** Listado completo, ordenado alfabéticamente por autor y luego por título. */
export function listarLibros() {
    return repo.listarTodos();
}

export function obtenerLibro(id) {
    const numero = Number(id);
    if (!Number.isInteger(numero) || numero <= 0) {
        throw new ValidationError({ id: 'El identificador debe ser un número entero positivo.' });
    }

    const libro = repo.buscarPorId(numero);
    if (!libro) throw new NotFoundError(`No existe un libro con id ${numero}.`);

    return libro;
}

/**
 * Préstamo / devolución de un libro.
 * Regla: sólo se presta un libro "Disponible" y sólo se devuelve uno "Prestado".
 * Lanza ValidationError (estado inválido), NotFoundError (id inexistente)
 * y ConflictError (el libro ya está en el estado pedido).
 */
export function cambiarEstado(id, entrada = {}) {
    const libro = obtenerLibro(id);

    const estadoCrudo = texto(entrada.estado);
    const estado = ESTADOS.find((e) => e.toLowerCase() === estadoCrudo.toLowerCase());
    if (!estado) {
        throw new ValidationError({ estado: `El estado debe ser uno de: ${ESTADOS.join(' o ')}.` });
    }

    if (libro.estado === estado) {
        throw new ConflictError(`El libro "${libro.titulo}" ya está ${estado.toLowerCase()}.`);
    }

    return repo.actualizarEstado(libro.id, estado);
}
