"""Turn the CAA's upper-case names into readable ones."""
from __future__ import annotations

import re

KEEP_UPPER = {"UK", "TUI", "KLM", "SAS", "TAP", "LOT", "BA", "USA", "UAE", "JFK", "AG", "AS", "AB", "AOC", "THY"}


WORD_FIXES = {"GMBH": "GmbH", "JETBLUE": "JetBlue", "SUNEXPRESS": "SunExpress", "DBA": "DBA",
              "EASYJET": "easyJet", "LTD": "Ltd", "PLC": "plc"}
SPECIAL_NAMES = {"EASYJET": "easyJet", "EASYJET UK LTD": "easyJet UK Ltd", "JET2.COM": "Jet2.com",
                 "JET2.COM LTD": "Jet2.com Ltd"}


def title_case(name: str) -> str:
    """'BRITISH AIRWAYS' -> 'British Airways', keeping known acronyms upper case."""
    name = str(name)
    if name in SPECIAL_NAMES:
        return SPECIAL_NAMES[name]
    words = []
    for word in name.title().split():
        core = re.sub(r"[^A-Za-z]", "", word).upper()
        if core in WORD_FIXES:
            word = word.replace(word.strip("()"), WORD_FIXES[core]) if word.strip("()").upper() == core else word
        elif core in KEEP_UPPER:
            word = word.upper()
        words.append(word)
    return " ".join(words)
