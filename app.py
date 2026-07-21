"""
Punto de entrada de QSL Manager.

- Levanta el servidor FastAPI en un hilo aparte (127.0.0.1, puerto fijo).
- Abre una ventana nativa con PyWebview apuntando a ese servidor.

Si PyWebview no está disponible (por ejemplo, corriendo en un servidor sin
entorno gráfico, como una Raspberry Pi headless), cae de vuelta a modo
"solo servidor" y el usuario abre el navegador manualmente.
"""
import threading
import time

import uvicorn

HOST = "127.0.0.1"
PORT = 8756


def run_server():
    from qsl_manager.server import app
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.2)  # dar tiempo a que el servidor levante

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
