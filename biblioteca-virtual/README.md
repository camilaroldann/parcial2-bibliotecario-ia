# Biblioteca Virtual

Aplicación web para gestionar el catálogo de libros de una biblioteca virtual, construida con **arquitectura en 3 capas**.

---

## 1. Stack tecnológico

| Capa | Tecnología | Por qué |
|------|-----------|---------|
| Front end | HTML5 + CSS3 + JavaScript (vanilla) | Sin build ni transpilación: se abre y funciona. Menos piezas que puedan fallar en un entorno local. |
| API / negocio | Node.js 22+ con Express 5 | Estándar de facto, mínimo boilerplate, mismo lenguaje en todas las capas. |
| Acceso a datos | SQLite mediante `node:sqlite` (módulo nativo de Node) | Base de datos real (SQL, restricciones, índices) en un único archivo. **Sin instalar ningún motor** y sin dependencias nativas que compilar. |

**Única dependencia externa: Express.** Todo lo demás viene con Node.

---

## 2. Estructura del proyecto

```
biblioteca-virtual/
├── package.json
├── README.md
│
├── db/
│   ├── schema.sql                      # Script de creación de la base de datos
│   └── biblioteca.db                   # Archivo SQLite (se genera automáticamente)
│
├── public/                             # ══ CAPA 1: FRONT END ══
│   ├── index.html                      #   Menú + vista "Cargar libro" + vista "Listar libros"
│   ├── css/styles.css                  #   Estilos
│   └── js/app.js                       #   Navegación, captura de datos y consumo de la API
│
└── src/
    ├── server.js                       # Punto de entrada (arranca el esquema y el servidor)
    ├── app.js                          # Ensamblado de Express
    │
    ├── api/                            # ══ CAPA 2: API / LÓGICA DE NEGOCIO ══
    │   ├── routes/
    │   │   ├── index.js                #   Enrutador raíz (/api)
    │   │   └── libros.routes.js        #   Rutas del recurso libros
    │   ├── controllers/
    │   │   └── libros.controller.js    #   Adaptación HTTP <-> servicio
    │   ├── services/
    │   │   └── libros.service.js       #   REGLAS DE NEGOCIO Y VALIDACIONES
    │   └── middlewares/
    │       └── error-handler.js        #   Traducción de errores de dominio a HTTP
    │
    ├── data/                           # ══ CAPA 3: ACCESO A DATOS ══
    │   ├── connection.js               #   Conexión SQLite + ejecución del esquema
    │   ├── libros.repository.js        #   Sentencias SQL y mapeo fila <-> objeto
    │   └── init-db.js                  #   Script `npm run db:init`
    │
    └── shared/
        ├── config.js                   # Configuración (puerto, rutas, estados válidos)
        └── errors.js                   # Errores de dominio (Validation / Conflict / NotFound)
```

### Separación de responsabilidades

| Capa | Sí hace | No hace |
|------|---------|---------|
| **Front end** (`public/`) | Menú, formulario, tabla, mensajes al usuario | No accede a la base de datos ni decide reglas |
| **API** (`src/api/`) | Expone endpoints, valida reglas de negocio, traduce errores a HTTP | No escribe SQL |
| **Datos** (`src/data/`) | SQL, mapeo de filas, orden en el motor | No valida reglas de negocio ni conoce HTTP |

El flujo es siempre unidireccional: `front end → controller → service → repository → SQLite`.
`node:sqlite` se importa **exclusivamente** en `src/data/connection.js`; cambiar SQLite por PostgreSQL sólo afectaría a la capa de datos.

---

## 3. Modelo de datos

**Tabla `libros`**

| Columna | Tipo | Restricciones |
|---------|------|---------------|
| `id` | INTEGER | PK, autoincremental |
| `titulo` | TEXT | NOT NULL, no vacío |
| `autor` | TEXT | NOT NULL, no vacío |
| `genero` | TEXT | NOT NULL, no vacío |
| `anio_publicacion` | INTEGER | NOT NULL, > 0 y ≤ año actual (trigger) |
| `estado` | TEXT | NOT NULL, DEFAULT `'Disponible'`, sólo `'Disponible'` o `'Prestado'` |
| `creado_en` | TEXT | NOT NULL, DEFAULT fecha/hora local |

**Índices**

- `ux_libros_titulo_autor` — ÚNICO sobre `lower(trim(titulo)), lower(trim(autor))`: impide duplicados aunque cambien mayúsculas o espacios.
- `ix_libros_orden` — sobre `autor COLLATE NOCASE, titulo COLLATE NOCASE`: sostiene el orden del listado.

**Triggers**

- `tg_libros_anio_no_futuro_insert` / `..._update` — rechazan un año mayor al actual. Se resuelve con trigger porque SQLite no admite funciones no deterministas (`strftime('now')`) dentro de un `CHECK`.

Las reglas viven en la capa de negocio (mensajes claros para el usuario) **y** en la base de datos (integridad garantizada aunque alguien inserte por fuera de la API).

---

## 4. Endpoints de la API

Base: `http://localhost:3000/api`

