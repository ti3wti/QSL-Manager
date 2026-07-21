# QSL Manager - IA based QSL Recognizer

[![Descargar QSL Manager](https://img.shields.io/badge/⬇️_Descargar-QSLManager.exe-brightgreen?style=for-the-badge)](https://github.com/ti3wti/QSL-Manager/releases/latest/download/QSLManager.exe)

🇪🇸 Español | [🇬🇧 English](README.en.md)

App local (Windows) para organizar tarjetas QSL de radioaficionados:
importa imágenes o PDFs, reconoce los datos automáticamente (indicativo,
país, fecha, banda, modo, locator), y las muestra en galería, mapa y
presentación -- con filtros por país y modo, importación directa desde
eQSL.cc, y reconocimiento local (sin internet) o por IA (más preciso).

Todo corre 100% en tu PC. Lo único que sale a internet es: los tiles del
mapa (OpenStreetMap), las llamadas a Gemini si activaste la IA, la
descarga desde eQSL.cc si la usás, y el ping opcional de estadísticas de
uso (podés desactivarlo).

## 1. Instalación

**¿Tenés el archivo `QSLManager.exe`?** Doble clic y listo -- no hace
falta instalar Python, ni `pip`, ni nada de lo que sigue en esta sección.
El `.exe` ya trae adentro todo lo necesario (Python, las librerías,
Tesseract). Andá directo a la sección **2. Primer arranque**.

**¿Vas a correrlo desde el código fuente en vez del `.exe`?** (por
ejemplo en Linux/Mac, o porque vas a modificar el código) -- ahí sí hace
falta lo siguiente:

1. **Python 3.10 o superior** — https://www.python.org/downloads/
   Al instalar, marca la casilla "Add Python to PATH".
2. En una terminal (PowerShell), dentro de la carpeta del proyecto:
   ```
   pip install -r requirements.txt
   ```
3. Ejecutar:
   ```
   python app.py
   ```

Se abre una ventana nativa con la app. Si PyWebview no puede abrir la
ventana (por ejemplo en un servidor sin entorno gráfico), el programa
imprime una URL (`http://127.0.0.1:8756`) para abrir en el navegador.

**⚠️ Sobre Tesseract si corrés desde el código fuente**: la app funciona
sin instalar nada de reconocimiento local *solo si* existe la carpeta
`tesseract-bin/` dentro del proyecto (viene incluida si te pasaron el
código completo por fuera de GitHub). **Si clonaste el repo desde GitHub,
esa carpeta NO está** -- se excluye a propósito porque son ~90 MB de
binarios de terceros (ver `.gitignore`). En ese caso, para que el
reconocimiento local funcione, tenés que instalar Tesseract vos mismo:

1. Descargalo de https://github.com/UB-Mannheim/tesseract/wiki
   (instalador para Windows, opciones por defecto)
2. En la app, ⚙ Configuración → campo "Ruta tesseract" → pegá la ruta
   completa a `tesseract.exe` (normalmente
   `C:\Program Files\Tesseract-OCR\tesseract.exe`)

Sin este paso, el reconocimiento local (Tesseract) va a fallar con
"not in your PATH" hasta que configures la ruta. El reconocimiento por
IA (Gemini, sección 4) no depende de esto -- funciona igual sin
Tesseract instalado.

## 2. Primer arranque

La primera vez se abre un asistente que pide:
1. **Idioma** (Español / English) -- también se puede cambiar después
   desde Configuración.
2. **Tu indicativo** -- necesario para que el reconocimiento sepa
   distinguir tu estación del remitente de la QSL. También aparece en el
   encabezado, útil si compartís capturas de pantalla.
3. **Activar IA (opcional)** -- ver sección 4.

Se puede volver a ver este asistente en cualquier momento desde
Configuración → "Ver de nuevo el asistente de bienvenida".

## 3. Uso básico

- **+ Importar QSLs**: selecciona una o varias imágenes/PDF. También podés
  **arrastrar y soltar** archivos directo sobre la ventana.
- Cada tarjeta importada queda marcada **"Revisar reconocimiento"**
  (naranja) hasta que la abras, confirmes o corrijas los campos, y le des
  **"Guardar cambios"** -- ahí queda verificada. Si el reconocimiento
  falló del todo, la insignia sale en rojo ("Error de reconocimiento") con
  el motivo abajo, y podés reintentar con los botones "↻ Reconocimiento
  Local" o "↻ Reconocimiento IA" dentro de la tarjeta.
- **🔁 Revisar pendientes**: reintenta de una sola vez el reconocimiento
  de todas las tarjetas que sigan sin verificar (por ejemplo, si
  importaste varias antes de configurar la IA). Corre en segundo plano,
  se puede seguir usando la app mientras tanto.
- **Filtros**: por país, por modo (FT8, SSB, PSK, RTTY, etc.), y buscador
  de indicativo con botón para limpiar.
- **Orden**: por fecha (reciente/antigua primero) o agrupado por país
  (con encabezados separadores).
- **Vistas**:
  - **Galería**: la vista normal, en tarjetas.
  - **Mapa**: ubica cada QSL con ubicación conocida (prioriza el
    locator/grid square; si no hay, usa el país). Selector de estilo de
    mapa (Voyager, Positron claro, Dark Matter oscuro, OSM clásico)
    disponible ahí mismo y en Configuración.
  - **Presentación**: pasa las QSL una por una en grande, para mostrar.
    Avance automático (segundos configurables, 4 por defecto) o manual
    con los botones / flechas del teclado / barra espaciadora para
    pausar. Respeta los filtros activos.
- **Tema**: claro, oscuro, o igual que el sistema (Configuración).
- **Idioma**: Español / English, con banderas, cambia al instante
  (asistente de bienvenida o Configuración).

## 4. Motor de reconocimiento: Tesseract (local) o IA (Gemini)

Por defecto la app usa **Tesseract** (incluido, sin internet, gratis
siempre). Para tarjetas con logos/fuentes decorativas -- que Tesseract
lee mal -- se puede activar **Google Gemini** (modelo de visión), que
entiende el diseño completo de la tarjeta. Capa gratuita generosa, **no
pide tarjeta de crédito**.

1. Entra a https://aistudio.google.com/apikey con tu cuenta de Google
2. Clic en "Crear Clave de API" y luego "Crear Clave"
3. En la app, ⚙ **Configuración** → pega la key
4. Clic en **"Detectar"** junto a Modelo -- le pregunta a Google en vivo
   qué modelos están disponibles (evita depender de un nombre fijo que
   Google puede retirar sin aviso, como ya pasó más de una vez)
5. Motor en "Automático" y Guardar

Con "Automático": usa Gemini si hay key configurada, si no cae a
Tesseract. También se puede forzar un motor específico (global en
Configuración, o por tarjeta con los botones dentro del detalle).

**Ritmo con IA**: la capa gratuita de Gemini limita solicitudes por
minuto. La app espera automáticamente ~4.5s entre cada llamada -- un
lote de 30 archivos con IA activada toma 2-3 minutos, es normal.

**Problemas comunes:**
- *Tesseract "not in your PATH"*: pega la ruta completa de
  `tesseract.exe` en Configuración (normalmente no hace falta, ya que
  viene incluido en `tesseract-bin/`).
- *Tesseract "[WinError 5] Acceso denegado"*: el antivirus de Windows
  interfiriendo con archivos temporales. La app ya usa su propia carpeta
  (`data/tmp/`) para evitar esto; si persiste, agregar excepción de
  antivirus para la carpeta del proyecto.
- *Gemini falla desde la primera solicitud*: casi siempre un modelo
  retirado por Google. Usar "Detectar" en Configuración.

## 5. Importar desde eQSL.cc

Botón **📥 eQSL** en el encabezado: pide tu indicativo y contraseña de
eQSL.cc, y baja tu bandeja de entrada directamente -- indicativo, fecha,
banda y modo ya vienen confirmados por eQSL, así que esas tarjetas quedan
verificadas sin pasar por reconocimiento.

eQSL no permite descargas rápidas: baja **una tarjeta cada ~2 segundos**,
así que un inbox grande puede tardar varios minutos. Corre en segundo
plano (se puede cerrar el modal y seguir usando la app; una insignia
verde en el encabezado muestra el progreso desde cualquier vista). Se
puede **detener y reanudar** en cualquier momento -- no vuelve a bajar lo
que ya tenés (se guarda un identificador único por tarjeta).

Usuario y contraseña quedan guardados localmente para no escribirlos cada
vez (botón "💾 Guardar y cerrar" si solo querés guardarlos sin descargar
todavía).

## 6. Estadísticas de uso (opcional)

Activado por defecto, se puede desactivar en Configuración. Si está
activo, cada vez que se guarda o abre la app con un indicativo
configurado, se manda un ping (solo el indicativo, nada más -- ni QSLs ni
ningún otro dato) a una hoja de cálculo del desarrollador, para tener una
idea de cuánta gente usa la app. El endpoint vive fijo en el código
(`TELEMETRY_ENDPOINT` en `qsl_manager/server.py`), no es un dato que el
usuario configure.

## 7. Dónde se guardan los datos

- `data/qsl.db` -- base de datos SQLite con todos los metadatos.
- `data/cards/` -- copia de cada imagen/PDF importado (el original queda
  intacto donde estaba).
- `data/config.json` -- configuración (indicativo, API key, credenciales
  de eQSL, preferencias). Todo local, nunca se sube a ningún repositorio.

Para respaldar todo, alcanza con copiar la carpeta `data/`.

## 8. Ampliar el reconocimiento de países

`qsl_manager/prefixes.json` es un diccionario simple
`"PREFIJO": ["País", lat, lon]`. Si llega una QSL de un país que no está
en la lista, se agrega ahí (no hace falta tocar código Python). Además,
si hay locator pero no se pudo determinar el país por otra vía, la app
consulta automáticamente OpenStreetMap (gratis, sin API key) como último
recurso.

## 9. Empaquetar como .exe para compartir

```
pip install pyinstaller
pyinstaller --name QSLManager --onefile --windowed ^
  --add-data "static;static" ^
  --add-data "qsl_manager/prefixes.json;qsl_manager" ^
  --add-data "tesseract-bin;tesseract-bin" ^
  app.py
```

El `.exe` (con Tesseract incluido) queda en `dist/QSLManager.exe`. Cada
persona que lo reciba tiene su propia base de datos local e independiente
-- no hay nada compartido entre instalaciones salvo que se arme
explícitamente un modo servidor central más adelante.

**Sobre `tesseract-bin/` y GitHub**: esa carpeta (~90 MB, decenas de
archivos binarios) no va al repositorio -- está en `.gitignore` a
propósito. Solo hace falta *localmente*, en tu PC, en el momento de
compilar (PyInstaller la lee del disco). Si alguien clona el repo desde
cero y quiere compilar su propio `.exe`, necesita conseguir Tesseract por
su cuenta (instalador en https://github.com/UB-Mannheim/tesseract/wiki)
y copiar esa carpeta ahí, o usar directamente su propia instalación
apuntando la ruta en Configuración en vez de empaquetarla.

## Limitaciones conocidas

- El reconocimiento (Tesseract o IA) es un punto de partida, no siempre
  acierta -- especialmente Tesseract con fuentes decorativas o fondos
  fotográficos cargados. Por diseño, siempre se revisa/corrige antes de
  que la tarjeta quede verificada (salvo eQSL, que viene pre-confirmado).
- El modo IA requiere internet y respeta los límites de la capa gratuita
  de Google.
- La tabla de prefijos de país cubre los DXCC más comunes, no los ~340
  existentes -- se amplía fácilmente, y la geocodificación por locator
  cubre bastante del resto.
- El mapa base (OpenStreetMap/CARTO) no tiene versión en español
  garantizada sin agregar otro proveedor con su propia cuenta (ej.
  MapTiler); los datos propios de cada QSL (país, etc.) sí están en
  español.
- Agrupar/filtrar por estado de EE.UU. no está implementado todavía (el
  prefijo del indicativo no es un indicador confiable del estado real).
