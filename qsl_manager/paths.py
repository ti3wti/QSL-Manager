"""
Rutas base de la app -- consciente de si corre como script normal o
empaquetada con PyInstaller (--onefile).

Este es el motivo real por el que, al empaquetar el .exe, la app se abría
pero no lograba conectarse: con PyInstaller onefile, `sys.executable`
apunta al .exe real (persistente, donde el usuario lo guardó), pero el
`__file__` de los módulos Python apunta a una carpeta TEMPORAL que
PyInstaller crea al arrancar y BORRA al cerrar el programa. Si la base de
datos, la configuración y las QSLs importadas se guardan ahí, se pierden
cada vez que se cierra la app -- y en algunos casos ni siquiera llega a
arrancar bien.

Por eso hay dos rutas separadas:
- BASE_DIR: para datos que el usuario genera y deben persistir (data/).
  Junto al .exe si está empaquetado; la raíz del proyecto si corre desde
  el código fuente.
- RESOURCE_DIR: para recursos empaquetados de solo lectura (static/,
  tesseract-bin/ si vino incluido en el build). Con PyInstaller onefile
  viven en la carpeta temporal de extracción (sys._MEIPASS) -- está bien
  que sea temporal porque solo se leen, nunca se escriben.
"""
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

if FROZEN and hasattr(sys, "_MEIPASS"):
    RESOURCE_DIR = Path(sys._MEIPASS)
else:
    RESOURCE_DIR = Path(__file__).resolve().parent.parent