| Método | Ruta | Descripción | Respuestas |
|--------|------|-------------|-----------|
| `GET` | `/health` | Estado del servicio | `200` |
| `GET` | `/libros` | Lista todos los libros, ordenados por autor y luego por título | `200` |
| `GET` | `/libros/:id` | Devuelve un libro por id | `200`, `400`, `404` |
| `POST` | `/libros` | Da de alta un libro | `201`, `400`, `409` |
| `PATCH` | `/libros/:id/estado` | **(Parcial 2)** Préstamo / devolución: `{"estado": "Prestado"}` o `{"estado": "Disponible"}`. Sólo se presta un libro disponible y sólo se devuelve uno prestado. | `200`, `400`, `404`, `409` |

> **Agregado en el Parcial 2:** el endpoint `PATCH /libros/:id/estado` y el script `npm run db:seed`, que carga un catálogo de ejemplo para la demo del agente (pasa por las mismas validaciones de la capa de negocio).

### `POST /api/libros`

```json
{
  "titulo": "Rayuela",
  "autor": "Julio Cortázar",
  "genero": "Novela",
  "anioPublicacion": 1963,
  "estado": "Disponible"
}
```

`201 Created`

```json
{
  "ok": true,
  "mensaje": "Libro cargado correctamente.",
  "dato": {
    "id": 1, "titulo": "Rayuela", "autor": "Julio Cortázar",
    "genero": "Novela", "anioPublicacion": 1963,
    "estado": "Disponible", "creadoEn": "2026-08-20 21:36:12"
  }
}
```

`400 Bad Request` — errores por campo, que el front end muestra debajo de cada input:

```json
{
  "ok": false,
  "mensaje": "Los datos enviados no son válidos.",
  "errores": {
    "titulo": "El título es obligatorio.",
    "anioPublicacion": "El año de publicación no puede ser mayor a 2026."
  }
}
```

`409 Conflict` — título + autor ya existentes:

```json
{
  "ok": false,
  "mensaje": "Ya existe un libro con el título \"Rayuela\" del autor \"Julio Cortázar\"."
}
```

### `GET /api/libros`

```json
{
  "ok": true,
  "total": 2,
  "datos": [
    { "id": 6, "titulo": "La invención de Morel", "autor": "Adolfo Bioy Casares", "genero": "Ciencia ficción", "anioPublicacion": 1940, "estado": "Disponible", "creadoEn": "..." },
    { "id": 1, "titulo": "Rayuela", "autor": "Julio Cortázar", "genero": "Novela", "anioPublicacion": 1963, "estado": "Disponible", "creadoEn": "..." }
  ]
}
```

---

## 5. Reglas de negocio implementadas

| Regla | Dónde se aplica |
|-------|-----------------|
| Todos los campos son obligatorios | `libros.service.js` + `NOT NULL` / `CHECK length(trim(...)) > 0` |
| El año debe ser numérico entero | `libros.service.js` (rechaza `"mil"`, `"19a3"`, decimales) |
| El año debe ser > 0 | `libros.service.js` + `CHECK` |
| El año no puede superar el año actual | `libros.service.js` + trigger |
| El estado sólo puede ser `Disponible` o `Prestado` | `libros.service.js` + `CHECK ... IN (...)` |
| El estado por defecto es `Disponible` | `libros.service.js` + `DEFAULT 'Disponible'` |
| Sin duplicados de título + autor | `libros.service.js` + índice ÚNICO (ignora mayúsculas y espacios) |
| Listado ordenado por autor y luego título | `libros.repository.js` (`ORDER BY ... COLLATE NOCASE`) |

---

## 6. Cómo ejecutar la aplicación localmente

**Requisito:** Node.js 22.5 o superior (probado en Node 24). Verificalo con `node --version`.

```bash
cd biblioteca-virtual
npm install          # instala Express (única dependencia)
npm start            # crea la base si no existe y levanta el servidor
```

Abrí **http://localhost:3000**

Comandos disponibles:

| Comando | Qué hace |
|---------|----------|
| `npm start` | Levanta la aplicación en el puerto 3000 |
| `npm run dev` | Igual, con recarga automática al guardar cambios |
| `npm run db:init` | Crea la base de datos sin levantar el servidor |

Para usar otro puerto o ubicación de la base:

```bash
PORT=4000 npm start                  # Linux / macOS / Git Bash
$env:PORT=4000; npm start            # PowerShell
```

**Para empezar con el catálogo vacío:** cerrá el servidor, borrá `db/biblioteca.db` (junto con `-shm` y `-wal` si existen) y volvé a ejecutar `npm start`.

---

## 7. Uso

1. **Cargar libro** — completá título, autor, género, año y estado, y presioná *Guardar libro*. Los errores de validación aparecen debajo de cada campo; el resultado se confirma con una notificación.
2. **Listar libros** — muestra el catálogo completo ordenado alfabéticamente por autor y, dentro de cada autor, por título. El botón *Actualizar* recarga los datos desde la API.

---

## 8. Verificación realizada

Probado de punta a punta contra el servidor en ejecución:

- ✅ Alta de libros con los 5 campos → `201` y persistencia en SQLite
- ✅ Listado ordenado por autor y luego por título (ignorando mayúsculas)
- ✅ Campos vacíos → `400` con mensaje por campo
- ✅ Año no numérico, año `0`, año futuro → `400`
- ✅ Año igual al año actual → aceptado
- ✅ Estado inválido (`"Perdido"`) → `400`
- ✅ Estado omitido → se guarda como `Disponible`
- ✅ Título + autor duplicados, incluso con distinta capitalización y espacios → `409`
- ✅ Acentos y caracteres UTF-8 correctos en toda la cadena
- ✅ Ruta de API inexistente → `404`
