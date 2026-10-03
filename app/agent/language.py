"""Deterministic EN / ES language detection (decision C3-12 B).

The Agent answers in the language of the question. Detection is a transparent
heuristic, not a model: Spanish-only characters, then counts of very common
words in each language. A message without language signals (for example just
"EMP024") keeps the language of the session.
"""

from __future__ import annotations

import re
from typing import Literal

Language = Literal["en", "es"]

_SPANISH_CHARS = re.compile(r"[¿¡ñáéíóú]", re.IGNORECASE)
_WORD = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)

_ES_WORDS = frozenset(
    "el la los las de del que qué por porque cuál cual cuáles cuántos cuantos cuántas cuantas "
    "es está esta están fue un una unos para con sin pero cómo como dónde donde quién quien "
    "empleado empleados nómina nomina proceso diferencia falló fallo fallaron pasó paso "
    "excepción excepciones tolerancia neto bruto deducciones aprobación aprobar hay "
    "mi tu su sus se lo le al y o tiene tienen puede puedo puedes dime muestra cuál".split()
)
_EN_WORDS = frozenset(
    "the is are was were what why how which who did does do a an of for with to "
    "employee employees payroll process difference failed fail pass passed exception "
    "exceptions tolerance net gross deductions approval approve there my your can "
    "show tell me and or it this that".split()
)


def detect_language(text: str, default: Language = "en") -> Language:
    if _SPANISH_CHARS.search(text):
        return "es"
    words = [w.lower() for w in _WORD.findall(text)]
    es = sum(w in _ES_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    if es > en:
        return "es"
    if en > es:
        return "en"
    return default
