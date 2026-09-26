"""Registry de skills permitidas por agente."""
from typing import List, Dict

SKILLS_POR_AGENTE: Dict[str, List[str]] = {
    "dev": [
        "dev", "terminal", "git", "files", "edit", "clipboard",
        "docs", "pdf", "office", "image", "education",
    ],
    "research": [
        "browser", "docs", "weather", "translate", "gmail",
        "clipboard", "system", "files",
    ],
    "execute": [
        "terminal", "system", "desktop", "browser", "clipboard",
        "files", "scheduler", "macro", "git",
    ],
    "chat": [],
}


def skills_for(agente: str) -> List[str]:
    return SKILLS_POR_AGENTE.get(agente, [])


def puede_usar(agente: str, skill: str) -> bool:
    permitidas = SKILLS_POR_AGENTE.get(agente, [])
    return not permitidas or skill in permitidas
