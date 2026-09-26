# Politica de Privacidad - Senna

**Ultima actualizacion:** Septiembre 2026

## Resumen

**Senna es 100% local.** No recolectamos, transmitimos ni almacenamos
ningun dato personal en servidores externos.

## Que datos maneja Senna

### En tu computadora (nunca salen de ahi)

- Conversaciones (guardadas en memory/conversations/*.json)
- Preferencias del usuario (guardadas en memory/*.json)
- Archivos generados (en sandbox/)
- Historial de trazas (en memory/traces/*.json)
- Logs de ejecucion (en logs/)

**Puedes borrar cualquier archivo en cualquier momento.**

### Hacia servicios externos (solo si tu los configuras)

Senna solo se conecta a servicios externos si TU pegas tus
credenciales en el panel Integraciones:

| Servicio | Que se envia | Cuando |
|----------|--------------|--------|
| Ollama | Texto de tus prompts | Cada mensaje (local, sin internet) |
| Telegram | Mensajes y archivos que tu envies | Solo cuando lo pidas |
| Gmail | Correos que tu envies/leas | Solo cuando lo pidas |
| Canva | Disenos que tu generes | Solo cuando lo pidas |
| n8n | Workflows que tu crees | Solo cuando lo pidas |

**Nunca enviamos tus datos a ningun servidor nuestro.**

### Como se guardan las credenciales

- Formato: .env.*.tmp (texto plano)
- Ubicacion: C:\JARVIS\.env.*.tmp (solo en tu PC)
- **Recomendacion:** no compartas estos archivos

## Menores de edad

Senna no esta disenado para ninos. No recolectamos datos de menores.

## Cambios

Podemos actualizar esta politica. Los cambios se publicaran en el
repositorio.

## Contacto

Si tienes dudas sobre privacidad, abre un issue en el repositorio.
