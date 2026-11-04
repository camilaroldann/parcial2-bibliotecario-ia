import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';
import { config } from '../shared/config.js';

/**
 * CAPA DE ACCESO A DATOS - Conexión
 * Única responsabilidad: abrir (y reutilizar) la conexión con SQLite.
 * Ninguna otra capa importa `node:sqlite` directamente.
 */

let db = null;

export function getDb() {
    if (db) return db;

    fs.mkdirSync(path.dirname(config.dbFile), { recursive: true });

    db = new DatabaseSync(config.dbFile);
    db.exec('PRAGMA foreign_keys = ON;');
    db.exec('PRAGMA journal_mode = WAL;');
    return db;
}

/** Crea las tablas e índices ejecutando db/schema.sql (idempotente). */
export function initSchema() {
    const schema = fs.readFileSync(config.schemaFile, 'utf8');
    getDb().exec(schema);
}

export function closeDb() {
    if (db) {
        db.close();
        db = null;
    }
}
