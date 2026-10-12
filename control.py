# -*- coding: utf-8 -*-
"""
Las reglas de la guía interna (la guía de voz de Otaviani, ESCRITURA.md), como función,
para revisar cada borrador antes de mandarlo. Si cambian las reglas allá, se copian acá.

revisar(texto, hablado) -> (errores, avisos)
  hablado=True  para guiones de reel (tope de 22 palabras por oración)
  hablado=False para carruseles, LinkedIn y X (tope de 20)
Agregado del 3/10/2026: la garantía y las promesas de resultado son error en todo.
"""
import re


def R(*ps):
    return re.compile("|".join(ps), re.I)


SUPERLATIVO = ("superlativo", R(r"\b(el|la|lo|los|las) mejor(es)?\b", r"\bn[úu]mero uno\b"))
ERRORES = [
    ("signo de apertura, raya o emoji", re.compile("[¿¡—]|[\U0001F300-\U0001FAFF☀-➿]")),
    ("jerga en inglés", R(r"\b(leads?|B2B|B2C|funnel|growth|engagement|performance|call|branding|insights?|feedback|CTA|ROI)\b")),
    ("promesa vacía", R(r"\bl[íi]der(es)? (del|en el) (mercado|rubro|sector)\b", r"\bsomos (los|las) mejores\b",
                        r"\b[úu]nic[oa]s? en (el|la) (mercado|rubro|pa[íi]s)\b", r"\bal instante\b")),
    ("verbo o frase de agencia", R(r"\bescal(ar|an|ó|amos|ando|en|e)\b", r"\bpotenci(ar|amos|á)\b", r"\bimpuls(ar|amos|á)\b",
                                   r"\bllev(ar|amos) (tu|su) (negocio|marca|empresa) al (siguiente|próximo) nivel\b",
                                   r"\bsoluciones integrales\b", r"\bsinergia", r"\b360\b", r"\bde la mano de\b",
                                   r"\bacompañamos\b", r"\btransform(ar|amos) (tu|su) (negocio|marca|empresa)\b",
                                   r"\bhoy más que nunca\b", r"\ben el mundo (de|del)\b", r"\binnovador(a|es|as)?\b",
                                   r"\bexperiencias? únicas?\b")),
    ("frase de adentro que se filtró afuera", R(r"\bsin vueltas\b", r"\bpalabras raras\b", r"\bsin sorpresas\b",
                                                 r"\bte lo cuento sin\b", r"\bcomo si nunca hubieras\b", r"\bsin rodeos\b",
                                                 r"\bsin humo\b", r"\ben idioma de\b", r"\ben criollo\b",
                                                 r"\btraducido al\b",
                                                 r"(^|[.\n]\s*)(qué mirar|para el comercio|para la distribuidora)\b")),
    ("defensa ante la desconfianza", R(r"\bsin compromiso\b", r"\bsin cargo\b", r"\b(charla|llamada|diagn[óo]stico|plan) gratis\b",
                                       r"\bqueda a tu nombre\b", r"\bno hace falta que conf[íi]es\b", r"\bsin letra chica\b")),
    ("molde de IA: no es X, es Y", R(r"\bno es (un|una|el|la|solo|sólo)?\s?[^.,;]{1,40}, es\b", r"\bno se trata de\b",
                                      r"\bno (solo|sólo) [^.]{1,60} sino\b")),
    ("oferta retirada (sin garantía desde el 3/10)", R(r"\bgarant[íi]", r"\b300 consultas\b", r"\bpor contrato\b")),
    ("nombre de marca viejo", R(r"\bGrupo Otaviani\b")),
]
AVISOS = [
    ("dos puntos en el medio de la oración", re.compile(r"\w: [a-záéíóúñ]")),
    ("relleno típico", R(r"\basí de (simple|sencillo)\b", r"\by esa cuenta no es chica\b", r"\bque es tarde\b",
                         r"\bcasi nadie lo tiene\b", r"\bliteralmente\b", r"\bbásicamente\b", r"\brealmente\b")),
    ("adjetivo de agencia", R(r"\bpremium\b", r"\b(productos?|servicios?|trabajos?|contenidos?) de calidad\b", r"\ba medida\b",
                              r"\bestratégic[oa]s?\b", r"\bintegral(es)?\b", r"\bpersonalizad[oa]s?\b", r"\bexcelencia\b")),
]


def oraciones(t):
    return [o for o in re.split(r"(?<=[.?!])\s+", t.strip()) if o]


def revisar(texto, hablado=False):
    tope = 22 if hablado else 20
    # lo que no se publica: indicaciones de [VISUAL], links y la línea de fuente (sus dos puntos no son de oración)
    texto = re.sub(r"\[VISUAL:[^\]]*\]", "", texto)
    texto = re.sub(r"https?://\S+", "", texto)
    texto = re.sub(r"(?im)^\s*fuente:.*$", "", texto).strip()
    errores, avisos = [], []
    reglas = ERRORES + ([] if hablado else [SUPERLATIVO])
    for nombre, rx in reglas:
        m = rx.search(texto)
        if m:
            errores.append(f"{nombre}: «{m.group(0)}»")
    for nombre, rx in AVISOS + ([SUPERLATIVO] if hablado else []):
        m = rx.search(texto)
        if m:
            avisos.append(f"{nombre}: «{m.group(0)}»")
    for o in oraciones(texto):
        n = len(o.split())
        if n > tope + 2:
            errores.append(f"oración de {n} palabras (tope {tope}): {o[:80]}")
        elif n > tope:
            avisos.append(f"oración de {n} palabras (tope {tope}): {o[:80]}")
    return errores, avisos
