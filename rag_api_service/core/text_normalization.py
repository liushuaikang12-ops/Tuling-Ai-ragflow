from __future__ import annotations

import re


# Word/PDF documents created with SymbolMT commonly expose the original
# one-byte Symbol encoding as Unicode private-use characters (U+F0xx).
# Browsers render those code points as tofu boxes even though the low byte
# still identifies the intended Greek or mathematical glyph.
# Keep the table explicit.  Besides being easier to audit, this avoids
# assuming that every private-use code point belongs to SymbolMT.
_SYMBOL_PUA_MAP = {
    "\uf041": "Α", "\uf042": "Β", "\uf043": "Χ", "\uf044": "Δ",
    "\uf045": "Ε", "\uf046": "Φ", "\uf047": "Γ", "\uf048": "Η",
    "\uf049": "Ι", "\uf04a": "ϑ", "\uf04b": "Κ", "\uf04c": "Λ",
    "\uf04d": "Μ", "\uf04e": "Ν", "\uf04f": "Ο", "\uf050": "Π",
    "\uf051": "Θ", "\uf052": "Ρ", "\uf053": "Σ", "\uf054": "Τ",
    "\uf055": "Υ", "\uf056": "ς", "\uf057": "Ω", "\uf058": "Ξ",
    "\uf059": "Ψ", "\uf05a": "Ζ",
    # Lower-case Greek letters.
    "\uf061": "α", "\uf062": "β", "\uf063": "χ", "\uf064": "δ",
    "\uf065": "ε", "\uf066": "φ", "\uf067": "γ", "\uf068": "η",
    "\uf069": "ι", "\uf06a": "ϕ", "\uf06b": "κ", "\uf06c": "λ",
    "\uf06d": "μ", "\uf06e": "ν", "\uf06f": "ο", "\uf070": "π",
    "\uf071": "θ", "\uf072": "ρ", "\uf073": "σ", "\uf074": "τ",
    "\uf075": "υ", "\uf076": "ϖ", "\uf077": "ω", "\uf078": "ξ",
    "\uf079": "ψ", "\uf07a": "ζ",
    # Relations, operators, arrows, and set symbols used in equations.
    "\uf022": "∀", "\uf024": "∃", "\uf027": "∋", "\uf03c": "<",
    "\uf03e": ">", "\uf040": "≅",
    "\uf05c": "∴", "\uf05e": "⊥", "\uf07e": "∼", "\uf0a3": "≤",
    "\uf0a5": "∞", "\uf0ab": "↔", "\uf0ac": "←", "\uf0ad": "↑",
    "\uf0ae": "→", "\uf0af": "↓", "\uf0b1": "±", "\uf0b3": "≥",
    "\uf0b4": "×", "\uf0b5": "∝", "\uf0b6": "∂", "\uf0b7": "•",
    "\uf0b8": "÷", "\uf0b9": "≠", "\uf0ba": "≡", "\uf0bb": "≈",
    "\uf0bc": "…", "\uf0c4": "⊗", "\uf0c5": "⊕", "\uf0c6": "∅",
    "\uf0c7": "∩", "\uf0c8": "∪", "\uf0c9": "⊃", "\uf0ca": "⊇",
    "\uf0cb": "⊄", "\uf0cc": "⊂", "\uf0cd": "⊆", "\uf0ce": "∈",
    "\uf0cf": "∉", "\uf0d0": "∠", "\uf0d1": "∇", "\uf0d5": "∏",
    "\uf0d6": "√", "\uf0d7": "⋅", "\uf0d8": "¬", "\uf0d9": "∧",
    "\uf0da": "∨", "\uf0db": "⇔", "\uf0dc": "⇐", "\uf0dd": "⇑",
    "\uf0de": "⇒", "\uf0df": "⇓", "\uf0e5": "∑", "\uf0f2": "∫",
    # Multi-part brackets from SymbolMT are flattened to readable delimiters.
    "\uf0e6": "(", "\uf0e7": "", "\uf0e8": ")", "\uf0e9": "[",
    "\uf0ea": "", "\uf0eb": "]", "\uf0ec": "{", "\uf0ed": "",
    "\uf0ee": "}", "\uf0ef": "", "\uf0f3": "∫", "\uf0f4": "∫",
    "\uf0f5": "∫", "\uf0f6": "(", "\uf0f7": "", "\uf0f8": ")",
    "\uf0f9": "[", "\uf0fa": "", "\uf0fb": "]", "\uf0fc": "{",
    "\uf0fd": "", "\uf0fe": "}",
}

_PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")


def normalize_pdf_symbol_text(text: str) -> str:
    """Convert known SymbolMT private-use glyphs into standard Unicode.

    Unknown private-use characters are retained: silently deleting them could
    change the mathematical meaning, while leaving them visible makes the
    remaining parser defect observable.
    """

    if not text or not _PRIVATE_USE_RE.search(text):
        return text
    return "".join(_SYMBOL_PUA_MAP.get(character, character) for character in text)
