from core.agent import Agent
from skills.files import FilesSkill

agent = Agent()
skills = {"files": FilesSkill()}

tests = [
    "abre el ultimo archivo de descargas",
    "cual es el archivo mas grande en documentos",
    "cuantos archivos pdf hay en descargas",
    "hay algun archivo mp4 en descargas",
]

for t in tests:
    print(f"\n{'='*60}")
    print(f"TAREA: {t}")
    print(f"{'='*60}")
    r = agent.run(t, skills)
    print(f"RESPUESTA: {r['display']}")
    print(f"PENSAMIENTO: {r['thought']}")
    print(f"PASOS: {len(r.get('steps', []))}")
    for step in r.get("steps", []):
        if step.get("type") == "action":
            print(f"  [{step['step']}] {step.get('action')} → {step.get('result', '')[:80]}")