/**
 * Errores de dominio. La capa de negocio los lanza sin saber nada de HTTP;
 * la capa API los traduce a códigos de estado en el manejador de errores.
 */

export class AppError extends Error {
    constructor(message, status, detalles = null) {
        super(message);
        this.name = new.target.name;
        this.status = status;
        this.detalles = detalles;
    }
}

/** 400 - Los datos recibidos no cumplen las reglas de validación. */
export class ValidationError extends AppError {
    constructor(detalles, message = 'Los datos enviados no son válidos.') {
        super(message, 400, detalles);
    }
}

/** 409 - El alta choca con un registro ya existente (título + autor duplicados). */
export class ConflictError extends AppError {
    constructor(message = 'El recurso ya existe.') {
        super(message, 409);
    }
}

/** 404 - El recurso solicitado no existe. */
export class NotFoundError extends AppError {
    constructor(message = 'El recurso no existe.') {
        super(message, 404);
    }
}
