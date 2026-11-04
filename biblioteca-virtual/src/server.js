import { createApp } from './app.js';
import { initSchema } from './data/connection.js';
import { config } from './shared/config.js';

// 1) La capa de datos prepara el esquema (idempotente)
initSchema();

// 2) Se levanta el servidor HTTP
createApp().listen(config.port, () => {
    console.log('----------------------------------------------------');
    console.log('  Biblioteca Virtual');
    console.log(`  Aplicación:    http://localhost:${config.port}`);
    console.log(`  API:           http://localhost:${config.port}/api/libros`);
    console.log(`  Base de datos: ${config.dbFile}`);
    console.log('----------------------------------------------------');
});
