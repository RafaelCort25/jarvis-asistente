import json
import time
from datetime import datetime
from pathlib import Path
import streamlit as st

# ─── CONFIGURACION ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Jarvis",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.brain import Brain
from core.config_loader import CONFIG
from core.router import Router

HISTORY_FILE = Path("memory/gui_history.json")
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


# ─── CSS MODERN ──────────────────────────────────────────────────────────────

MODERN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ═══════════════════════════════════════════════════════════════
   PALETA Y VARIABLES
   ═══════════════════════════════════════════════════════════════ */
:root {
    /* Fondos con jerarquía */
    --bg-primary: #0f1117;        /* Fondo principal */
    --bg-secondary: #16181f;      /* Sidebar y paneles */
    --bg-tertiary: #1e2029;       /* Elementos elevados */
    --bg-hover: #252833;          /* Hover */
    
    /* Texto */
    --text-primary: #ececf1;      /* Texto principal */
    --text-secondary: #9ca3af;    /* Texto secundario */
    --text-tertiary: #6b7280;     /* Texto muted */
    
    /* Acentos */
    --accent-primary: #8b5cf6;    /* Violeta elegante */
    --accent-secondary: #6366f1;  /* Indigo */
    --accent-glow: rgba(139, 92, 246, 0.15);
    
    /* Bordes */
    --border-subtle: rgba(255, 255, 255, 0.06);
    --border-medium: rgba(255, 255, 255, 0.1);
    
    /* Radios */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-xl: 24px;
}

/* ═══════════════════════════════════════════════════════════════
   BASE
   ═══════════════════════════════════════════════════════════════ */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, sans-serif !important;
}

.stApp {
    background: var(--bg-primary) !important;
    background-image: 
        radial-gradient(circle at 15% 0%, rgba(139, 92, 246, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 85% 100%, rgba(99, 102, 241, 0.06) 0%, transparent 40%) !important;
    background-attachment: fixed !important;
    color: var(--text-primary) !important;
}

/* Ocultar header de Streamlit */
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 0 !important;
}

#MainMenu, footer, .stDeployButton {
    display: none !important;
}

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR — Estilo Claude
   ═══════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border-subtle) !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 2rem !important;
}

[data-testid="stSidebar"] h1 {
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
    color: var(--text-primary) !important;
    background: none !important;
    -webkit-text-fill-color: var(--text-primary) !important;
    animation: none !important;
    border: none !important;
    padding: 0 !important;
}

[data-testid="stSidebar"] h3 {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: var(--text-tertiary) !important;
    margin-top: 1.5rem !important;
    margin-bottom: 0.75rem !important;
}

[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] small {
    color: var(--text-tertiary) !important;
    font-size: 0.8rem !important;
}

/* ═══════════════════════════════════════════════════════════════
   TÍTULOS PRINCIPALES
   ═══════════════════════════════════════════════════════════════ */
h1 {
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    font-size: 2.25rem !important;
    letter-spacing: -0.03em !important;
    color: var(--text-primary) !important;
    background: linear-gradient(135deg, #ffffff 0%, #c4b5fd 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    animation: none !important;
    border: none !important;
    padding: 0 !important;
    margin-bottom: 0.5rem !important;
}

h2, h3 {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

/* ═══════════════════════════════════════════════════════════════
   CHAT MESSAGES — Estilo ChatGPT/Claude
   ═══════════════════════════════════════════════════════════════ */
.stChatMessage {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 1.5rem 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
    border-bottom: 1px solid var(--border-subtle) !important;
}

/* Mensaje del usuario — fondo sutil */
.stChatMessage[data-testid*="user"] {
    background: var(--bg-secondary) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1.25rem 1.5rem !important;
    margin: 0.5rem 0 !important;
    border: 1px solid var(--border-subtle) !important;
}

/* Mensaje del asistente — sin fondo, como Claude */
.stChatMessage[data-testid*="assistant"] {
    background: transparent !important;
    padding: 1.5rem 0.5rem !important;
    border-bottom: 1px solid var(--border-subtle) !important;
    border-radius: 0 !important;
}

/* Contenido de los mensajes */
.stChatMessage p,
.stChatMessage li,
.stChatMessage span {
    color: var(--text-primary) !important;
    font-size: 0.95rem !important;
    line-height: 1.7 !important;
}

/* Avatar del chat */
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"] {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-medium) !important;
}

/* ═══════════════════════════════════════════════════════════════
   INPUT DEL CHAT — Estilo moderno
   ═══════════════════════════════════════════════════════════════ */
[data-testid="stChatInput"] {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-medium) !important;
    border-radius: var(--radius-xl) !important;
    padding: 0.5rem 1rem !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
    transition: all 0.2s ease !important;
}

