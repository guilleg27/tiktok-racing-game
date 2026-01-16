"""Resource path helper for PyInstaller compatibility."""

import sys
import os


def resource_path(relative_path: str) -> str:
    """
    Obtiene la ruta absoluta al recurso, compatible con PyInstaller en Windows/macOS/Linux.
    
    Cuando la aplicación está empaquetada con PyInstaller, los recursos
    se extraen a una carpeta temporal _MEIPASS. Esta función maneja
    ambos casos: desarrollo y ejecutable empaquetado.
    
    Args:
        relative_path: Ruta relativa al recurso (ej: "assets/audio/bgm.wav")
        
    Returns:
        str: Ruta absoluta al recurso con separadores correctos para el SO
    """
    # Normalizar separadores de ruta para el SO actual
    # Convierte "assets/audio/bgm.wav" a "assets\\audio\\bgm.wav" en Windows
    normalized_path = os.path.normpath(relative_path)
    
    # Detectar si estamos en un ejecutable empaquetado
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller crea una carpeta temporal y almacena la ruta en _MEIPASS
        base_path = sys._MEIPASS
    else:
        # Desarrollo: usar el directorio del proyecto (donde está main.py)
        # Buscar hacia arriba hasta encontrar la raíz del proyecto
        base_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        
        # Fallback: directorio actual si la estructura es diferente
        if not os.path.exists(os.path.join(base_path, normalized_path)):
            base_path = os.path.abspath(".")
    
    return os.path.join(base_path, normalized_path)


def is_frozen() -> bool:
    """
    Detecta si la aplicación está ejecutándose como ejecutable empaquetado.
    
    Returns:
        bool: True si está empaquetado con PyInstaller, False en desarrollo
    """
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')