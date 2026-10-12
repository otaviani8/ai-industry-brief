# -*- coding: utf-8 -*-
"""
Lote semanal de contenido (lunes 7:30 de Argentina): borradores para Instagram, LinkedIn y X a partir de las noticias
del rubro de la semana. No publica nada: manda un mail con los borradores para que el dueño elija.

1. Junta los titulares de los últimos 7 días (Google News, las mismas búsquedas que el resumen diario).
2. Haiku elige las 6 noticias con más material para el dueño de una distribuidora.
3. Baja la nota completa de cada una (para que los datos salgan de la nota y no solo del titular).
4. Sonnet redacta con VOZ.md (la voz), MOLDES.md (los formatos de cada plataforma) y EJEMPLOS.md (guiones aprobados):
   2 guiones de reel, 2 carruseles, 3 posts de LinkedIn y 5 de X.
5. Cada pieza pasa por control.py (las reglas de ESCRITURA.md). Si alguna tiene errores, Sonnet la corrige una vez.
6. Manda el mail "Contenido · semana del dd/mm".

Uso:  python contenido.py            -> todo, manda el mail
      python contenido.py --seco     -> elige y baja las notas; no redacta ni manda
      python contenido.py --sin-mail -> todo menos el envío; imprime el mail en texto
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

import control
import resumen

BASE = os.path.dirname(os.path.abspath(__file__))
SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-4-5"
PRECIO = {SONNET: (2.0, 10.0), HAIKU: (1.0, 5.0)}  # USD por millón de tokens: entrada, salida
CAMPOS_PUBLICADOS = ["gancho", "guion", "cierre", "portada", "gigante", "laminas", "pie", "texto", "posts",
                     "encuesta", "primer_comentario"]
gasto = {"usd": 0.0}


def leer(nombre):
    with open(os.path.join(BASE, nombre), encoding="utf-8") as f:
        return f.read()


def claude(modelo, sistema, usuario, max_tokens, effort=None):
    import anthropic
    client = anthropic.Anthropic()
    extra = {"output_config": {"effort": effort}} if effort else {}
    if modelo == SONNET:
        # respaldo del servidor si el modelo rechaza la consulta (recomendado para Sonnet 5.5); con streaming porque
        # la salida es larga (piensa y después escribe el JSON)
        with client.beta.messages.stream(model=modelo, max_tokens=max_tokens, system=sistema,
                                         messages=[{"role": "user", "content": usuario}],
                                         betas=["server-side-fallback-2026-07-01"],
                                         extra_body={"fallbacks": "default", **extra}) as stream:
            resp = stream.get_final_message()
    else:
        resp = client.messages.create(model=modelo, max_tokens=max_tokens, system=sistema,
                                      messages=[{"role": "user", "content": usuario}], extra_body=extra or None)
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"{modelo} rechazó la consulta")
    if resp.stop_reason == "max_tokens":
        print(f"aviso: {modelo} llegó al tope de {max_tokens} tokens de salida", file=sys.stderr)
    entrada, salida = PRECIO.get(modelo, PRECIO[SONNET])
    costo = resp.usage.input_tokens / 1e6 * entrada + resp.usage.output_tokens / 1e6 * salida
    gasto["usd"] += costo
    print(f"{modelo}: {resp.usage.input_tokens} de entrada, {resp.usage.output_tokens} de salida, USD {costo:.4f}",
          file=sys.stderr)
    texto = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise RuntimeError(f"{modelo} no devolvió JSON: {texto[:300]}")
    return json.loads(m.group(0))


# ───────── 1 a 3: noticias ─────────

ELEGIR = """Sos el editor de contenido de Otaviani, una agencia argentina que le consigue comercios nuevos a distribuidoras, mayoristas, importadores y fábricas PyME que le venden a comercios. Recibís los titulares de la semana. Elegí las 6 noticias con más material para escribir publicaciones que le sirvan al dueño de una distribuidora argentina: un dato nuevo y concreto del canal mayorista, del consumo, de los comercios, de las importaciones, del crédito y los cheques, de los costos o de un rubro (ferretería, textil, juguetes, alimentos, electrodomésticos). Que no sean del mismo tema. Descartá notas de otros países, de color, de opinión sin dato y de política sin efecto en el comercio.
Respondé SOLO con un JSON: {"elegidas": [{"n": 12, "por_que": "una oración"}]}"""


def articulo(link, palabras=900):
    """Baja la nota original detrás del link de Google News y devuelve su texto."""
    try:
        from googlenewsdecoder import gnewsdecoder
        url = gnewsdecoder(link, interval=1).get("decoded_url") or link
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36"})
        h = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except Exception as e:
        return link, f"(no se pudo bajar la nota: {e})"
    cuerpo = ""
    for bloque in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h, re.S):
        m = re.search(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)*)"', bloque)
        if m:
            try:
                cuerpo = json.loads('"' + m.group(1) + '"')
                break
            except Exception:
                pass
    if len(cuerpo.split()) < 120:
        ps = [html.unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)]
        cuerpo = " ".join(p for p in ps if len(p) > 60 and "{" not in p and "http" not in p)
    return url, " ".join(re.sub(r"\s+", " ", cuerpo).split()[:palabras])


def noticias_de_la_semana(ahora):
    items = resumen.juntar(ahora - dt.timedelta(days=7), cuando="7d", tope=250)
    print(f"{len(items)} titulares de la semana", file=sys.stderr)
    lista = "\n".join(f"{i}. [{x['medio']}, {x['fecha'].astimezone(resumen.ART):%d/%m}] {x['titulo']}"
                      for i, x in enumerate(items, 1))
    elegidas = claude(HAIKU, ELEGIR, "Titulares:\n" + lista, 1500).get("elegidas", [])
    out = []
    for e in elegidas[:6]:
        if not (isinstance(e.get("n"), int) and 1 <= e["n"] <= len(items)):
            continue
        x = dict(items[e["n"] - 1])
        x["url"], x["texto"] = articulo(x["link"])
        x["por_que"] = e.get("por_que", "")
        out.append(x)
    return out


# ───────── 4 y 5: redacción y control ─────────

PEDIDO = """Escribí el lote de esta semana con las noticias de abajo.

