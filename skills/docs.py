from skills.base import Skill
from core.rag import RAG


class DocsSkill(Skill):
    name = "docs"
    description = "Indexa y consulta documentos (PDF, TXT, MD, DOCX)"

    def __init__(self):
        self.rag = RAG()

    def run(self, action, params):
        if action == "index_file":
            return self.rag.index_file(params.get("path", ""))
        if action == "index_folder":
            return self.rag.index_folder(params.get("path", ""))
        if action == "ask":
            result = self.rag.ask(params.get("query", ""))
            answer = result["answer"]
            sources = result["sources"]
            if sources:
                return f"{answer}\n\nFuentes: {', '.join(sources)}"
            return answer
        if action == "list":
            return self.rag.list_documents()
        if action == "delete":
            return self.rag.delete_document(params.get("name", ""))
        return f"Accion desconocida en docs: {action}"