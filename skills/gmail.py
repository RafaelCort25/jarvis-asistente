"""Skill de Gmail: leer, buscar y enviar correos via IMAP/SMTP."""
import email
import imaplib
import mimetypes
import os
import re
import smtplib
from email.header import decode_header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
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
        # ── Adjuntos ──
        if action == "send_attachment":
            return self._send_attachment(
                params.get("to", ""),
                params.get("subject", ""),
                params.get("body", ""),
                params.get("files", []),
            )
        if action == "list_attachments":
            return self._list_attachments(params.get("uid", ""))
        if action == "download_attachments":
            return self._download_attachments(
                params.get("uid", ""),
                params.get("output_dir", ""),
            )
        # ── Busqueda avanzada ──
        if action == "search_advanced":
            return self._search_advanced(params)
        # ── Gestion ──
        if action == "mark_read":
            return self._mark_read(params.get("uid", ""), read=True)
        if action == "mark_unread":
            return self._mark_read(params.get("uid", ""), read=False)
        if action == "archive":
            return self._archive(params.get("uid", ""))
        if action == "delete":
            return self._delete(params.get("uid", ""))
        # ── Responder ──
        if action == "reply":
            return self._reply(params.get("uid", ""), params.get("body", ""))
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

    # ─── ADJUNTOS ────────────────────────────────────────────────────────

    def _send_attachment(self, to, subject, body, files):
        """Envia un correo con archivos adjuntos."""
        to = (to or "").strip()
        subject = (subject or "").strip() or "(sin asunto)"
        body = (body or "").strip()

        if not to:
            return {"thought": "", "display": "Falta el destinatario.", "voice": "Falta el destinatario."}
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to):
            return {"thought": "", "display": f"'{to}' no parece un email valido.", "voice": "Email invalido."}
        if not files:
            return {"thought": "", "display": "Falta la lista de archivos adjuntos.", "voice": "Sin adjuntos."}

        # Resolver rutas
        adjuntos = []
        for f in files:
            fp = Path(f.strip().strip('"').strip("'"))
            if not fp.is_absolute():
                fp = ROOT / fp
            if not fp.exists():
                return {"thought": "", "display": f"No encontre el archivo: {fp}", "voice": "Archivo no encontrado."}
            adjuntos.append(fp)

        total_mb = sum(a.stat().st_size for a in adjuntos) / 1024 / 1024
        if total_mb > 25:
            return {"thought": "", "display": f"Adjuntos demasiado grandes ({total_mb:.1f} MB, max 25 MB).", "voice": "Adjuntos muy grandes."}

        resumen = f"Enviar a {to}: '{subject}' con {len(adjuntos)} adjunto(s)"
        if not confirmation.require("gmail", "send", resumen):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        user, password = _load_env()
        if not user or not password:
            return {"thought": "Error gmail", "display": "No hay configuracion (.env.gmail.tmp).", "voice": "Sin configuracion."}

        try:
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to
            msg.attach(MIMEText(body, "plain", "utf-8"))

            for adj in adjuntos:
                ctype, _ = mimetypes.guess_type(str(adj))
                if ctype is None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)
                with open(adj, "rb") as f:
                    part = MIMEApplication(f.read(), _subtype=subtype)
                part.add_header("Content-Disposition", "attachment", filename=adj.name)
                msg.attach(part)

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=TIMEOUT) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)

            nombres = ", ".join(a.name for a in adjuntos)
            return {
                "thought": f"Correo con adjuntos enviado a {to}",
                "display": f"Correo enviado a {to}.\nAdjuntos: {nombres}",
                "voice": f"Correo enviado con {len(adjuntos)} adjuntos.",
            }
        except Exception as e:
            return {"thought": "Error enviando", "display": f"Error enviando: {e}", "voice": "No pude enviar."}

    def _list_attachments(self, uid):
        """Lista los adjuntos de un correo (sin descargarlos)."""
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
            adjuntos = []
            for part in msg.walk():
                filename = part.get_filename()
                if filename:
                    filename = _decode_header_value(filename)
                    size = len(part.get_payload(decode=True) or b"")
                    adjuntos.append({"name": filename, "size_kb": round(size / 1024, 1), "content_type": part.get_content_type()})

            mail.logout()

            if not adjuntos:
                return {"thought": "", "display": f"El correo {uid} no tiene adjuntos.", "voice": "Sin adjuntos."}

            lineas = [f"El correo tiene {len(adjuntos)} adjunto(s):"]
            for i, a in enumerate(adjuntos, 1):
                lineas.append(f"  {i}. {a['name']} ({a['size_kb']} KB) - {a['content_type']}")

            return {
                "thought": f"{len(adjuntos)} adjuntos",
                "display": "\n".join(lineas),
                "voice": f"El correo tiene {len(adjuntos)} adjuntos.",
                "data": adjuntos,
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error."}

    def _download_attachments(self, uid, output_dir):
        """Descarga los adjuntos de un correo a disco."""
        if not uid:
            return {"thought": "", "display": "Falta el UID.", "voice": "Falta el UID."}

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

            if output_dir:
                out_dir = Path(output_dir.strip().strip('"'))
                if not out_dir.is_absolute():
                    out_dir = ROOT / out_dir
            else:
                out_dir = ROOT / "sandbox" / "gmail_adjuntos" / f"correo_{uid}"

            try:
                out_dir.relative_to(ROOT)
            except ValueError:
                mail.logout()
                return {"thought": "", "display": f"Ruta fuera del proyecto: {out_dir}", "voice": "Ruta invalida."}

            out_dir.mkdir(parents=True, exist_ok=True)

            guardados = []
            for part in msg.walk():
                filename = part.get_filename()
                if filename:
                    filename = _decode_header_value(filename)
                    safe_name = re.sub(r'[<>:"/\\|?*]', "_", filename)
                    out_file = out_dir / safe_name
                    payload = part.get_payload(decode=True)
                    if payload:
                        out_file.write_bytes(payload)
                        guardados.append(out_file)

            mail.logout()

            if not guardados:
                return {"thought": "", "display": f"El correo no tiene adjuntos.", "voice": "Sin adjuntos."}

            lineas = [f"Descargados {len(guardados)} adjuntos en {out_dir}:"]
            for g in guardados:
                lineas.append(f"  - {g.name} ({g.stat().st_size // 1024} KB)")

            return {
                "thought": f"{len(guardados)} adjuntos descargados",
                "display": "\n".join(lineas),
                "voice": f"Descargue {len(guardados)} adjuntos.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error descargando."}

    # ─── BUSQUEDA AVANZADA ───────────────────────────────────────────────

    def _search_advanced(self, params):
        """Busqueda con filtros: from, subject, since, before, unread, limit."""
        from_addr = params.get("from_addr", "").strip()
        subject = params.get("subject", "").strip()
        since_date = params.get("since", "").strip()
        before_date = params.get("before", "").strip()
        unread_only = params.get("unread_only", False)
        limit = int(params.get("limit", 5) or 5)

        if not any([from_addr, subject, since_date, before_date, unread_only]):
            return {"thought": "", "display": "Necesito al menos un filtro.", "voice": "Sin filtros."}

        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}

        try:
            mail.select("INBOX")
            criterios = []
            if from_addr:
                criterios.extend(["FROM", f'"{from_addr}"'])
            if subject:
                criterios.extend(["SUBJECT", f'"{subject}"'])
            if since_date:
                criterios.extend(["SINCE", since_date])
            if before_date:
                criterios.extend(["BEFORE", before_date])
            if unread_only:
                criterios.append("UNSEEN")

            if not criterios:
                criterios = ["ALL"]

            status, data = mail.search(None, *criterios)
            if status != "OK":
                mail.logout()
                return {"thought": "", "display": "Error en la busqueda.", "voice": "Error."}

            uids = data[0].split() if data and data[0] else []
            if not uids:
                mail.logout()
                return {"thought": "", "display": "No encontre correos con esos filtros.", "voice": "Sin resultados."}

            ultimos = uids[-limit:][::-1]
            lineas = [f"Correos encontrados ({len(uids)} total, mostrando {len(ultimos)}):"]
            for i, uid in enumerate(ultimos, 1):
                status, msg_data = mail.fetch(uid, "(RFC822.HEADER)")
                if status != "OK":
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                remitente = _decode_header_value(msg.get("From", ""))
                asunto = _decode_header_value(msg.get("Subject", ""))
                fecha = msg.get("Date", "")[:25]
                lineas.append(f"  {i}. De: {remitente}")
                lineas.append(f"     Asunto: {asunto}")
                lineas.append(f"     Fecha: {fecha}")
                lineas.append(f"     UID: {uid.decode()}")

            mail.logout()
            return {
                "thought": f"{len(uids)} correos encontrados",
                "display": "\n".join(lineas),
                "voice": f"Encontre {len(uids)} correos.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error."}

    # ─── GESTION ─────────────────────────────────────────────────────────

    def _mark_read(self, uid, read=True):
        """Marca un correo como leido o no leido."""
        if not uid:
            return {"thought": "", "display": "Falta el UID.", "voice": "Falta el UID."}

        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}

        try:
            mail.select("INBOX")
            flag = "+FLAGS" if read else "-FLAGS"
            status, _ = mail.store(str(uid).encode(), flag, "\\Seen")
            mail.logout()
            estado = "leido" if read else "no leido"
            return {
                "thought": f"Marcado como {estado}",
                "display": f"Correo {uid} marcado como {estado}.",
                "voice": f"Marcado como {estado}.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error."}

    def _archive(self, uid):
        """Archiva un correo (lo quita de INBOX)."""
        if not uid:
            return {"thought": "", "display": "Falta el UID.", "voice": "Falta el UID."}

        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}

        try:
            mail.select("INBOX")
            status, _ = mail.copy(str(uid).encode(), "[Gmail]/All Mail")
            if status != "OK":
                mail.logout()
                return {"thought": "", "display": "No pude archivar.", "voice": "Error archivando."}
            mail.store(str(uid).encode(), "+FLAGS", "\\Deleted")
            mail.expunge()
            mail.logout()
            return {
                "thought": f"Correo {uid} archivado",
                "display": f"Correo {uid} archivado.",
                "voice": "Correo archivado.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error."}

    def _delete(self, uid):
        """Mueve un correo a la papelera."""
        if not uid:
            return {"thought": "", "display": "Falta el UID.", "voice": "Falta el UID."}

        if not confirmation.require("gmail", "delete", f"Borrar correo {uid}"):
            return {"thought": "Cancelado", "display": "Cancelado.", "voice": "Cancelado."}

        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}

        try:
            mail.select("INBOX")
            status, _ = mail.copy(str(uid).encode(), "[Gmail]/Trash")
            if status == "OK":
                mail.store(str(uid).encode(), "+FLAGS", "\\Deleted")
                mail.expunge()
            mail.logout()
            return {
                "thought": f"Correo {uid} a la papelera",
                "display": f"Correo {uid} movido a la papelera.",
                "voice": "Correo borrado.",
            }
        except Exception as e:
            try:
                mail.logout()
            except Exception:
                pass
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error."}

    # ─── RESPONDER ───────────────────────────────────────────────────────

    def _reply(self, uid, body):
        """Responde al correo con el UID dado."""
        if not uid or not body:
            return {"thought": "", "display": "Necesito UID y cuerpo.", "voice": "Faltan datos."}

        mail, user, err = self._connect_imap()
        if err:
            return {"thought": "Error gmail", "display": err, "voice": "No pude conectar."}

        try:
            mail.select("INBOX")
            status, msg_data = mail.fetch(str(uid).encode(), "(RFC822.HEADER)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                mail.logout()
                return {"thought": "", "display": "No encontre el correo.", "voice": "No lo encontre."}

            msg = email.message_from_bytes(msg_data[0][1])
            original_from = _decode_header_value(msg.get("From", ""))
            original_subject = _decode_header_value(msg.get("Subject", ""))
            msg_id = msg.get("Message-ID", "")
            mail.logout()

            # Extraer email del From
            m = re.search(r"<([^>]+)>", original_from)
            to_addr = m.group(1) if m else original_from.strip()
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to_addr):
                return {"thought": "", "display": f"No pude extraer email de: {original_from}", "voice": "Email invalido."}

            subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

            user, password = _load_env()
            if not user or not password:
                return {"thought": "", "display": "Sin configuracion.", "voice": "Sin configuracion."}

            msg_reply = MIMEText(body, "plain", "utf-8")
            msg_reply["Subject"] = subject
            msg_reply["From"] = user
            msg_reply["To"] = to_addr
            if msg_id:
                msg_reply["In-Reply-To"] = msg_id
                msg_reply["References"] = msg_id

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=TIMEOUT) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg_reply)

            return {
                "thought": f"Respuesta enviada a {to_addr}",
                "display": f"Respuesta enviada a {to_addr}.\nAsunto: {subject}",
                "voice": f"Respuesta enviada.",
            }
        except Exception as e:
            return {"thought": "Error", "display": f"Error: {e}", "voice": "Error respondiendo."}

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