/**
 * Carga un catálogo de ejemplo para la demo del agente: `npm run db:seed`
 * Pasa por la capa de negocio (mismas validaciones que la API) y es idempotente:
 * los libros que ya existen se saltean.
 */
import { initSchema, closeDb } from './connection.js';
import { crearLibro } from '../api/services/libros.service.js';
import { ConflictError } from '../shared/errors.js';
import { config } from '../shared/config.js';

const LIBROS = [
    { titulo: 'Rayuela', autor: 'Julio Cortázar', genero: 'Novela', anioPublicacion: 1963 },
    { titulo: 'Bestiario', autor: 'Julio Cortázar', genero: 'Cuentos', anioPublicacion: 1951 },
    { titulo: 'Ficciones', autor: 'Jorge Luis Borges', genero: 'Cuentos', anioPublicacion: 1944 },
    { titulo: 'El Aleph', autor: 'Jorge Luis Borges', genero: 'Cuentos', anioPublicacion: 1949, estado: 'Prestado' },
    { titulo: 'La invención de Morel', autor: 'Adolfo Bioy Casares', genero: 'Ciencia ficción', anioPublicacion: 1940 },
    { titulo: 'El túnel', autor: 'Ernesto Sabato', genero: 'Novela psicológica', anioPublicacion: 1948 },
    { titulo: 'Cien años de soledad', autor: 'Gabriel García Márquez', genero: 'Realismo mágico', anioPublicacion: 1967 },
    { titulo: 'Fahrenheit 451', autor: 'Ray Bradbury', genero: 'Ciencia ficción', anioPublicacion: 1953 },
    { titulo: 'Crónicas marcianas', autor: 'Ray Bradbury', genero: 'Ciencia ficción', anioPublicacion: 1950, estado: 'Prestado' },
    { titulo: '1984', autor: 'George Orwell', genero: 'Distopía', anioPublicacion: 1949 },
    { titulo: 'Un mundo feliz', autor: 'Aldous Huxley', genero: 'Distopía', anioPublicacion: 1932 },
    { titulo: 'Las ventajas de ser invisible', autor: 'Stephen Chbosky', genero: 'Novela juvenil', anioPublicacion: 1999 },
    { titulo: 'El principito', autor: 'Antoine de Saint-Exupéry', genero: 'Fábula', anioPublicacion: 1943 },
    { titulo: 'Clean Code', autor: 'Robert C. Martin', genero: 'Programación', anioPublicacion: 2008 },
    { titulo: 'Diseño de sistemas de datos intensivos', autor: 'Martin Kleppmann', genero: 'Programación', anioPublicacion: 2017 },
    { titulo: 'Las cosas que perdimos en el fuego', autor: 'Mariana Enriquez', genero: 'Terror', anioPublicacion: 2016 },
];

initSchema();

let cargados = 0;
for (const libro of LIBROS) {
    try {
        crearLibro(libro);
        cargados++;
    } catch (error) {
        if (!(error instanceof ConflictError)) throw error;
    }
}

closeDb();
console.log(`Catálogo de ejemplo: ${cargados} libros nuevos (${LIBROS.length - cargados} ya existían) en ${config.dbFile}`);
