"""Trace de ejecucion multiagente."""
import json
from datetime import datetime
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parent.parent.parent
TRACE_DIR = ROOT / "memory" / "traces"


class Trace:
    def __init__(self, sesion_id: str = None):
        self.sesion_id = sesion_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.pasos = []
        self._lock = Lock()

    def log(self, result):
        with self._lock:
            self.pasos.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "agente": getattr(result, "agente", "?"),
                "tarea": getattr(result, "tarea", "")[:200],
                "respuesta": getattr(result, "respuesta", "")[:300],
                "exito": getattr(result, "exito", False),
                "tiempo": round(getattr(result, "tiempo_seg", 0), 2),
                "error": getattr(result, "error", ""),
            })

    def log_evento(self, tipo: str, data: dict):
        with self._lock:
            self.pasos.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "tipo": tipo,
                **data,
            })

    def guardar(self):
        try:
            TRACE_DIR.mkdir(parents=True, exist_ok=True)
            ruta = TRACE_DIR / f"{self.sesion_id}.json"
            ruta.write_text(
                json.dumps(self.pasos, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[TRACE] Error guardando: {e}")

    def resumen(self) -> str:
        lineas = [f"Trace {self.sesion_id} - {len(self.pasos)} pasos"]
        for p in self.pasos:
            if "agente" in p:
                lineas.append(
                    f"  [{p['agente']}] {p['tiempo']}s "
                    f"{'OK' if p['exito'] else 'FAIL'} - {p['tarea'][:60]}"
                )
            else:
                lineas.append(f"  [{p.get('tipo', '?')}] {str(p)[:120]}")
        return "\n".join(lineas)