[data-testid="stChatInput"]:focus-within {
    border-color: var(--accent-primary) !important;
    box-shadow: 0 4px 30px var(--accent-glow) !important;
}

[data-testid="stChatInput"] textarea {
    color: var(--text-primary) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.95rem !important;
    background: transparent !important;
}

[data-testid="stChatInput"] textarea::placeholder {
    color: var(--text-tertiary) !important;
}

/* Botón de enviar */
[data-testid="stChatInput"] button {
    background: var(--accent-primary) !important;
    border-radius: 50% !important;
    transition: all 0.2s ease !important;
}

[data-testid="stChatInput"] button:hover {
    background: var(--accent-secondary) !important;
    transform: scale(1.05) !important;
}

/* ═══════════════════════════════════════════════════════════════
   BOTONES
   ═══════════════════════════════════════════════════════════════ */
.stButton > button {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--text-primary) !important;
    border-radius: var(--radius-md) !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.15s ease !important;
    box-shadow: none !important;
}

.stButton > button:hover {
    background: var(--bg-hover) !important;
    border-color: var(--border-medium) !important;
    transform: translateY(-1px) !important;
}

.stButton > button:active {
    transform: translateY(0) !important;
}

/* ═══════════════════════════════════════════════════════════════
   TOGGLES
   ═══════════════════════════════════════════════════════════════ */
[data-testid="stToggle"] label span {
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
}

/* ═══════════════════════════════════════════════════════════════
   DIVIDERS Y EXPANDERS
   ═══════════════════════════════════════════════════════════════ */
hr {
    border: none !important;
    border-top: 1px solid var(--border-subtle) !important;
    margin: 1.5rem 0 !important;
}

[data-testid="stExpander"] {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
}

/* ═══════════════════════════════════════════════════════════════
   SPINNER
   ═══════════════════════════════════════════════════════════════ */
.stSpinner > div {
    border-top-color: var(--accent-primary) !important;
}

/* ═══════════════════════════════════════════════════════════════
   TEXTO SECUNDARIO (pensamientos, detalles)
   ═══════════════════════════════════════════════════════════════ */
.stMarkdown small,
.stMarkdown code {
    color: var(--text-tertiary) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    background: var(--bg-secondary) !important;
    padding: 0.15rem 0.4rem !important;
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border-subtle) !important;
}

/* ═══════════════════════════════════════════════════════════════
   CAPTIONS Y TEXTO PEQUEÑO
   ═══════════════════════════════════════════════════════════════ */
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--text-tertiary) !important;
    font-size: 0.8rem !important;
}

/* ═══════════════════════════════════════════════════════════════
   SCROLLBAR
   ═══════════════════════════════════════════════════════════════ */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: var(--bg-hover);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--border-medium);
}

/* ═══════════════════════════════════════════════════════════════
   BOTONES DE ACCIONES RÁPIDAS
   ═══════════════════════════════════════════════════════════════ */
.stButton > button[kind="secondary"] {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-subtle) !important;
    font-size: 0.8rem !important;
    padding: 0.6rem 0.5rem !important;
    min-height: 44px !important;
}

.stButton > button[kind="secondary"]:hover {
    background: var(--bg-tertiary) !important;
    border-color: var(--accent-primary) !important;
    box-shadow: 0 0 0 3px var(--accent-glow) !important;
}

