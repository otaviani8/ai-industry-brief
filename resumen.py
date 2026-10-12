# -*- coding: utf-8 -*-
"""
Resumen diario del rubro (distribuidoras, mayoristas, importadores y fábricas que le venden a comercios).

1. Junta noticias de Google News (RSS, gratis) con las búsquedas de BUSQUEDAS.
2. Se queda solo con lo publicado en la ventana (24 h; el lunes, desde el viernes) según la fecha del RSS.
3. Hace UNA consulta a Claude Haiku 4.5 para elegir hasta 7 y explicar qué significa cada una.
4. Manda el mail por Gmail (SMTP con contraseña de aplicación).

Uso:  python resumen.py            -> todo, manda el mail
      python resumen.py --seco     -> solo junta y filtra; imprime lo que mandaría a Haiku (sin IA ni mail)
      python resumen.py --sin-mail -> todo menos el envío; imprime el mail

Variables de entorno: ANTHROPIC_API_KEY, GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO.
"""
import datetime as dt
import email.utils
import html
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ART = dt.timezone(dt.timedelta(hours=-3))
MODELO = "claude-haiku-4-5"
MAX_ITEMS = 120

BUSQUEDAS = [
    "consumo masivo mayoristas autoservicios",
    "Scentia consumo",
    "NielsenIQ consumo masivo",
    "CADAM mayoristas",
    "autoservicios mayoristas",
    "distribuidoras mayoristas",
    "ventas minoristas pyme CAME",
    "importaciones ARCA aduana importadores",
    "aranceles importación bienes de consumo",
    "courier Temu Shein importaciones",
    "cheques rechazados pymes",
    "mora empresas crédito pymes",
    "costo transporte de cargas FADEEAC",
    "cierre de comercios locales",
    "Ingresos Brutos percepciones mayoristas",
    "Makro OR Maxiconsumo OR Diarco OR Vital OR Yaguar mayorista",
    "industria textil importaciones",
    "ferreterías ventas",
    "dólar mayorista banda cambiaria",
    "inflación INDEC",
]

# Datos programados (actualizar en diciembre con el calendario INDEC del primer semestre de 2027)
CALENDARIO = [
    (dt.date(2026, 10, 13), "INDEC publica la inflación de septiembre."),
    (dt.date(2026, 10, 18), "Día de la Madre: última semana de compras de los comercios."),
    (dt.date(2026, 10, 21), "INDEC publica las importaciones de septiembre, con el courier."),
    (dt.date(2026, 10, 30), "INDEC publica autoservicios mayoristas de agosto."),
    (dt.date(2026, 11, 2), "Arranca CyberMonday (hasta el 4/11)."),
    (dt.date(2026, 11, 3), "Conferencia Industrial de la UIA."),
    (dt.date(2026, 11, 12), "INDEC publica la inflación de octubre."),
    (dt.date(2026, 11, 19), "INDEC publica las importaciones de octubre."),
    (dt.date(2026, 11, 25), "INDEC publica autoservicios mayoristas de septiembre."),
]

SISTEMA = """Sos el analista de noticias de Otaviani, una agencia argentina que le consigue comercios nuevos a distribuidoras, mayoristas, importadores y fábricas PyME que le venden a comercios (ferreterías, kioscos, almacenes, autoservicios, bazares). Le armás a Sebastián, el dueño, el resumen de la mañana con las noticias del rubro de ESOS clientes. No es un resumen de marketing ni de publicidad.

Recibís una lista numerada de titulares de las últimas horas. Elegí hasta 7, en orden de importancia para alguien que le vende a distribuidoras. Prioridad: consumo y canal mayorista; cámaras del rubro (CADAM, CAME, CAC, CIRA, COPAL); reglas de importación, aranceles y courier; cheques, mora, crédito y dólar; fletes e impuestos de los mayoristas; cierres y aperturas de comercios; movimientos de mayoristas grandes; rubros con noticia propia (textil, calzado, juguetes, ferretería, electrodomésticos, alimentos).

Descartá: notas de color, opinión sin dato, notas de otros países, deportes, política sin efecto en el comercio, y repeticiones del mismo hecho (quedate con el titular más completo).

Reglas de escritura:
- Usá SOLO la información del titular. No agregues números, nombres ni causas que no estén ahí.
- "titular": el hecho, sin adjetivos, en una línea.
- "que_paso": una oración que cuenta el hecho con los datos del titular.
- "que_significa": una oración sobre qué significa para una distribuidora o importadora que le vende a comercios.
- Español rioplatense, registro institucional, frases cortas. Sin emojis, sin signo de apertura de pregunta, sin guiones largos. Sin palabras de agencia (leads, embudo, funnel, B2B, escalar). Se habla de comercios, pedidos, lista de precios, plazo, margen, cheques.
- Si no hay nada que valga la pena, devolvé "noticias" vacío.

Respondé SOLO con un JSON válido, sin texto antes ni después, con esta forma:
{"lo_mas_importante": "una oración con el hecho del día, o vacío", "asunto": "el hecho principal en 6 a 9 palabras", "noticias": [{"n": 3, "titular": "...", "que_paso": "...", "que_significa": "..."}]}
donde "n" es el número del titular en la lista."""


def ventana(ahora):
    """24 h (con 2 de margen); el lunes, desde el viernes a las 7:00."""
    horas = 74 if ahora.weekday() == 0 else 26
    return ahora - dt.timedelta(hours=horas)


