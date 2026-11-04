import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Raíz del proyecto (un nivel arriba de /src). */
export const ROOT_DIR = path.resolve(__dirname, '..', '..');

export const config = {
    port: Number(process.env.PORT) || 3000,
    dbFile: process.env.DB_FILE || path.join(ROOT_DIR, 'db', 'biblioteca.db'),
    schemaFile: path.join(ROOT_DIR, 'db', 'schema.sql'),
    publicDir: path.join(ROOT_DIR, 'public'),
};

/** Valores admitidos para el campo "estado" de un libro. */
export const ESTADOS = Object.freeze(['Disponible', 'Prestado']);
export const ESTADO_POR_DEFECTO = 'Disponible';
