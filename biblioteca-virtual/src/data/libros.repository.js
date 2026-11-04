import { getDb } from './connection.js';

/**
 * CAPA DE ACCESO A DATOS - Repositorio de libros
 * Única responsabilidad: traducir entre SQL y objetos JavaScript.
 * No valida reglas de negocio ni conoce HTTP.
 */

/** Convierte una fila de la tabla al objeto de dominio usado por la aplicación. */
function mapRow(row) {
    if (!row) return null;
    return {
        id: row.id,
        titulo: row.titulo,
        autor: row.autor,
        genero: row.genero,
        anioPublicacion: row.anio_publicacion,
        estado: row.estado,
        creadoEn: row.creado_en,
    };
}

/**
 * Devuelve todos los libros ordenados alfabéticamente por autor y luego por título.
 * El orden se resuelve en el motor (COLLATE NOCASE) y se apoya en ix_libros_orden.
 */
export function listarTodos() {
    const filas = getDb()
        .prepare(
            `SELECT id, titulo, autor, genero, anio_publicacion, estado, creado_en
               FROM libros
              ORDER BY autor COLLATE NOCASE ASC, titulo COLLATE NOCASE ASC`
        )
        .all();
    return filas.map(mapRow);
}

export function buscarPorId(id) {
    const fila = getDb()
        .prepare(
            `SELECT id, titulo, autor, genero, anio_publicacion, estado, creado_en
               FROM libros
              WHERE id = ?`
        )
        .get(id);
    return mapRow(fila);
}

/** Busca un libro por título + autor ignorando mayúsculas y espacios sobrantes. */
export function buscarPorTituloYAutor(titulo, autor) {
    const fila = getDb()
        .prepare(
            `SELECT id, titulo, autor, genero, anio_publicacion, estado, creado_en
               FROM libros
              WHERE lower(trim(titulo)) = lower(trim(?))
                AND lower(trim(autor))  = lower(trim(?))`
        )
        .get(titulo, autor);
    return mapRow(fila);
}

/** Inserta un libro ya validado y devuelve el registro persistido. */
export function insertar({ titulo, autor, genero, anioPublicacion, estado }) {
    const resultado = getDb()
        .prepare(
            `INSERT INTO libros (titulo, autor, genero, anio_publicacion, estado)
             VALUES (?, ?, ?, ?, ?)`
        )
        .run(titulo, autor, genero, anioPublicacion, estado);

    return buscarPorId(Number(resultado.lastInsertRowid));
}

/** Actualiza el estado (Disponible / Prestado) y devuelve el registro actualizado. */
export function actualizarEstado(id, estado) {
    getDb().prepare('UPDATE libros SET estado = ? WHERE id = ?').run(estado, id);
    return buscarPorId(id);
}

export function contar() {
    return getDb().prepare('SELECT COUNT(*) AS total FROM libros').get().total;
}
