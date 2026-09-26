"""Memoria compartida entre agentes."""
from typing import List, Dict


class SharedMemory:
    def __init__(self, max_msgs: int = 12):
        self.max_msgs = max_msgs
        self.history: List[Dict] = []
        self.facts: List[str] = []
        self.handoffs: List[Dict] = []

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_msgs:
            self.history = self.history[-self.max_msgs:]

    def add_fact(self, fact: str):
        if fact and fact not in self.facts:
            self.facts.append(fact)

    def add_handoff(self, de: str, a: str, motivo: str):
        self.handoffs.append({"de": de, "a": a, "motivo": motivo})

    def get_conversation_context(self) -> str:
        if not self.history:
            return ""
        lineas = []
        for msg in self.history[-6:]:
            rol = "Usuario" if msg["role"] == "user" else "Asistente"
            lineas.append(f"{rol}: {msg['content'][:200]}")
        return "\n".join(lineas)

    def get_facts_context(self) -> str:
        if not self.facts:
            return ""
        return "Datos aprendidos:\n" + "\n".join(f"- {f}" for f in self.facts)

    def clear(self):
        self.history.clear()
        self.facts.clear()
        self.handoffs.clear()
