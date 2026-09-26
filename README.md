# Senna - Asistente Personal

Asistente de escritorio con IA local que controla tu PC, automatiza
tareas y se integra con servicios externos.

## Caracteristicas

- **31 skills** operativas (sistema, archivos, dev, Gmail, Canva, n8n, CAD, etc.)
- **Multiagente profesional** - Supervisor + DEV / RESEARCH / EXECUTE / CHAT
- **RAG local** - Indexa tus documentos y pregunta sobre ellos
- **Pipeline CAD/BIM** - DWG -> analisis -> muros 3D -> IFC (Revit/ArchiCAD)
- **Voz + Wake word** - "Oye Senna" (proximamente)
- **GUI moderna** - Panel de sistema, credenciales, historial y modelos
- **100% local** - Ollama + ChromaDB, sin enviar datos a la nube

## Requisitos

- **Windows 10/11** (64 bits)
- **Ollama** con modelos descargados:
  - llama3.2:3b (rapido, chat)
  - qwen2.5-coder:7b (codigo)
  - llava-phi3:latest (vision)
- **RAM:** 8 GB minimo, 16 GB recomendado
- **GPU:** opcional pero muy recomendado (RTX 3060+)

## Instalacion

### Opcion A: Instalador

Descarga SennaSetup.exe y ejecutalo.

### Opcion B: Manual (dev)

    git clone https://github.com/RafaelCort25/jarvis-asistente.git C:/JARVIS
    cd C:/JARVIS
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m uvicorn api_server:app --port 8000

## Uso

1. Arranca Ollama: ollama serve
2. Arranca Senna: & "C:/jarvis-electron/dist/Jarvis.exe"
3. Escribe o habla. Ejemplos:
   - "Que hora es?"
   - "Hazme un script que sume dos numeros"
   - "Toma una captura"
   - "Que es la fotosintesis?"
   - "Cuadro de superficies del plano X.dxf"

## Configuracion

### Modelos por agente

Abre Sistema -> Agentes Multiagente y elige el modelo de cada uno.

### Integraciones

Abre Sistema -> Configurar integraciones y pega tus API keys
(Gmail, Canva, n8n, Telegram, Maps).

## Estructura

    C:/JARVIS/
    |- core/              # Router, agente, brain, multiagente
    |- skills/            # 31 skills
    |- integrations/      # Telegram bot, etc.
    |- config/            # settings.yaml, models.json, agents.json
    |- memory/            # Conversaciones, preferencias, trazas
    |- sandbox/           # Archivos generados
    |- api_server.py      # Servidor FastAPI
    |- jarvis-orb.html    # GUI
    |- requirements.txt

## Problemas comunes

### "Ollama no responde"
Abre una terminal y ejecuta ollama serve. Debe quedar corriendo.

### "Failed to connect"
Verifica que el puerto 8000 este libre: netstat -ano | Select-String ":8000".

### "Modelo no instalado"
Descarga el modelo: ollama pull llama3.2:3b.

## Licencia

Propietario - Todos los derechos reservados. Ver LICENSE.txt.

## Disclaimer

Senna puede ejecutar acciones destructivas. Lee DISCLAIMER.md
antes de usarlo.

## Documentacion

- SKILLS.md - Catalogo completo de skills
- TERMS.md - Terminos de uso
- PRIVACY.md - Politica de privacidad
- DISCLAIMER.md - Descargo de responsabilidad
