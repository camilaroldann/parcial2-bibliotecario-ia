import express from 'express';
import apiRouter from './api/routes/index.js';
import { notFoundHandler, errorHandler } from './api/middlewares/error-handler.js';
import { config } from './shared/config.js';

/** Ensamblado de la aplicación: front end estático + API + manejo de errores. */
export function createApp() {
    const app = express();

    app.use(express.json({ limit: '100kb' }));

    // CAPA FRONT END: archivos estáticos servidos desde /public
    app.use(express.static(config.publicDir));

    // CAPA API
    app.use('/api', apiRouter);
    app.use('/api', notFoundHandler);

    app.use(errorHandler);

    return app;
}
