-- =====================================================================
--  Biblioteca Virtual - Script de creacion de la base de datos (SQLite)
--  Ejecutar con:  npm run db:init
--  (el servidor tambien lo ejecuta al arrancar; es idempotente)
-- =====================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS libros (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo            TEXT    NOT NULL,
    autor             TEXT    NOT NULL,
    genero            TEXT    NOT NULL,
    anio_publicacion  INTEGER NOT NULL,
    estado            TEXT    NOT NULL DEFAULT 'Disponible',
    creado_en         TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),

    -- Reglas de negocio reforzadas a nivel de motor de base de datos.
    -- Nota: un CHECK solo admite expresiones deterministas, por eso el limite
    -- "no mayor al anio actual" se aplica con un trigger (ver mas abajo).
    CONSTRAINT ck_libros_titulo  CHECK (length(trim(titulo)) > 0),
    CONSTRAINT ck_libros_autor   CHECK (length(trim(autor))  > 0),
    CONSTRAINT ck_libros_genero  CHECK (length(trim(genero)) > 0),
    CONSTRAINT ck_libros_anio    CHECK (anio_publicacion > 0 AND anio_publicacion <= 9999),
    CONSTRAINT ck_libros_estado  CHECK (estado IN ('Disponible', 'Prestado'))
);

-- Evita duplicados de (titulo + autor) sin distinguir mayusculas ni espacios sobrantes
CREATE UNIQUE INDEX IF NOT EXISTS ux_libros_titulo_autor
    ON libros (lower(trim(titulo)), lower(trim(autor)));

-- Indice de apoyo para el listado ordenado por autor y titulo
CREATE INDEX IF NOT EXISTS ix_libros_orden
    ON libros (autor COLLATE NOCASE, titulo COLLATE NOCASE);

-- Regla: el anio de publicacion no puede ser mayor al anio actual
CREATE TRIGGER IF NOT EXISTS tg_libros_anio_no_futuro_insert
BEFORE INSERT ON libros
FOR EACH ROW
WHEN NEW.anio_publicacion > CAST(strftime('%Y', 'now', 'localtime') AS INTEGER)
BEGIN
    SELECT RAISE(ABORT, 'CHECK constraint failed: anio_publicacion no puede ser mayor al anio actual');
END;

CREATE TRIGGER IF NOT EXISTS tg_libros_anio_no_futuro_update
BEFORE UPDATE OF anio_publicacion ON libros
FOR EACH ROW
WHEN NEW.anio_publicacion > CAST(strftime('%Y', 'now', 'localtime') AS INTEGER)
BEGIN
    SELECT RAISE(ABORT, 'CHECK constraint failed: anio_publicacion no puede ser mayor al anio actual');
END;
