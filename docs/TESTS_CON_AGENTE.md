# Pruebas diseñadas con el agente **@Tester**

Las suites de `tests/` se construyeron con un agente de desarrollo declarativo, separado del agente de producción. La separación sigue el principio de la clase de Multiagentes: **quien escribe el código no es quien lo audita**.

- Definición: [`.github/agents/tester.agent.md`](../.github/agents/tester.agent.md). Contiene rol, alcance (solo escribe en `tests/`), flujo de trabajo, formato de salida y restricciones.
- Dónde se invoca: **VS Code + GitHub Copilot Chat**, que detecta solo los archivos de `.github/agents/`. En el selector de agentes se elige `Tester` o se escribe `@Tester`. En Antigravity se vincula el mismo archivo desde *Agent Customizations → Agents*.

## Flujo de trabajo usado

1. **Diseño.** @Tester lee el módulo y arma la tabla de casos antes de escribir código: *happy path*, límites, excepciones y seguridad.
2. **Implementación.** Escribe los tests con patrón AAA y `parametrize`, usando los dobles de `tests/conftest.py`.
3. **Ejecución.** Corre pytest con cobertura y reporta el resultado.
4. **Iteración.** Con las líneas sin cubrir del reporte, propone casos nuevos.

## Prompts de ejemplo

```text
@Tester Diseñá la tabla de casos para validar_libro de src/bibliotecario/validacion.py.
Incluí límites del año (0, negativo, año actual, año actual + 1, dos cifras), tipos
incorrectos (bool, float, texto no numérico) y el límite de 200 caracteres por campo.
```

```text
@Tester Implementá tests unitarios AAA para RecomendarLibros usando LLMFalso y
BibliotecaFalsa. Cubrí: ids inventados por el modelo, ids repetidos, más de 3
recomendaciones, ids como texto y catálogo sin libros disponibles (no debe llamar al LLM).
```

```text
@Tester Escribí pruebas integradas contra la API real usando el fixture api_real:
alta, duplicado con otra capitalización (409), errores 400 por campo, préstamo dos
veces (409) y un payload de inyección SQL que debe guardarse como texto literal.
```

```text
@Tester Corré la suite con cobertura y proponé tests para las líneas que faltan en
src/bibliotecario/skills.py.
```

## Hallazgos reales de las pruebas

1. **Respuesta con array.** El caso `'[{"skill": "x"}]'` de `test_extraer_json_respuestas_invalidas_lanzan_error` **falló en la primera corrida**. Cuando el modelo respondía con un *array*, `extraer_json` tomaba el objeto de adentro en lugar de rechazar la respuesta. Se corrigió `llm.extraer_json` para que primero intente parsear la respuesta completa y la rechace si no es un objeto.
2. **El modelo copiaba los ids del ejemplo few-shot.** Al probar el agente con el catálogo real, *"Recomendame algo de ciencia ficción"* devolvía *Ficciones* (cuentos). El ejemplo de `recomendar_libros.skill.md` usaba el id 3 para *Fahrenheit 451*, y el modelo de 3B copiaba ese 3, que en la base real es *Ficciones*. El test existente no lo había detectado porque en `CATALOGO_EJEMPLO` el id 3 también era *Fahrenheit 451*. Se agregó `test_recomendacion_real_no_copia_ids_del_ejemplo_few_shot`, que usa el catálogo del seed con sus ids reales: **falla con el prompt viejo** y pasa una vez que los ids del ejemplo se cambiaron por 101, 102 y 103, que no existen en ningún catálogo. Si el modelo los copia igual, el filtro de ids inventados los descarta. La lección es que en los ejemplos few-shot no conviene usar valores que puedan coincidir con datos reales.

## Cómo ejecutarlas

```powershell
.\.venv\Scripts\python.exe -m pytest -v --cov=bibliotecario --cov-report=term-missing
.\.venv\Scripts\python.exe -m pytest -m ollama -v          # contra el modelo real
```