Cantidades exactas: {cantidad}.
Usá cada noticia para una o más piezas, sin repetir el mismo ángulo en dos piezas. Cada dato, número y cita sale del texto de la nota; si no está en la nota, no va.

Respondé SOLO con un JSON válido, sin texto antes ni después, con esta forma (los campos que no aplican a un tipo se omiten):
{{"piezas": [
 {{"id": "R1", "tipo": "reel", "molde": "...", "etapa": "TOFU", "noticia": 1, "para_que": "...", "gancho": ["...", "..."], "guion": ["...", "..."], "cierre": "...", "portada": "...", "gigante": "..."}},
 {{"id": "C1", "tipo": "carrusel", "molde": "...", "etapa": "TOFU", "noticia": 2, "para_que": "...", "laminas": ["...", "..."], "pie": "...", "imagen": "qué foto o persona va en la portada"}},
 {{"id": "L1", "tipo": "linkedin", "molde": "...", "etapa": "TOFU", "noticia": 3, "para_que": "...", "formato": "...", "texto": "...", "adjunto": "qué imagen, documento o encuesta acompaña", "encuesta": {{"pregunta": "...", "opciones": ["..."]}}, "primer_comentario": "..."}},
 {{"id": "X1", "tipo": "x", "molde": "...", "etapa": "TOFU", "noticia": 4, "para_que": "...", "formato": "...", "posts": ["..."], "adjunto": "...", "encuesta": {{"pregunta": "...", "opciones": ["..."]}}}}
]}}
"noticia" es el número de la noticia en la lista. Los ids van R1, R2, C1, C2, L1 a L3, X1 a X5.

