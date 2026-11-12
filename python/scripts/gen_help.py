"""Regenerate web/src/lib/help.ts from coilcal/gui/help.py: uv run python scripts/gen_help.py"""

import json
from pathlib import Path

from coilcal.gui.help import GUIDE_HTML, TAB_TIPS, TIPS


def dump(x: object) -> str:
    return json.dumps(x, ensure_ascii=False, indent=2)


guide = GUIDE_HTML.strip().replace("<h2>", '<h2 id="guide-title">', 1)
out = Path(__file__).parents[2] / "web/src/lib/help.ts"
out.write_text(
    "// Tooltips and the guide, generated from coilcal/gui/help.py by python/scripts/gen_help.py.\n"
    "// Edit help.py and regenerate; do not edit by hand.\n\n"
    f"export const TIPS: Record<string, string> = {dump(TIPS)};\n\n"
    f"export const TAB_TIPS: Record<string, string> = {dump(TAB_TIPS)};\n\n"
    '/** The F1 guide (trusted HTML from help.py); its <h2> has id="guide-title". */\n'
    f"export const GUIDE_HTML = {json.dumps(guide, ensure_ascii=False)};\n"
)
