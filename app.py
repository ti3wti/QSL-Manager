"""
Punto de entrada de QSL Manager.

- Levanta el servidor FastAPI en un hilo aparte (127.0.0.1, puerto fijo).
- Abre una ventana nativa con PyWebview apuntando a ese servidor.

Si PyWebview no está disponible (por ejemplo, corriendo en un servidor sin
entorno gráfico, como una Raspberry Pi headless), cae de vuelta a modo
"solo servidor" y el usuario abre el navegador manualmente.
"""
import sys
import threading
import time
import traceback

# En modo --windowed (PyInstaller sin consola), sys.stdout y sys.stderr
# no son "silenciosos": son directamente None. Cualquier print() o
# librería que intente escribir ahí (como el logging por defecto de
# Uvicorn, que revisa si la salida es una terminal) revienta con
# AttributeError antes de que el servidor llegue a arrancar. Se
# reemplazan por streams que no hacen nada -- nadie va a ver ese output
# de todas formas al no haber consola.
if sys.stdout is None:
    import io
    sys.stdout = io.StringIO()
if sys.stderr is None:
    import io
    sys.stderr = io.StringIO()

import uvicorn

from qsl_manager.paths import BASE_DIR

HOST = "127.0.0.1"
PORT = 8756
ERROR_LOG_PATH = BASE_DIR / "error_log.txt"

_server_error = None


def run_server():
    global _server_error
    try:
        from qsl_manager.server import app
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=None)
    except Exception as e:
        # Si esto revienta (por ejemplo, --windowed sin consola donde el
        # error no se ve en ningún lado), al menos queda registrado en un
        # archivo junto al .exe -- sin esto, la ventana simplemente no
        # logra conectarse y no hay forma de saber por qué.
        _server_error = traceback.format_exc()
        try:
            ERROR_LOG_PATH.write_text(_server_error, encoding="utf-8")
        except Exception:
            pass


def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.2)  # dar tiempo a que el servidor levante

    if _server_error:
        # El servidor no pudo arrancar -- avisar en vez de abrir una
        # ventana que solo va a mostrar "no se puede acceder".
        print("El servidor no pudo arrancar. Detalle:")
        print(_server_error)
        print(f"\nQuedó guardado en: {ERROR_LOG_PATH}")
        try:
            import webview
            webview.create_window(
                "QSL Manager - Error al iniciar",
                html=f"<pre style='white-space:pre-wrap;font-family:monospace;padding:20px;'>"
                     f"No se pudo iniciar el servidor interno.\n\n{_server_error}\n\n"
                     f"Este texto también quedó guardado en:\n{ERROR_LOG_PATH}</pre>",
                width=900, height=600,
            )
            webview.start()
        except ImportError:
            pass
        return

    url = f"http://{HOST}:{PORT}"

    try:
        import webview
        webview.create_window("QSL Manager - TI3WTI", url, width=1200, height=800)
        webview.start()
    except ImportError:
        print(f"PyWebview no está instalado. Abre manualmente: {url}")
        print("Presiona Ctrl+C para salir.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
