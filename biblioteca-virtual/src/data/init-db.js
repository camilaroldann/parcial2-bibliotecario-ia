/**
 * Script independiente para crear la base de datos: `npm run db:init`
 * El servidor también la crea al arrancar, así que este script es opcional.
 */
import { initSchema, closeDb } from './connection.js';
import { config } from '../shared/config.js';

initSchema();
closeDb();
console.log(`Base de datos lista en: ${config.dbFile}`);
