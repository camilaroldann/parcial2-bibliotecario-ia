/**
 * CAPA FRONT END
 * Única responsabilidad: navegación, captura de datos y presentación.
 * Toda la persistencia y las reglas se resuelven contra la API en /api/libros.
 */
(function () {
    'use strict';

    const API = '/api/libros';

    const vistas = {
        alta: document.getElementById('vista-alta'),
        listado: document.getElementById('vista-listado'),
    };

    const opcionesMenu = document.querySelectorAll('.menu__opcion');
    const formulario = document.getElementById('form-libro');
    const cuerpoTabla = document.getElementById('tabla-libros');
    const mensajeVacio = document.getElementById('mensaje-vacio');
    const contador = document.getElementById('contador');
    const alerta = document.getElementById('alerta');
    const botonGuardar = formulario.querySelector('button[type="submit"]');

    let temporizadorAlerta = null;

    // ------------------------- Navegación del menú -------------------------

    function mostrarVista(nombre) {
        Object.entries(vistas).forEach(([clave, seccion]) => {
            seccion.classList.toggle('vista--oculta', clave !== nombre);
        });

        opcionesMenu.forEach((boton) => {
            boton.classList.toggle('menu__opcion--activa', boton.dataset.vista === nombre);
        });

        if (nombre === 'listado') cargarLibros();
        if (nombre === 'alta') document.getElementById('titulo').focus();
    }

    opcionesMenu.forEach((boton) => {
        boton.addEventListener('click', () => mostrarVista(boton.dataset.vista));
    });

    document.getElementById('btn-refrescar').addEventListener('click', cargarLibros);

    // ------------------------- Utilidades de UI -------------------------

    function mostrarAlerta(mensaje, tipo) {
        clearTimeout(temporizadorAlerta);
        alerta.textContent = mensaje;
        alerta.className = `alerta alerta--${tipo}`;
        temporizadorAlerta = setTimeout(() => alerta.classList.add('vista--oculta'), 4500);
    }

    function limpiarErrores() {
        formulario.querySelectorAll('.campo__error').forEach((elemento) => (elemento.textContent = ''));
        formulario.querySelectorAll('.campo').forEach((campo) => campo.classList.remove('campo--invalido'));
    }

    function pintarErrores(errores) {
        Object.entries(errores || {}).forEach(([campo, mensaje]) => {
            const contenedor = formulario.querySelector(`.campo__error[data-error="${campo}"]`);
            if (contenedor) {
                contenedor.textContent = mensaje;
                contenedor.closest('.campo').classList.add('campo--invalido');
            }
        });
    }

    // ------------------------- Alta de libros -------------------------

    formulario.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        limpiarErrores();

        const datos = {
            titulo: document.getElementById('titulo').value,
            autor: document.getElementById('autor').value,
            genero: document.getElementById('genero').value,
            anioPublicacion: document.getElementById('anioPublicacion').value,
            estado: document.getElementById('estado').value,
        };

        botonGuardar.disabled = true;

        try {
            const respuesta = await fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(datos),
            });
            const cuerpo = await respuesta.json();

            if (!respuesta.ok) {
                pintarErrores(cuerpo.errores);
                mostrarAlerta(cuerpo.mensaje || 'No se pudo guardar el libro.', 'error');
                return;
            }

            formulario.reset();
            limpiarErrores();
            mostrarAlerta(`"${cuerpo.dato.titulo}" se cargó correctamente.`, 'exito');
            document.getElementById('titulo').focus();
        } catch (error) {
            mostrarAlerta('No se pudo conectar con el servidor.', 'error');
        } finally {
            botonGuardar.disabled = false;
        }
    });

    formulario.addEventListener('reset', () => setTimeout(limpiarErrores, 0));

    // ------------------------- Listado de libros -------------------------

    function crearCelda(texto) {
        const celda = document.createElement('td');
        celda.textContent = texto;
        return celda;
    }

    function crearFila(libro) {
        const fila = document.createElement('tr');
        fila.append(
            crearCelda(libro.titulo),
            crearCelda(libro.autor),
            crearCelda(libro.genero),
            crearCelda(libro.anioPublicacion)
        );

        const celdaEstado = document.createElement('td');
        const etiqueta = document.createElement('span');
        etiqueta.className = `etiqueta etiqueta--${libro.estado.toLowerCase()}`;
        etiqueta.textContent = libro.estado;
        celdaEstado.appendChild(etiqueta);
        fila.appendChild(celdaEstado);

        return fila;
    }

    async function cargarLibros() {
        try {
            const respuesta = await fetch(API);
            const cuerpo = await respuesta.json();

            if (!respuesta.ok) {
                mostrarAlerta(cuerpo.mensaje || 'No se pudo obtener el listado.', 'error');
                return;
            }

            const libros = cuerpo.datos || [];
            cuerpoTabla.replaceChildren(...libros.map(crearFila));

            const hayLibros = libros.length > 0;
            mensajeVacio.classList.toggle('vista--oculta', hayLibros);
            contador.textContent = hayLibros
                ? `${libros.length} libro${libros.length === 1 ? '' : 's'} en el catálogo.`
                : '';
        } catch (error) {
            mostrarAlerta('No se pudo conectar con el servidor.', 'error');
        }
    }

    // ------------------------- Arranque -------------------------

    mostrarVista('alta');
})();
