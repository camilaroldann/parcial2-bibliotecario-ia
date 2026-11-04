import * as service from '../services/libros.service.js';

/**
 * CAPA API - Controladores
 * Única responsabilidad: adaptar HTTP <-> servicio de negocio.
 * No contiene reglas de negocio ni SQL.
 */

/** POST /api/libros */
export function crear(req, res, next) {
    try {
        const libro = service.crearLibro(req.body);
        res.status(201).json({ ok: true, mensaje: 'Libro cargado correctamente.', dato: libro });
    } catch (error) {
        next(error);
    }
}

/** GET /api/libros */
export function listar(req, res, next) {
    try {
        const libros = service.listarLibros();
        res.status(200).json({ ok: true, total: libros.length, datos: libros });
    } catch (error) {
        next(error);
    }
}

/** GET /api/libros/:id */
export function obtener(req, res, next) {
    try {
        res.status(200).json({ ok: true, dato: service.obtenerLibro(req.params.id) });
    } catch (error) {
        next(error);
    }
}

/** PATCH /api/libros/:id/estado  (préstamo / devolución) */
export function cambiarEstado(req, res, next) {
    try {
        const libro = service.cambiarEstado(req.params.id, req.body);
        res.status(200).json({ ok: true, mensaje: 'Estado actualizado correctamente.', dato: libro });
    } catch (error) {
        next(error);
    }
}