def google_news(q, cuando="3d"):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{q} when:{cuando}", "hl": "es-419", "gl": "AR", "ceid": "AR:es-419"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raiz = ET.fromstring(r.read())
    out = []
    for it in raiz.iter("item"):
        titulo = (it.findtext("title") or "").strip()
        medio = (it.findtext("source") or "").strip()
        if medio and titulo.endswith(" - " + medio):
            titulo = titulo[: -len(" - " + medio)]
        try:
            fecha = email.utils.parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            continue
        out.append({"titulo": titulo, "medio": medio, "fecha": fecha, "link": (it.findtext("link") or "").strip()})
    return out


def clave(t):
    return re.sub(r"[^a-z0-9áéíóúñ ]", "", t.lower())[:80]


def juntar(desde, cuando="3d", tope=MAX_ITEMS):
    vistos, items = set(), []
    for q in BUSQUEDAS:
        try:
            res = google_news(q, cuando)
        except Exception as e:
            print(f"aviso: '{q}' fallo: {e}", file=sys.stderr)
            continue
        for x in res:
            k = clave(x["titulo"])
            if x["fecha"] >= desde and k not in vistos:
                vistos.add(k)
                items.append(x)
    items.sort(key=lambda x: x["fecha"], reverse=True)
    return items[:tope]


def pedir_a_haiku(items):
    import anthropic
    lista = "\n".join(f"{i}. [{x['medio']}, {x['fecha'].astimezone(ART):%d/%m %H:%M}] {x['titulo']}"
                      for i, x in enumerate(items, 1))
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODELO,
        max_tokens=3000,
        system=SISTEMA,
        messages=[{"role": "user", "content": "Titulares:\n" + lista}],
    )
    texto = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{.*\}", texto, re.S)
    datos = json.loads(m.group(0)) if m else {"lo_mas_importante": "", "asunto": "", "noticias": []}
    u = resp.usage
    costo = u.input_tokens / 1e6 * 1.0 + u.output_tokens / 1e6 * 5.0
    print(f"haiku: {u.input_tokens} tokens de entrada, {u.output_tokens} de salida, USD {costo:.4f}", file=sys.stderr)
    return datos


def semana(hoy):
    out = [f"{d:%d/%m}: {t}" for d, t in CALENDARIO if hoy <= d <= hoy + dt.timedelta(days=7)]
    for d in (hoy + dt.timedelta(days=k) for k in range(8)):
        if d.day <= 7 and d.weekday() == 6:
            out.append(f"{d:%d/%m}: CAME publica las ventas minoristas PyME del mes pasado.")
        if d.day == 1:
            out.append(f"Primeros días de {d:%m}: FADEEAC publica el costo del transporte de cargas.")
    if any(20 <= (hoy + dt.timedelta(days=k)).day <= 25 for k in range(8)):
        out.append("Entre el 20 y el 25: Scentia publica el consumo masivo por canal (sale por los diarios).")
    return sorted(set(out))


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def armar_mail(datos, items, hoy):
    noticias = [n for n in datos.get("noticias", []) if isinstance(n.get("n"), int) and 1 <= n["n"] <= len(items)][:7]
    asunto = f"Rubro · {DIAS[hoy.weekday()]} {hoy:%d/%m} · " + (datos.get("asunto") or "Sin novedades del rubro")
    txt, htm = [], []
    if noticias and datos.get("lo_mas_importante"):
        txt.append(f"Lo más importante: {datos['lo_mas_importante']}\n")
        htm.append(f"<p><b>Lo más importante:</b> {html.escape(datos['lo_mas_importante'])}</p><hr>")
    if not noticias:
        txt.append("Sin novedades del rubro.\n")
        htm.append("<p>Sin novedades del rubro.</p>")
    for n in noticias:
        it = items[n["n"] - 1]
        fecha = f"{it['fecha'].astimezone(ART):%d/%m}"
        txt.append(f"{n['titular']}\nQué pasó: {n['que_paso']}\nQué significa para una distribuidora: "
                   f"{n['que_significa']}\nFuente: {it['medio']}, {fecha} · {it['link']}\n")
        htm.append(f"<p><b>{html.escape(n['titular'])}</b><br>Qué pasó: {html.escape(n['que_paso'])}<br>"
                   f"Qué significa para una distribuidora: {html.escape(n['que_significa'])}<br>"
                   f"<small>Fuente: <a href=\"{html.escape(it['link'])}\">{html.escape(it['medio'])}</a>, {fecha}</small></p>")
    sem = semana(hoy)
    if sem:
        txt.append("Esta semana salen:\n" + "\n".join("- " + s for s in sem))
        htm.append("<hr><p><b>Esta semana salen:</b><br>" + "<br>".join(html.escape(s) for s in sem) + "</p>")
    return asunto, "\n".join(txt), "<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.5;max-width:640px\">" + "".join(htm) + "</div>"


def mandar(asunto, txt, htm, nombre="Resumen del rubro"):
    user, pwd = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = asunto, f"{nombre} <{user}>", os.environ.get("MAIL_TO", user)
    msg.attach(MIMEText(txt, "plain", "utf-8"))
    msg.attach(MIMEText(htm, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pwd)
        s.send_message(msg)


def main():
    ahora = dt.datetime.now(ART)
    items = juntar(ventana(ahora))
    print(f"{len(items)} titulares en la ventana", file=sys.stderr)
    if "--seco" in sys.argv:
        for i, x in enumerate(items, 1):
            print(f"{i}. [{x['medio']}, {x['fecha'].astimezone(ART):%d/%m %H:%M}] {x['titulo']}")
        return
    datos = pedir_a_haiku(items) if items else {"noticias": []}
    asunto, txt, htm = armar_mail(datos, items, ahora.date())
    if "--sin-mail" in sys.argv:
        print(asunto + "\n\n" + txt)
        return
    mandar(asunto, txt, htm)
    print("mail enviado: " + asunto, file=sys.stderr)


if __name__ == "__main__":
    main()
