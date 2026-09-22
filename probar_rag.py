from core.rag import RAG

r = RAG()

print("=== INDEXANDO ===")
print(r.index_file(r"C:\Users\alein\Downloads\Cv_AlessandroCortijo (3).pdf"))

print("\n=== DOCUMENTOS INDEXADOS ===")
print(r.list_documents())

print("\n=== PREGUNTA 1: de que trata ===")
result = r.ask("de que trata este documento")
print(result["answer"])
print("Fuentes:", result["sources"])

print("\n=== PREGUNTA 2: datos especificos ===")
result = r.ask("cuales son las habilidades tecnicas o experiencia mencionadas")
print(result["answer"])
print("Fuentes:", result["sources"])