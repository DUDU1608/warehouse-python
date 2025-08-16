from functools import lru_cache
import re

# Optional online translator
try:
    from deep_translator import GoogleTranslator
    _gt = GoogleTranslator(source="auto", target="hi")
except Exception:
    _gt = None

# --- Domain overrides (lowercase keys). Add more as needed. ---
OVERRIDES = {
    "putul": "पुतुल",
    "warehouse": "गोदाम",
    "agro": "एग्रो",
    "shree": "श्री",
    "anunay": "अनुनय",
    "seller": "सेलर",
    "stockist": "स्टॉकिस्ट",
    "loan": "लोन",
    "payment": "पेमेंट",
    "purchase": "परचेज",
    "company": "कंपनी",
    "wheat": "गेहूं",
    "maize": "मक्का",
    "bimal": "बिमल",
    "kumari": "कुमारी",
    "Cash": "नकद",
    "margin": "भंडार"
}

_ASCII_RE = re.compile(r"[A-Za-z]")

def _looks_latin(s: str) -> bool:
    return bool(_ASCII_RE.search(s or ""))

@lru_cache(maxsize=4096)
def to_hindi_name(value: str) -> str:
    if not value:
        return value

    # Tokenize into words/non-words so we can apply overrides per word
    tokens = re.findall(r"[A-Za-z]+|\d+|[^\sA-Za-z\d]+|\s+", value)
    out_parts = []
    for tok in tokens:
        if tok.isalpha():  # word made of letters
            lower = tok.lower()
            # 1) Exact override hit?
            if lower in OVERRIDES:
                out_parts.append(OVERRIDES[lower])
                continue
            # 2) Try online translator once per word
            if _gt is not None:
                try:
                    gt = _gt.translate(tok)
                    if gt and gt.strip() and not _looks_latin(gt):
                        out_parts.append(gt)
                        continue
                except Exception:
                    pass
            # 3) Fallback phonetic (very light)
            out_parts.append(_phonetic_word(lower))
        else:
            out_parts.append(tok)
    return "".join(out_parts)

def _phonetic_word(w: str) -> str:
    # Very minimal fallback: helps for simple syllables,
    # but rely on OVERRIDES for business terms / names.
    t = w
    # common digraphs
    for a, b in [
        ("sh", "श"), ("chh", "छ"), ("ch", "च"),
        ("kh", "ख"), ("gh", "घ"), ("th", "थ"), ("dh", "ध"),
        ("ph", "फ"), ("bh", "भ"), ("wh", "व"), ("qu", "क्व"),
    ]:
        t = t.replace(a, b)

    # quick vowel groups
    for a, b in [("aa", "आ"), ("ee", "ई"), ("oo", "ऊ"), ("ai", "ऐ"), ("au", "औ")]:
        t = t.replace(a, b)

    # singles (rough)
    t = (t.replace("a", "अ").replace("e", "ए").replace("i", "इ")
           .replace("o", "ओ").replace("u", "उ"))

    # consonants
    cons = {
        "k":"क","g":"ग","c":"क","j":"ज","t":"त","d":"द","n":"न",
        "p":"प","b":"ब","m":"म","y":"य","r":"र","l":"ल","v":"व","w":"व",
        "s":"स","h":"ह","q":"क","x":"क्स","z":"ज़","f":"फ",
    }
    return "".join(cons.get(ch, ch) for ch in t)
