import sys
from rich.console import Console
from core.brain import Brain
from core.router import Router
from core.config_loader import CONFIG

console = Console()


def init_voice():
    from voice.tts import TTS
    from voice.stt import STT
    from voice.wake_word import WakeWord
    tts = TTS()
    stt = STT()
    ww = WakeWord(threshold=0.25, device=1)
    return tts, stt, ww


def _make_voice_confirmation(tts, stt):
    """Devuelve un handler que pregunta por voz y espera si/no."""
    import time as _time

    def handler(skill, action, summary, level, timeout=30):
        prefix = "Atencion. " if level == "high" else ""
        tts.speak(f"{prefix}{summary}")
        _time.sleep(0.4)

        attempts = 0
        start = _time.time()

        while attempts < 3 and (_time.time() - start) < timeout:
            tts.speak("Confirmas?")
            text = stt.listen()
            attempts += 1

            if not text:
                continue

            t = text.lower().strip()
            if any(w in t for w in ["si", "confirmo", "dale", "hazlo", "adelante", "vale", "ok"]):
                tts.speak("Confirmado.")
                return True
            if any(w in t for w in ["no", "cancela", "cancelar", "espera", "para", "stop"]):
                tts.speak("Cancelado.")
                return False

        tts.speak("Cancelado por falta de respuesta.")
        return False

    return handler


def _make_text_confirmation():
    """Fallback para modo texto: pide confirmacion por consola."""
    def handler(skill, action, summary, level, timeout=30):
        print(f"\n[CONFIRMACION {level.upper()}] {summary}")
        try:
            resp = input("Confirmas? (s/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return resp in ("s", "si", "y", "yes")
    return handler


def _speak_with_barge_in(tts, stt, text, brain, router):
    """Reproduce texto mientras escucha posible interrupcion."""
    wav_path = tts.speak_async(text)
    if not wav_path:
        return True
    try:
        interrupt_text = stt.listen_with_interrupt(tts, max_duration=8)
        if interrupt_text and interrupt_text.strip() and len(interrupt_text.strip()) > 2:
            console.print(f"[green]Interrumpiste:[/] {interrupt_text}")
            return process(interrupt_text, brain, router, tts, stt)
    finally:
        tts.cleanup(wav_path)
    return True


def process(user, brain, router, tts=None, stt=None):
    if not user or not user.strip():
        return True
    t = user.lower().strip()
    if any(w in t for w in ["salir", "exit", "quit", "apagate", "adios", "chau", "hasta luego"]):
        return False
    if t == "reset":
        brain.reset()
        console.print("[dim]Memoria reiniciada.[/]")
        return True

    result, is_chat = router.route(user)

    if result:
        if result.get("thought") and CONFIG["jarvis"].get("debug"):
            console.print(f"[dim]🤔 {result['thought']}[/]")

        if result.get("display"):
            console.print(f"[bold magenta]{CONFIG['jarvis']['name']}:[/] {result['display']}\n")

        if tts and result.get("voice"):
            if stt:
                return _speak_with_barge_in(tts, stt, result["voice"], brain, router)
            else:
                tts.speak(result["voice"])
        return True

    if not is_chat:
        return True

    console.print("[dim]Pensando...[/]")
    reply = brain.chat(user)
    console.print(f"[bold magenta]{CONFIG['jarvis']['name']}:[/] {reply}\n")
    if tts:
        if stt:
            return _speak_with_barge_in(tts, stt, reply[:600], brain, router)
        else:
            tts.speak(reply[:600])
    return True


def main():
    mode = "handsfree"
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--text", "-t"):
            mode = "text"
        elif sys.argv[1] in ("--voice", "-v"):
            mode = "voice"

    console.print(f"[bold cyan]{CONFIG['jarvis']['name']}[/] iniciando modo [yellow]{mode}[/].\n")
    console.print("[dim]Memoria activa. Di 'recuerda que...' para guardar algo.[/]\n")

    # 1. Nucleo
    brain = Brain()
    router = Router()

    # 2. Voz (tts, stt, ww)
    tts = stt = ww = None
    if mode in ("voice", "handsfree"):
        try:
            tts, stt, ww = init_voice()
        except Exception as e:
            console.print(f"[red]Error iniciando voz: {e}[/]")
            console.print("[yellow]Cambiando a modo texto.[/]")
            mode = "text"

    # 3. Capa de confirmacion (ya con tts/stt listos)
    from core import confirmation
    if tts and stt:
        confirmation.set_handler(_make_voice_confirmation(tts, stt))
    else:
        confirmation.set_handler(_make_text_confirmation())

    # 4. Scheduler
    from scheduler.scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.set_router(router)
    scheduler.start()

    # 5. Vigilante proactivo
    from core.watcher import get_watcher
    watcher = get_watcher()
    watcher.start()

    # 6. Loop principal
    if mode == "handsfree":
        console.print("[green]Modo manos libres. Di 'Hey Yarvis' para activarme.[/]\n")
        tts.speak(f"{CONFIG['jarvis']['name']} listo. Di hey yarvis para activarme.")

        MAX_CONSECUTIVE = 3
        while True:
            try:
                ww.wait_for_wake()
                console.print("[cyan]>> Wake word detectada[/]")
                tts.speak("Te escucho.")

                for turno in range(MAX_CONSECUTIVE):
                    text = stt.listen()
                    if not text or len(text.strip()) < 3:
                        console.print("[dim]No detecte nada.[/]")
                        break
                    console.print(f"[green]Dijiste:[/] {text}")

                    t = text.lower().strip()
                    if any(w in t for w in ["basta", "callate", "silencio", "gracias"]):
                        tts.speak("Ok.")
                        break
                    if not process(text, brain, router, tts, stt):
                        console.print("[yellow]Hasta luego.[/]")
                        if tts:
                            tts.speak("Hasta luego.")
                        return
                    if turno == MAX_CONSECUTIVE - 1:
                        tts.speak("Di hey yarvis si necesitas algo mas.")
            except KeyboardInterrupt:
                break

    elif mode == "voice":
        from rich.prompt import Prompt
        console.print("[green]Modo voz. Enter para hablar, texto para escribir.[/]\n")
        while True:
            try:
                user = Prompt.ask("[bold green]Tu[/]").strip()
                if not user:
                    text = stt.listen()
                    if not text:
                        console.print("[dim]No detecte voz.[/]")
                        continue
                    console.print(f"[green]Dijiste:[/] {text}")
                    user = text
                if not process(user, brain, router, tts, stt):
                    break
            except (KeyboardInterrupt, EOFError):
                break

    else:
        from rich.prompt import Prompt
        while True:
            try:
                user = Prompt.ask("[bold green]Tu[/]").strip()
                if not process(user, brain, router, tts, stt):
                    break
            except (KeyboardInterrupt, EOFError):
                break

    console.print("[yellow]Hasta luego.[/]")
    if tts:
        tts.speak("Hasta luego.")


if __name__ == "__main__":
    main()