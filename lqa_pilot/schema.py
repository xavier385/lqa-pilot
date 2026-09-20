"""Small explicit schemas shared by Codex structured output and local validation."""
import math
from .util import PilotError


def obj(**props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items}


S = {"type": "string"}
B = {"type": "boolean"}
N = {"type": "number"}


def enum(*values):
    return {"type": "string", "enum": list(values)}


BBOX = obj(x=N, y=N, width=N, height=N)
CHECK = obj(id=S, scope=S, instruction=S, modality=enum("visual", "audio", "source"))
CASE = obj(id=S, title=S, objective=S, journey=arr(S), checks=arr(CHECK))
PLAN = obj(cases=arr(CASE), assumptions=arr(S), material_gaps=arr(S))
ACTION = obj(kind=enum("tap", "swipe", "long_press", "back", "wait", "type_text", "inspect", "finish", "blocked"),
             x=N, y=N, x2=N, y2=N, duration_ms=N, text=S,
             target=S, expected_change=S, risk=enum("navigation", "game_progress", "spend", "account", "communication", "privacy"))
NAV = obj(screen_name=S, visible_text=arr(S), observed_scopes=arr(S),
          uncovered_areas=arr(S), inspect_checks=arr(S), action=ACTION,
          rationale=S, blocker=S)
FINDING = obj(check_id=S, taxonomy_id=S, evidence_id=S, bbox=BBOX,
              observed=S, expected=S, explanation=S, confidence=N)
ANALYSIS = obj(checks=arr(obj(check_id=S, status=enum("clear", "issue", "unreadable", "not_observed"),
                            evidence_ids=arr(S), explanation=S)), candidates=arr(FINDING),
               transcriptions=arr(obj(evidence_id=S, text=S)))
VERIFY = obj(verdict=enum("confirmed", "rejected", "uncertain"),
             observed=S, expected=S, explanation=S, report_comment={"type": "string", "maxLength": 220}, confidence=N)
FAST_FINDING = obj(**FINDING["properties"], fast_kind=enum("ui_layout", "typo", "glossary", "nonsense", "meaning_grammar", "reputation", "minor_style"), meaning_impact=B, glossary_key=S)
FAST_ANALYSIS = obj(**{**ANALYSIS["properties"], "candidates": arr(FAST_FINDING)})
FAST_VERIFY = obj(**VERIFY["properties"], fast_eligible=B)
AUDIT = obj(checks=arr(obj(check_id=S, covered=B, explanation=S)),
            scope_complete=B, missing_areas=arr(S), explanation=S)


def validate(value, schema, path="$"):
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool,
             "number": (int, float)}
    if kind and (not isinstance(value, types[kind]) or (kind == "number" and isinstance(value, bool))):
        raise PilotError(f"JSON non valido {path}: atteso {kind}")
    if kind == "number" and not math.isfinite(value):
        raise PilotError(f"Numero non finito: {path}")
    if kind == "string" and "maxLength" in schema and len(value) > schema["maxLength"]:
        raise PilotError(f"Testo troppo lungo {path}: massimo {schema['maxLength']} caratteri")
    if "enum" in schema and value not in schema["enum"]:
        raise PilotError(f"Valore non ammesso {path}: {value}")
    if kind == "object":
        props = schema["properties"]
        if set(value) != set(props):
            raise PilotError(f"Campi JSON errati in {path}: {set(value) ^ set(props)}")
        for k, sub in props.items():
            validate(value[k], sub, f"{path}.{k}")
    if kind == "array":
        for i, entry in enumerate(value):
            validate(entry, schema["items"], f"{path}[{i}]")
    return value
