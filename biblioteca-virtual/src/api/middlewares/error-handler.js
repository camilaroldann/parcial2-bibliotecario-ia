import { AppError } from '../../shared/errors.js';

/** 404 para rutas de API inexistentes. */
export function notFoundHandler(req, res) {
    res.status(404).json({ ok: false, mensaje: `Ruta no encontrada: ${req.method} ${req.originalUrl}` });
}

/**
 * Manejador central de errores: traduce errores de dominio a respuestas HTTP.
 * Es el único punto de la API que conoce ambos mundos.
 */
export function errorHandler(error, req, res, next) { // eslint-disable-line no-unused-vars
    if (error instanceof AppError) {
        return res.status(error.status).json({
            ok: false,
            mensaje: error.message,
            ...(error.detalles ? { errores: error.detalles } : {}),
        });
    }

    // JSON malformado enviado por el cliente
    if (error?.type === 'entity.parse.failed') {
        return res.status(400).json({ ok: false, mensaje: 'El cuerpo de la petición no es un JSON válido.' });
    }

    // Red de seguridad: restricciones que sólo detecta la base de datos
    const mensajeOriginal = error?.message ?? '';
    if (/UNIQUE constraint failed/i.test(mensajeOriginal)) {
        return res.status(409).json({ ok: false, mensaje: 'Ya existe un libro con ese título y autor.' });
    }
    if (/CHECK constraint failed/i.test(mensajeOriginal)) {
        return res.status(400).json({ ok: false, mensaje: 'Los datos enviados no cumplen las restricciones del catálogo.' });
    }

    console.error('[error inesperado]', error);
    res.status(500).json({ ok: false, mensaje: 'Ocurrió un error interno en el servidor.' });
}
