"""Estado pendiente conversacional.

Cuando una skill muestra una lista de opciones (videos, archivos, etc.),
guarda el contexto en este modulo. La siguiente frase del usuario
puede ser interpretada como una seleccion ("la primera", "el 3", "cancela").

Uso:
    from core import pending_state as ps
    ps.set_pending("youtube_select", {"videos": [...]})
    
    # Siguiente frase:
    pend = ps.get_pending()
    if pend and ps.es_seleccion(texto):
        numero = ps.parsear_seleccion(texto, len(pend["data"]["videos"]))
        ...
"""
import re
import time
from threading import Lock

_lock = Lock()

# Timeout en segundos (si el usuario no responde en este tiempo, expira)
PENDING_TIMEOUT = 300  # 5 minutos

_pending = {
    "tipo": None,       # "youtube_select", "opciones", etc.
    "data": {},         # datos especificos del tipo
    "creado": 0,        # timestamp
}


def set_pending(tipo, data=None):
    """Marca un estado pendiente."""
    with _lock:
        _pending["tipo"] = tipo
        _pending["data"] = data or {}
        _pending["creado"] = time.time()


def get_pending():
    """Devuelve el estado pendiente o None si expiro/no existe."""
    with _lock:
        if _pending["tipo"] is None:
            return None
        # Verificar timeout
        if time.time() - _pending["creado"] > PENDING_TIMEOUT:
            _pending["tipo"] = None
            _pending["data"] = {}
            return None
        return dict(_pending)


def clear():
    """Limpia el estado pendiente."""
    with _lock:
        _pending["tipo"] = None
        _pending["data"] = {}
        _pending["creado"] = 0


def es_seleccion(texto):
    """Detecta si el texto es una seleccion simple."""
    t = texto.lower().strip()
    if not t:
        return False
    # Cancelar
    if t in ("cancela", "cancelar", "no", "olvidalo", "olvidalo", "salir", "exit"):
        return True
    # Numero simple: "1", "2", "3", "el 1", "la 2", "opcion 3"
    if re.match(r'^(?:el|la|opcion|num|numero)?\s*\d+$', t):
        return True
    # Ordinales: "la primera", "el segundo", "el tercero", "el ultimo"
    if re.match(r'^(?:el|la)\s+(?:primero|primera|segundo|segunda|tercero|tercera|cuarto|quinta|ultimo|ultima)$', t):
        return True
    # Referencias simples
    if t in ("ese", "esa", "aquel", "aquella"):
        return True
    return False


def parsear_seleccion(texto, max_opciones):
    """Convierte un texto de seleccion a un indice (0-based).
    
    Devuelve:
        - int >= 0: indice valido
        - -1: usuario cancelo
        - -2: no se pudo interpretar
    """
    t = texto.lower().strip()
    # Cancelar
    if t in ("cancela", "cancelar", "no", "olvidalo", "olvidalo", "salir", "exit"):
        return -1
    # Numero: "1", "el 1", "opcion 3"
    m = re.match(r'^(?:el|la|opcion|num|numero)?\s*(\d+)$', t)
    if m:
        n = int(m.group(1))
        if 1 <= n <= max_opciones:
            return n - 1
        return -2
    # Ordinales
    ordinales = {
        "primero": 0, "primera": 0,
        "segundo": 1, "segunda": 1,
        "tercero": 2, "tercera": 2,
        "cuarto": 3, "cuarta": 3,
        "quinto": 4, "quinta": 4,
        "ultimo": max_opciones - 1, "ultima": max_opciones - 1,
    }
    m = re.match(r'^(?:el|la)\s+(\w+)$', t)
    if m and m.group(1) in ordinales:
        return ordinales[m.group(1)]
    # Referencias
    if t in ("ese", "esa"):
        return 0
    return -2


if __name__ == "__main__":
    # Test rapido
    print("=== Test pending_state ===")
    set_pending("youtube_select", {"videos": ["v1", "v2", "v3", "v4", "v5"]})
    print("Pending:", get_pending())
    print()
    for texto in ["la primera", "el 3", "opcion 2", "cancela", "el ultimo", "5", "hola mundo"]:
        if es_seleccion(texto):
            idx = parsear_seleccion(texto, 5)
            print(f"  '{texto}' -> seleccion, idx={idx}")
        else:
            print(f"  '{texto}' -> NO es seleccion")