Noticias:
{noticias}"""


def plan(hoy):
    """Qué molde lleva cada pieza esta semana (MOLDES.md). La encuesta de LinkedIn va la primera semana del mes."""
    linkedin = "L3 (encuesta), L1 y L2" if hoy.day <= 7 else "L1, L1 y L2"
    return ("2 de tipo reel (moldes distintos entre E5, E2, E1 y E10), 2 de tipo carrusel, "
            f"3 de tipo linkedin con los moldes {linkedin}, y 5 de tipo x con los moldes X1, X1, X1, X2 y X4")


def textos_publicados(p):
    out = []
    for k in CAMPOS_PUBLICADOS:
        v = p.get(k)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out += [x for x in v if isinstance(x, str)]
        elif isinstance(v, dict):
            out += [v.get("pregunta", "")] + [x for x in v.get("opciones", []) if isinstance(x, str)]
    return [t for t in out if t.strip()]


def controlar(piezas):
    for p in piezas:
        errores, avisos = [], []
        for t in textos_publicados(p):
            e, a = control.revisar(t, hablado=p.get("tipo") == "reel")
            errores += e
            avisos += a
        p["_errores"], p["_avisos"] = errores, avisos
    return [p for p in piezas if p["_errores"]]


def redactar(noticias):
    sistema = leer("VOZ.md") + "\n\n" + leer("MOLDES.md") + "\n\n" + leer("EJEMPLOS.md")
    bloque = "\n\n".join(f"### Noticia {i}\nTitular: {x['titulo']}\nMedio: {x['medio']}, {x['fecha'].astimezone(resumen.ART):%d/%m/%Y}\n"
                         f"Link: {x['url']}\nTexto de la nota: {x['texto']}" for i, x in enumerate(noticias, 1))
    piezas = claude(SONNET, sistema, PEDIDO.format(cantidad=plan(dt.date.today()), noticias=bloque), 32000,
                    effort="low").get("piezas", [])
    malas = controlar(piezas)
    if malas:
        pedido = ("Estas piezas no pasaron el control de escritura. Corregí solo lo que marca cada error, sin cambiar el resto, "
                  "y devolvé SOLO un JSON {\"piezas\": [...]} con las piezas corregidas completas (mismos ids y campos).\n\n"
                  + json.dumps([{k: v for k, v in p.items() if not k.startswith("_")} | {"errores": p["_errores"]} for p in malas],
                               ensure_ascii=False))
        arregladas = {p["id"]: p for p in claude(SONNET, sistema, pedido, 20000, effort="low").get("piezas", [])}
        piezas = [arregladas.get(p["id"], p) for p in piezas]
        controlar(piezas)
    return piezas


# ───────── 6: el mail ─────────

TITULOS = {"reel": "Guiones de reel", "carrusel": "Carruseles", "linkedin": "LinkedIn", "x": "X"}


def armar_mail(piezas, noticias, hoy):
    asunto = f"Contenido · semana del {hoy:%d/%m} · {len(piezas)} borradores"
    h = [f"<p>Borradores de la semana, a partir de {len(noticias)} noticias del rubro. No se publicó nada.</p>"]
    t = [f"Borradores de la semana, a partir de {len(noticias)} noticias del rubro. No se publicó nada.\n"]
    for tipo, titulo in TITULOS.items():
        grupo = [p for p in piezas if p.get("tipo") == tipo]
        if not grupo:
            continue
        h.append(f"<h2 style=\"font-size:18px;margin-top:28px\">{titulo}</h2>")
        t.append(f"\n===== {titulo.upper()} =====\n")
        for p in grupo:
            n = p.get("noticia")
            x = noticias[n - 1] if isinstance(n, int) and 1 <= n <= len(noticias) else None
            cab = f"{p.get('id', '')} · {p.get('etapa', '')} · {p.get('molde', '')}"
            h.append(f"<div style=\"border-left:3px solid #ccc;padding-left:12px;margin:16px 0\"><p><b>{html.escape(cab)}</b><br>"
                     f"<i>{html.escape(p.get('para_que', ''))}</i></p>")
            t.append(f"\n--- {cab}\nPara qué: {p.get('para_que', '')}")
            for k in ["formato", "gancho", "guion", "cierre", "portada", "gigante", "laminas", "pie", "imagen", "texto",
                      "posts", "encuesta", "adjunto", "primer_comentario"]:
                v = p.get(k)
                if not v:
                    continue
                if isinstance(v, dict):
                    v = [v.get("pregunta", "")] + [f"Opción: {o}" for o in v.get("opciones", [])]
                if isinstance(v, list):
                    h.append(f"<p><b>{k.replace('_', ' ').capitalize()}</b><br>" + "<br>".join(f"{i}. {html.escape(str(s))}" for i, s in enumerate(v, 1)) + "</p>")
                    t.append(f"{k.replace('_', ' ').capitalize()}:\n" + "\n".join(f"  {i}. {s}" for i, s in enumerate(v, 1)))
                else:
                    h.append(f"<p><b>{k.replace('_', ' ').capitalize()}</b><br>{html.escape(str(v)).replace(chr(10), '<br>')}</p>")
                    t.append(f"{k.replace('_', ' ').capitalize()}: {v}")
            if x:
                h.append(f"<p><small>Fuente: <a href=\"{html.escape(x['url'])}\">{html.escape(x['medio'])}, "
                         f"{x['fecha'].astimezone(resumen.ART):%d/%m}</a></small></p>")
                t.append(f"Fuente: {x['medio']}, {x['fecha'].astimezone(resumen.ART):%d/%m} · {x['url']}")
            control_txt = ("Control: " + "; ".join(p.get("_errores", []) + p.get("_avisos", []))) if (p.get("_errores") or p.get("_avisos")) else "Control: pasó sin observaciones."
            h.append(f"<p><small style=\"color:#888\">{html.escape(control_txt)}</small></p></div>")
            t.append(control_txt)
    h.append(f"<hr><p><small>Costo de este lote: USD {gasto['usd']:.3f}.</small></p>")
    t.append(f"\nCosto de este lote: USD {gasto['usd']:.3f}.")
    return asunto, "\n".join(t), "<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.5;max-width:680px\">" + "".join(h) + "</div>"


def main():
    ahora = dt.datetime.now(resumen.ART)
    noticias = noticias_de_la_semana(ahora)
    if "--seco" in sys.argv:
        for i, x in enumerate(noticias, 1):
            print(f"{i}. {x['titulo']} ({x['medio']}) · {len(x['texto'].split())} palabras de nota · {x['por_que']}")
        return
    piezas = redactar(noticias)
    asunto, txt, htm = armar_mail(piezas, noticias, ahora.date())
    if "--sin-mail" in sys.argv:
        print(asunto + "\n\n" + txt)
        return
    resumen.mandar(asunto, txt, htm, nombre="Contenido Otaviani")
    print(f"mail enviado: {asunto} · costo total USD {gasto['usd']:.3f}", file=sys.stderr)


if __name__ == "__main__":
    main()