/* ═══════════════════════════════════════════════════════════════
   RESPONSIVE
   ═══════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
    h1 { font-size: 1.75rem !important; }
    .stChatMessage { padding: 1rem 0 !important; }
}
</style>
"""

st.markdown(MODERN_CSS, unsafe_allow_html=True)


# ─── INICIALIZACION ─────────────────────────────────────────────────────────


@st.cache_resource
def init_jarvis():
    brain = Brain()
    router = Router()
    return brain, router


def init_session_state():
    if "messages" not in st.session_state:
        # Cargar historial persistente si existe
        if HISTORY_FILE.exists():
            try:
                st.session_state.messages = json.loads(
                    HISTORY_FILE.read_text(encoding="utf-8")
                )
            except Exception:
                st.session_state.messages = []
        else:
            st.session_state.messages = []


def save_history():
    try:
        # Guardar solo los ultimos 100
        hist = st.session_state.messages[-100:]
        HISTORY_FILE.write_text(
            json.dumps(hist, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[GUI HISTORY ERROR] {e}")


@st.cache_resource
def get_tts():
    """Cachea el TTS entre reruns de Streamlit."""
    try:
        from voice.tts import TTS
        return TTS()
    except Exception as e:
        print(f"[TTS ERROR] {e}")
        return None


def lazy_init_voice():
    tts = get_tts()
    st.session_state.tts = tts


def transcribe_audio(audio_bytes):
    """Transcribe audio del navegador usando faster-whisper directamente."""
    if not audio_bytes:
        return ""
    if "stt" not in st.session_state:
        with st.spinner("Cargando STT... (solo la primera vez)"):
            try:
                from voice.stt import STT

                st.session_state.stt = STT()
            except Exception as e:
                st.error(f"Error STT: {e}")
                return ""
    try:
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_bytes)
            audio_path = f.name

        try:
            segments, _ = st.session_state.stt.model.transcribe(
                audio_path,
                language=st.session_state.stt.language,
                initial_prompt=st.session_state.stt.initial_prompt,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=200),
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text for seg in segments).strip()
            cleaned = st.session_state.stt.clean(text)
            print(f"[GUI STT] raw={text!r} limpio={cleaned!r}")
            return cleaned
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
    except Exception as e:
        st.error(f"Error transcribiendo: {e}")
        return ""


# ─── INTERFAZ ───────────────────────────────────────────────────────────────

init_session_state()
brain, router = init_jarvis()


# SIDEBAR
with st.sidebar:
    st.title("🤖 Jarvis")
    st.caption(f"Modo: {CONFIG['jarvis']['name']}")

    st.divider()

    st.subheader("⚙️ Opciones")
    voice_on = st.toggle("🔊 Hablar respuestas", value=False)
    if voice_on:
        lazy_init_voice()

    if st.button("🗑️ Limpiar chat", use_container_width=True):
        st.session_state.messages = []
        brain.reset()
        save_history()
        st.rerun()

    if st.button("🔄 Reset memoria", use_container_width=True):
        brain.reset()
        st.success("Memoria reiniciada.")

    # ─── SEGURIDAD ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("🛡️ Seguridad")
    
    alert_dir = Path("security/alerts")
    alert_count = len(list(alert_dir.glob("*.jpg"))) if alert_dir.exists() else 0

    if "surveillance" not in st.session_state:
        st.session_state.surveillance = None

    surveillance_active = (
        st.session_state.surveillance is not None and st.session_state.surveillance.running
    )
    if st.toggle("👁️ Vigilancia activa", value=surveillance_active, key="surv_toggle"):
        if not surveillance_active:
            try:
                from security.surveillance import Surveillance
                from integrations.notifier import send

                def alert_callback(photo_path, confidence):
                    try:
                        send(
                            f"🚨 *ALERTA* — Desconocido detectado\nConfianza: {int(confidence)}",
                            image_path=photo_path,
                        )
                    except Exception as e:
                        print(f"[GUI ALERT ERROR] {e}")

                surv = Surveillance(on_unknown=alert_callback)
                surv.start()
                st.session_state.surveillance = surv
                try:
                    send("🛡️ Vigilancia iniciada (desde GUI).")
                except Exception:
                    pass
                st.success("Vigilancia iniciada.")
                st.rerun()
            except Exception as e:
                st.error(f"Error iniciando: {e}")
    else:
        if surveillance_active:
            st.session_state.surveillance.stop()
            st.session_state.surveillance = None
            try:
                from integrations.notifier import send

                send("🛡️ Vigilancia detenida (desde GUI).")
            except Exception:
                pass
            st.info("Vigilancia detenida.")

    st.caption(f"📸 {alert_count} alertas guardadas")
    if alert_count > 0:
        latest = sorted(alert_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)[0]
        if st.button("🖼️ Ver última alerta", use_container_width=True):
            st.session_state.show_last_alert = True

    if st.session_state.get("show_last_alert") and alert_count > 0:
        st.image(str(latest), caption=latest.name)
        if st.button("✖️ Cerrar imagen"):
            st.session_state.show_last_alert = False
            st.rerun()

    st.divider()
    st.caption(f"💬 {len(st.session_state.messages)} mensajes en el chat")
    st.caption(f"🧠 {len(brain.memory.get_preferences())} preferencias guardadas")

    st.divider()
    st.caption("**Skills activas**")
    for skill, enabled in CONFIG["skills"].items():
        icon = "✅" if enabled else "❌"
        st.caption(f"{icon} {skill}")

    st.divider()
    st.caption("**Comandos de ejemplo**")
    st.caption("• Abre notepad")
    st.caption("• Pon bad bunny")
    st.caption("• Sube el volumen")
    st.caption("• Guarda nota comprar pan")
    st.caption("• Busca en google el clima")


# TITULO
st.title("💬 Habla con Jarvis")
st.caption("Escribe o habla. Jarvis te responde y ejecuta comandos.")


# HISTORIAL
for msg in st.session_state.messages:
    avatar = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg.get("meta"):
            st.markdown(
                f"<small>{msg['meta']}</small>",
                unsafe_allow_html=True,
            )


# ─── INPUT DE VOZ ───────────────────────────────────────────────────────────

st.divider()
col_mic1, col_mic2, col_mic3 = st.columns([1, 1, 2])

with col_mic1:
    try:
        from streamlit_mic_recorder import mic_recorder

        audio = mic_recorder(
            start_prompt="🎤 Grabar",
            stop_prompt="⏹️ Parar",
            just_once=True,
            use_container_width=True,
            key="mic",
        )
        if audio and audio.get("bytes"):
            current_id = audio.get("id", "unknown")
            if st.session_state.get("last_mic_id") != current_id:
                st.session_state.last_mic_id = current_id
                with st.spinner("Transcribiendo..."):
                    text = transcribe_audio(audio["bytes"])
                if text:
                    st.session_state.pending_input = text
                    st.rerun()
    except ImportError:
        st.caption("Instala streamlit-mic-recorder")


# ─── INPUT DE TEXTO ─────────────────────────────────────────────────────────

user_input = st.chat_input("Escribe un comando...")

if "pending_input" in st.session_state and st.session_state.pending_input:
    user_input = st.session_state.pending_input
    st.session_state.pending_input = ""


# ─── PROCESAR INPUT ─────────────────────────────────────────────────────────

if user_input:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})
    save_history()

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Pensando..."):
            result, is_chat = router.route(user_input)

            if result:
                thought = result.get("thought", "")
                display = result.get("display", "")
                voice = result.get("voice", "")

                response_text = display or voice or "Listo."

                meta_parts = []
                if thought:
                    meta_parts.append(f"🤔 {thought}")
                if voice and voice != display:
                    meta_parts.append(f"🔊 {voice}")
                meta = " | ".join(meta_parts) if meta_parts else ""

                st.markdown(response_text)
                if meta:
                    st.markdown(
                        f"<small>{meta}</small>",
                        unsafe_allow_html=True,
                    )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response_text,
                        "meta": meta,
                    }
                )
                save_history()

                if voice_on and st.session_state.get("tts") and voice:
                    st.session_state.tts.speak(voice)

            elif is_chat:
                reply = brain.chat(user_input)
                st.markdown(reply)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": reply,
                    }
                )
                save_history()

                if voice_on and st.session_state.get("tts"):
                    st.session_state.tts.speak(reply[:600])

            else:
                msg = "No entendí el comando."
                st.markdown(msg)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": msg,
                    }
                )
                save_history()


# ─── BOTONES RAPIDOS ────────────────────────────────────────────────────────

st.divider()
st.caption("⚡ Acciones rápidas")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.button("🔊 Vol +", use_container_width=True):
        result, _ = router.route("sube el volumen")
        if result:
            st.success(result.get("display", "Listo."))

with col2:
    if st.button("🔉 Vol -", use_container_width=True):
        result, _ = router.route("baja el volumen")
        if result:
            st.success(result.get("display", "Listo."))

with col3:
    if st.button("⏯️ Play/Pausa", use_container_width=True):
        result, _ = router.route("pausa la musica")
        if result:
            st.success(result.get("display", "Listo."))

with col4:
    if st.button("📸 Captura", use_container_width=True):
        result, _ = router.route("toma una captura")
        if result:
            st.success(result.get("display", "Listo."))

with col5:
    if st.button("📝 Notas", use_container_width=True):
        result, _ = router.route("lee mis notas")
        if result:
            st.info(result.get("display", "Sin notas."))

col6, col7, col8, col9, col10 = st.columns(5)

with col6:
    if st.button("⏭️ Siguiente", use_container_width=True):
        result, _ = router.route("siguiente cancion")
        if result:
            st.success(result.get("display", "Listo."))

with col7:
    if st.button("🔒 Bloquear", use_container_width=True):
        result, _ = router.route("bloquea la pc")
        if result:
            st.success(result.get("display", "Listo."))

with col8:
    if st.button("🌐 Google", use_container_width=True):
        st.session_state.pending_input = "abre google"
        st.rerun()

with col9:
    if st.button("▶️ YouTube", use_container_width=True):
        st.session_state.pending_input = "abre youtube"
        st.rerun()

with col10:
    if st.button("🎵 Spotify", use_container_width=True):
        result, _ = router.route("abre spotify")
        if result:
            st.success(result.get("display", "Listo."))