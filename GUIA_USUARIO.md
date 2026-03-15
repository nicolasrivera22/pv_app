# PVWorkbench — Guía rápida para Windows

Esta guía es para la persona que va a probar el ejecutable de PVWorkbench en Windows.

## Qué es esta app

PVWorkbench es una herramienta local para analizar diseños solares fotovoltaicos, comparar alternativas y revisar resultados económicos y energéticos de manera visual.

La app funciona en tu navegador, pero **no requiere internet** para correr localmente. El ejecutable abre un servidor local y luego abre la app automáticamente en el navegador.

## Cómo abrir la app

1. Abre la carpeta `PVWorkbench` entregada.
2. Haz doble clic en `PVWorkbench.exe`.
3. Espera unos segundos.
4. La app debería abrirse automáticamente en tu navegador.

Si no se abre sola:

- espera un poco más
- revisa si Windows mostró una advertencia de seguridad
- intenta abrir de nuevo el ejecutable

## Flujo recomendado de prueba

### 1. Cargar el ejemplo

En la página principal, carga el ejemplo incluido para confirmar que la app está funcionando bien.

### 2. Ejecutar un barrido determinístico

Haz correr el análisis determinístico y verifica que aparezcan:

- curva VPN vs kWp
- tabla de candidatos
- resumen del diseño seleccionado
- gráficos de análisis detallado
- esquema unifilar / esquemático

### 3. Probar cambios básicos

Prueba editar algunos parámetros sencillos, por ejemplo:

- consumo mensual
- precios
- inclusión de batería
- parámetros financieros básicos

Luego aplica cambios y vuelve a correr el análisis.

### 4. Guardar y reabrir proyecto

Guarda el proyecto, cierra la app y vuelve a abrirlo. Comprueba que el proyecto se pueda reabrir correctamente.

### 5. Exportar resultados

Prueba la exportación y verifica que se generen archivos en la carpeta del proyecto o en la carpeta `Resultados`.

### 6. Probar la página de riesgo

Si ya tienes un escenario determinístico resuelto, entra a la página de riesgo y corre una simulación Monte Carlo pequeña.

## Qué feedback nos sirve mucho

Por favor anota cosas como:

- partes que no entiendes
- botones o acciones que no son evidentes
- pantallas que se sienten lentas
- mensajes de error raros
- resultados que te sorprenden o parecen inconsistentes
- pasos que esperabas hacer más fácil

No solo nos interesan los bugs: también nos interesa saber **dónde la app confunde**.

## Problemas comunes

### La app no abre en el navegador

- espera unos segundos más
- vuelve a ejecutar `PVWorkbench.exe`
- revisa si tu antivirus o Windows bloqueó la ejecución

### La app abre pero algo no carga

Cierra la app, vuelve a abrirla y prueba primero con el ejemplo incluido.

### No sé dónde quedaron los resultados exportados

Busca en:

- la carpeta `Resultados`
- o dentro del proyecto guardado en `proyectos/<nombre>/exports/Resultados/`

## Importante

- Esta es una app local de prueba, no una plataforma web multiusuario.
- El objetivo de esta etapa es validar uso real, claridad, estabilidad y empaquetado en Windows.
