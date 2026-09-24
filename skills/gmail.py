"""Skill de Gmail: leer, buscar y enviar correos via IMAP/SMTP."""
import email
import imaplib
import re
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from pathlib import Path

from skills.base import Skill
from core import confirmation

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.gmail.tmp"
TIMEOUT = 20


def _load_env():
    """Carga GMAIL_USER y GMAIL_APP_PASSWORD del archivo .env.gmail.tmp."""
    if not ENV_FILE.exists():
        return None, None
    user = None
    password = None
    try:
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("GMAIL_USER="):
                user = line.split("=", 1)[1].strip()
            elif line.startswith("GMAIL_APP_PASSWORD="):
                password = line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"[GMAIL] Error leyendo env: {e}")
        return None, None
    return user, password


def _decode_header_value(raw):
    """Decodifica cabeceras MIME (acentos, caracteres raros)."""
    if not raw:
        return ""
    try:
        parts = decode_header(raw)
        out = []
        for content, charset in parts:
            if isinstance(content, bytes):
                out.append(content.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(content)
        return " ".join(out)
    except Exception:
        return str(raw)


def _get_body(msg):
    """Extrae el cuerpo de texto plano del mensaje."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    continue
        return "(sin cuerpo de texto)"
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )
    except Exception:
        return "(no se pudo leer el cuerpo)"


class GmailSkill(Skill):
    name = "gmail"
    description = "Lee, busca y envia correos de Gmail"

    def run(self, action, params):
        if action == "list_recent":
            return self._list_recent(int(params.get("n", 5) or 5))
        if action == "read":
            return self._read(params.get("uid", ""))
        if action == "search":
            return self._search(params.get("query", ""))
        if action == "send":
            return self._send(
                params.get("to", ""),
                params.get("subject", ""),
                params.get("body", ""),
            )
        if action == "count_unread":
            return self._count_unread()
        return f"Accion desconocida en gmail: {action}"

    # ─── HELPERS ────────────────────────────────────────────────────

    def _connect_imap(self):
        user, password = _load_env()
        if not user or not password:
            return None, None, "No hay configuracion de Gmail (.env.gmail.tmp)."
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=TIMEOUT)
            mail.login(user, password)
            return mail, user, None
        except imaplib.IMAP4.error as e:
            return None, None, f"Error autenticando en Gmail: {e}"
        except Exception as e:
            return None, None, f"Error conectando a Gmail: {e}"

    # ─── ACCIONES ───────────────────────────────────────────────────

    def _list_recent(self, n=5):
        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar a Gmail."}

        try:
            mail.select("INBOX")
            status, data = mail.search(None, "UNSEEN")
            if status != "OK":
                return {"thought": "", "display": "No pude buscar correos.", "voice": "Error buscando."}

            uids = data[0].split()
            if not uids:
                mail.logout()
                return {
                    "thought": "",
                    "display": "No tienes correos sin leer.",
                    "voice": "No tienes correos sin leer.",
                }

            ultimos = uids[-n:][::-1]
            lineas = [f"Correos sin leer ({len(uids)} en total, mostrando {len(ultimos)}):"]
            for i, uid in enumerate(ultimos, 1):
                status, msg_data = mail.fetch(uid, "(RFC822.HEADER)")
                if status != "OK":
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                remitente = _decode_header_value(msg.get("From", ""))
                asunto = _decode_header_value(msg.get("Subject", ""))
                fecha = msg.get("Date", "")
                lineas.append(f"  {i}. De: {remitente}")
                lineas.append(f"     Asunto: {asunto}")
                lineas.append(f"     Fecha: {fecha[:25]}")
                lineas.append(f"     UID: {uid.decode()}")

            mail.logout()
            return {
                "thought": f"{len(uids)} correos sin leer",
                "display": "\n".join(lineas),
                "voice": f"Tienes {len(uids)} correos sin leer.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error leyendo correos."}

    def _read(self, uid):
        if not uid:
            return {"thought": "", "display": "Falta el UID del correo.", "voice": "Falta el UID."}

        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}

        try:
            mail.select("INBOX")
            status, msg_data = mail.fetch(str(uid).encode(), "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                mail.logout()
                return {"thought": "", "display": f"No encontre el correo {uid}.", "voice": "No lo encontre."}

            msg = email.message_from_bytes(msg_data[0][1])
            remitente = _decode_header_value(msg.get("From", ""))
            asunto = _decode_header_value(msg.get("Subject", ""))
            fecha = msg.get("Date", "")
            cuerpo = _get_body(msg)

            # Limitar a 1500 chars para no saturar
            if len(cuerpo) > 1500:
                cuerpo = cuerpo[:1500] + "... (truncado)"

            display = (
                f"De: {remitente}\n"
                f"Asunto: {asunto}\n"
                f"Fecha: {fecha}\n"
                f"---\n{cuerpo}"
            )
            mail.logout()
            return {
                "thought": f"Correo de {remitente}",
                "display": display,
                "voice": f"Correo de {remitente}: {asunto}",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error leyendo el correo."}

    def _search(self, query):
        query = (query or "").strip()
        if not query:
            return {"thought": "", "display": "Dime que buscar.", "voice": "Dime que buscar."}

        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}

        try:
            mail.select("INBOX")
            # Buscar en asunto o remitente
            status, data = mail.search(None, f'OR SUBJECT "{query}" FROM "{query}"')
            if status != "OK":
                # Fallback: buscar solo en asunto
                status, data = mail.search(None, f'SUBJECT "{query}"')

            uids = data[0].split() if data and data[0] else []
            if not uids:
                mail.logout()
                return {
                    "thought": "",
                    "display": f"No encontre correos con '{query}'.",
                    "voice": f"No encontre correos con {query}.",
                }

            ultimos = uids[-5:][::-1]
            lineas = [f"Correos con '{query}' ({len(uids)} en total):"]
            for i, uid in enumerate(ultimos, 1):
                status, msg_data = mail.fetch(uid, "(RFC822.HEADER)")
                if status != "OK":
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                remitente = _decode_header_value(msg.get("From", ""))
                asunto = _decode_header_value(msg.get("Subject", ""))
                lineas.append(f"  {i}. De: {remitente}")
                lineas.append(f"     Asunto: {asunto}")
                lineas.append(f"     UID: {uid.decode()}")

            mail.logout()
            return {
                "thought": f"{len(uids)} correos con '{query}'",
                "display": "\n".join(lineas),
                "voice": f"Encontre {len(uids)} correos con {query}.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error buscando."}

    def _count_unread(self):
        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}
        try:
            mail.select("INBOX")
            status, data = mail.search(None, "UNSEEN")
            n = len(data[0].split()) if data and data[0] else 0
            mail.logout()
            return {
                "thought": f"{n} sin leer",
                "display": f"Tienes {n} correos sin leer.",
                "voice": f"Tienes {n} correos sin leer.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error."}

    def _send(self, to, subject, body):
        to = (to or "").strip()
        subject = (subject or "").strip() or "(sin asunto)"
        body = (body or "").strip()

        if not to:
            return {"thought": "", "display": "Falta el destinatario.", "voice": "Falta el destinatario."}
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to):
            return {"thought": "", "display": f"'{to}' no parece un email valido.", "voice": "Email invalido."}
        if not body:
            return {"thought": "", "display": "Falta el cuerpo del correo.", "voice": "Falta el cuerpo."}

        if not confirmation.require("gmail", "send", f"Enviar correo a {to}: '{subject}'"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        user, password = _load_env()
        if not user or not password:
            return {"thought": "Error gmail", "display": "No hay configuracion (.env.gmail.tmp).", "voice": "Sin configuracion."}

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=TIMEOUT) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)

            return {
                "thought": f"Correo enviado a {to}",
                "display": f"Correo enviado a {to}.\nAsunto: {subject}",
                "voice": f"Correo enviado a {to}.",
            }
        except Exception as e:
            return {"thought": "Error enviando", "display": f"Error enviando: {e}", "voice": "No pude enviar el correo."}