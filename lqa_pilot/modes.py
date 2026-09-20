"""Selectable policies share the same navigator and evidence pipeline."""
import copy
from .util import PilotError

MODES = ("full", "fast", "video")

FAST_RULES = """FAST MODE: perform only the following checks, using a conservative threshold:
1. Visible UI text overflow, clipping, overlap, broken glyphs or other rendering failures affecting readability.
2. Unambiguous typos (wrong/missing letters), not spacing, hyphenation, capitalization preferences or word choice.
3. Terminology inconsistency ONLY against an explicitly supplied nonempty glossary; cite its exact glossary_key.
4. Nonsensical sentences or indisputable grammar errors that materially change/destroy meaning, with no plausible
grammatical/contextual explanation. Understandable but awkward labels or compounds are OUT OF SCOPE.
5. Clearly harmful/reputational language in context, or a breach of supplied market/content rules. Historical
WWII names, quotations, factions and neutral descriptions alone are not bugs. Distinguish portrayal from endorsement.
Do not invent German/Russian legal prohibitions, a forbidden-word list or a claim of illegality. Report a concrete
contextual risk for review, not legal clearance. Apply supplied content_policy and setting; missing policy is not proof.
Ignore minor style, punctuation, spaces, hyphens, harmless unnatural wording and inconsistency without a glossary.
A clear result means clear for THIS FAST SCOPE only. Do not claim a full linguistic/translation/legal review.
Classify each candidate with fast_kind, meaning_impact and glossary_key (empty unless glossary-based).
"""

def glossary_entries(project):
    glossary = project.get("glossary", {})
    if isinstance(glossary, dict) and isinstance(glossary.get("terms"), list):
        glossary = glossary["terms"]
    if isinstance(glossary, list):
        return {str(e.get("id") or e.get("source")): e for e in glossary
                if isinstance(e, dict) and (e.get("id") or e.get("source")) and e.get("target")}
    if isinstance(glossary, dict):
        return {str(k): v for k, v in glossary.items() if v and k not in {"notes", "source", "description"}}
    return {}

def apply_mode(project, mode=None):
    p = copy.deepcopy(project)
    selected = mode or p.get("mode", "full")
    if selected not in MODES:
        raise PilotError("Modalità non valida: scegliere full, fast o video")
    p["mode"] = selected
    p["report_language"] = "English"
    from .codex import DEFAULT_MODELS
    models = p.setdefault("codex", {}).setdefault("models", {})
    for role, default in DEFAULT_MODELS.items():
        models[role] = {**default, **models.get(role, {})}
    # All three modes keep the same navigator/model and movement recovery.
    if selected == "fast":
        for role in ("analyze", "verify", "audit"):
            models[role]["reasoning"] = "low"
    if selected == "video":
        models["audit"]["reasoning"] = "low"
    return p

def fast_allowed(candidate, project):
    kind = candidate.get("fast_kind")
    if kind == "ui_layout":
        return True
    if kind == "glossary":
        return candidate.get("glossary_key") in glossary_entries(project)
    if kind == "reputation":
        return bool(candidate.get("meaning_impact"))
    # Pure whitespace/hyphen/punctuation/case changes cannot masquerade as typos.
    letters = lambda s: "".join(c.casefold() for c in s if c.isalnum())
    if letters(candidate.get("observed", "")) == letters(candidate.get("expected", "")):
        return False
    if kind == "typo":
        return True
    return kind in {"nonsense", "meaning_grammar"} and candidate.get("meaning_impact") is True
