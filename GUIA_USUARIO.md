# PVWorkbench — Guía de uso local

Esta guía está pensada para la persona que va a usar o probar PVWorkbench localmente, sobre todo en Windows con el ejecutable empaquetado.

## Qué hace la app

PVWorkbench sirve para:

- crear escenarios FV o FV con batería
- ajustar supuestos y perfiles
- correr un escaneo determinístico de diseños factibles
- comparar diseños seleccionados
- analizar riesgo económico con Monte Carlo
- guardar proyectos y exportar resultados

La app corre localmente en tu navegador, pero no necesita internet para funcionar.

## Mapa actual de navegación

- `Resultados`: revisión de resultados determinísticos, KPIs, gráficas, tabla de candidatos y esquema unifilar.
- `Supuestos`: configuración del escenario. Aquí también están las acciones para empezar (`Cargar ejemplo`, `Importar Excel`) y el acceso interno hacia `Admin`.
- `Comparar`: comparación lado a lado de diseños seleccionados del último escaneo del escenario activo.
- `Riesgo`: Monte Carlo sobre un diseño fijo ya obtenido en determinístico.
- `Ayuda`: guía de uso dentro de la app.
- `Admin`: acceso interno con PIN local para catálogos, precios y tablas internas.

Importante:

- la edición detallada de demanda ahora vive en `Supuestos > Demanda`
- el acceso interno ya no aparece en `Resultados`; está solo en `Supuestos`
- el PIN de `Admin` es una protección local de uso interno, no autenticación real

## Cómo abrir la app

### En Windows con el ejecutable

1. Abre la carpeta `PVWorkbench` entregada.
2. Haz doble clic en `PVWorkbench.exe`.
3. Espera unos segundos.
4. La app debería abrirse sola en el navegador.

Si no se abre sola:

- espera un poco más
- revisa si Windows mostró una advertencia de seguridad
- vuelve a ejecutar `PVWorkbench.exe`

### Desde el código fuente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python desktop_launcher.py
```

## Cómo empezar desde cero

El punto de arranque más claro está en la sidebar de `Supuestos`.

Tienes dos caminos:

- `Cargar ejemplo`: crea un escenario usando el ejemplo incluido. Es la forma más rápida de validar que todo funciona.
- `Importar Excel`: crea un escenario a partir de un archivo válido y conserva sus catálogos y perfiles.

Si todavía no tienes proyectos guardados, la app te lo indica y te muestra estas dos acciones de arranque.

## Flujo recomendado de uso

### 1. Crear o abrir un escenario

En `Supuestos`:

- usa `Cargar ejemplo` para arrancar rápido
- o usa `Importar Excel` para traer un libro real
- si ya existe un proyecto, ábrelo desde el selector de proyectos

### 2. Ajustar los supuestos

En `Supuestos` verás dos subtabs:

- `Generales`: entradas seguras para trabajar con cliente, restricciones de tamaño y parámetros generales
- `Demanda`: edición detallada de la demanda, perfiles y vistas auxiliares de demanda

Haz primero cambios pequeños y fáciles de verificar.

### 3. Entrar a Admin solo si hace falta

Desde la tarjeta `Acceso interno` en `Supuestos` puedes abrir `Admin`.

`Admin` se usa para:

- supuestos sensibles de precio
- catálogos de inversores y baterías
- tablas internas mensuales, solares y de precios

No uses `Admin` para editar la demanda detallada. Esa parte vive en `Supuestos > Demanda`.

### 4. Correr el escaneo determinístico

Después de ajustar el escenario:

- ejecuta el escaneo determinístico
- revisa la curva VPN vs kWp
- revisa la tabla de candidatos
- selecciona un diseño para ver el análisis detallado

La app puede mostrar contadores o marcadores de descarte. Eso significa que sí se evaluaron tamaños adicionales, pero fueron filtrados por restricciones técnicas antes de aparecer como diseños viables.

### 5. Revisar Resultados

En `Resultados` puedes ver:

- estado del escenario activo
- KPIs del diseño seleccionado
- balance mensual
- flujo de caja descontado acumulado
- cobertura anual y otras gráficas de detalle
- esquema unifilar / esquemático

Esta página es la vista principal para revisar lo que salió del escaneo.

### 6. Comparar diseños

En `Comparar`:

- selecciona diseños del escenario activo
- agrégalos a la shortlist
- revisa tabla resumen y gráficas comparativas

Si cambias el escenario o sus supuestos, vuelve a correr el determinístico antes de comparar de nuevo.

### 7. Correr Riesgo

En `Riesgo`:

- elige un escenario ya resuelto
- elige un diseño factible
- configura Monte Carlo
- corre la simulación
- revisa histogramas, ECDF y percentiles

`Riesgo` sirve para entender la incertidumbre de un diseño elegido, no para buscar un diseño nuevo.

### 8. Guardar y exportar

- `Guardar proyecto` conserva el espacio de trabajo y sus escenarios
- las exportaciones generan archivos fuera de la vista de edición
- según el modo de ejecución, los resultados pueden quedar en `Resultados` o dentro de la carpeta del proyecto

## Qué conviene probar en una validación rápida

1. Cargar el ejemplo.
2. Navegar entre `Resultados`, `Supuestos`, `Comparar`, `Riesgo` y `Ayuda`.
3. Cambiar algunos parámetros básicos.
4. Correr el escaneo determinístico.
5. Seleccionar un diseño y revisar su análisis detallado.
6. Guardar y reabrir un proyecto.
7. Probar `Comparar`.
8. Probar `Riesgo` con pocas simulaciones.
9. Verificar que las exportaciones aparezcan en la ruta esperada.

## Qué feedback ayuda mucho

Anota especialmente:

- partes que no entiendes
- acciones que no son evidentes
- pantallas lentas
- mensajes de error extraños
- resultados que te sorprenden o parecen inconsistentes
- pasos que esperabas hacer más fácil

No solo interesan los bugs. También importa mucho saber dónde la app confunde.

## Problemas comunes

### La app no abre en el navegador

- espera unos segundos más
- vuelve a ejecutar `PVWorkbench.exe`
- revisa si Windows o el antivirus bloquearon la ejecución

### La app abre, pero no sabes cómo empezar

Ve a `Supuestos` y usa una de estas acciones:

- `Cargar ejemplo`
- `Importar Excel`

### No encuentro la edición de demanda

Está en `Supuestos > Demanda`.

### No encuentro el acceso a Admin

Está en `Supuestos`, dentro de la tarjeta `Acceso interno`.

### No sé dónde quedaron los resultados exportados

Busca en:

- la carpeta `Resultados`
- o dentro del proyecto guardado, en su carpeta de exportaciones

## Documentos útiles

- `Ayuda` dentro de la app
- `PVWorkbench_Guia_Rapida.html` como guía visual breve
- `README.md` para visión general del repositorio
- `DEVELOPER_NOTES.md` para mantenimiento técnico

## Importante

- Esta es una app local de prueba.
- No es una plataforma web multiusuario.
- El PIN de `Admin` es una barrera local de uso interno, no seguridad real.
- El objetivo de esta etapa es validar claridad, estabilidad, flujo de uso y empaquetado.
