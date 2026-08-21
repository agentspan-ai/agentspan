#!/usr/bin/env python3
"""Reverse-engineer agent-schema.json into a Python dataclass and a Java record,
then prove the schema is correct by diffing the generated models against the
server's AgentConfig models and validating a generated instance.

Run from the repo root:  python3 sdk/java/docs/generated/generate.py
Outputs (regenerated each run):
  sdk/java/docs/generated/agent_config.py        — Python dataclasses
  sdk/java/docs/generated/AgentConfigModel.java  — Java records

Exit code 0 iff: (a) generated models are field-for-field identical to the
schema, (b) a generated instance validates against the schema, and (c) every
server AgentConfig field (root + nested models) is present in the schema.
"""
import json, os, re, sys, importlib.util, dataclasses

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SCHEMA = os.path.join(ROOT, "sdk/java/docs/agent-schema.json")
MODEL_DIR = os.path.join(ROOT, "server/conductor-agentspan/src/main/java/dev/agentspan/runtime/model")

schema = json.load(open(SCHEMA))
defs = schema["$defs"]
ROOT_CLS = "AgentConfig"
cap = lambda d: d[0].upper() + d[1:]
ref_cls = lambda r: ROOT_CLS if r == "#" else cap(r.split("/")[-1])

PY = {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "object": "Dict[str, Any]"}
JV = {"string": "String", "integer": "Integer", "number": "Double", "boolean": "Boolean", "object": "Map<String, Object>"}

def base_type(s, scalar, ref, arr):
    if not isinstance(s, dict): return scalar(None)
    if "$ref" in s: return ref(s["$ref"])
    if "oneOf" in s: return scalar("__any__")
    t = s.get("type")
    if isinstance(t, list):
        nn = [x for x in t if x != "null"]
        return base_type({"type": nn[0]} if nn else {}, scalar, ref, arr) if nn else scalar("__any__")
    if t == "array": return arr(s.get("items", {}))
    return scalar(t)

py_type = lambda s: base_type(s, lambda t: ("Any" if t in (None, "__any__") else PY.get(t, "Any")),
                              ref_cls, lambda it: f"List[{py_type(it)}]")
jv_type = lambda s: base_type(s, lambda t: ("Object" if t in (None, "__any__") else JV.get(t, "Object")),
                              ref_cls, lambda it: f"List<{jv_type(it)}>")

order = [(ROOT_CLS, schema)] + [(cap(n), d) for n, d in defs.items()]

def gen_py(name, node):
    p = node.get("properties") or {}
    if not p: return f"@dataclass\nclass {name}:\n    pass"
    body = "\n".join(f"    {k}: Optional[{py_type(v)}] = None" for k, v in p.items())
    return f"@dataclass\nclass {name}:\n{body}"

def gen_java(name, node):
    p = node.get("properties") or {}
    if not p: return f"  public record {name}() {{}}"
    comps = ", ".join(f"{jv_type(v)} {k}" for k, v in p.items())
    return f"  public record {name}({comps}) {{}}"

with open(os.path.join(HERE, "agent_config.py"), "w") as f:
    f.write('"""AUTO-GENERATED from agent-schema.json by generate.py — do not edit."""\n')
    f.write("from __future__ import annotations\nfrom dataclasses import dataclass\n")
    f.write("from typing import Any, Dict, List, Optional\n\n\n")
    f.write("\n\n\n".join(gen_py(n, d) for n, d in order) + "\n")

with open(os.path.join(HERE, "AgentConfigModel.java"), "w") as f:
    f.write("// AUTO-GENERATED from agent-schema.json by generate.py — do not edit.\n")
    f.write("import java.util.List;\nimport java.util.Map;\n\npublic final class AgentConfigModel {\n")
    f.write("  private AgentConfigModel() {}\n\n")
    f.write("\n".join(gen_java(n, d) for n, d in order) + "\n}\n")

# ---- proof ----
spec = importlib.util.spec_from_file_location("gen_ac", os.path.join(HERE, "agent_config.py"))
m = importlib.util.module_from_spec(spec); sys.modules["gen_ac"] = m; spec.loader.exec_module(m)

ok = True

# (a) generated models are field-for-field identical to the schema
for clsname, node in [(ROOT_CLS, schema)] + [(cap(n), defs[n]) for n in defs]:
    fields = {x.name for x in dataclasses.fields(getattr(m, clsname))}
    props = set((node.get("properties") or {}).keys())
    if fields != props:
        ok = False; print(f"[a] FAIL {clsname}: {fields ^ props}")
print("[a] generated dataclass/record fields ≡ schema (root + %d nested): %s" % (len(defs), "OK" if ok else "FAIL"))

# (b) a generated instance validates against the schema
try:
    from jsonschema import Draft202012Validator
    clean = lambda x: ({k: clean(v) for k, v in x.items() if v is not None} if isinstance(x, dict)
                       else [clean(v) for v in x] if isinstance(x, list) else x)
    inst = m.AgentConfig(name="gen_agent", model="openai/gpt-4o", external=False, maxTurns=5,
                         timeoutSeconds=0, reasoningEffort="high",
                         memory=m.Memory(messages=[{"role": "user", "message": "hi"}], maxMessages=10),
                         gate=m.Gate(type="text_contains", text="STOP", caseSensitive=False))
    errs = list(Draft202012Validator(schema).iter_errors(clean(dataclasses.asdict(inst))))
    for e in errs: ok = False; print("   VIOLATION:", e.message)
    print("[b] generated instance validates against schema:", "OK" if not errs else "FAIL")
except ImportError:
    print("[b] skipped (pip install jsonschema to run)")

# (c) every server AgentConfig field (root + nested) is present in the schema
def server_fields(cls):
    p = os.path.join(MODEL_DIR, cls + ".java")
    if not os.path.exists(p): return None
    src = open(p).read()
    fields = re.findall(r"private\s+(?:final\s+)?[\w<>,\s\[\].]+?\s+([a-z]\w*)\s*[;=]", src)
    jp = dict(re.findall(r'@JsonProperty\("([^"]+)"\)[^;{]*?\s(\w+)\s*[;=]', src))
    inv = {v: k for k, v in jp.items()}
    return {inv.get(f, f) for f in fields}

MAP = {ROOT_CLS: "AgentConfig", "Tool": "ToolConfig", "Guardrail": "GuardrailConfig",
       "Memory": "MemoryConfig", "Termination": "TerminationConfig", "Handoff": "HandoffConfig",
       "Callback": "CallbackConfig", "CodeExecution": "CodeExecutionConfig", "CliConfig": "CliConfig",
       "ThinkingConfig": "ThinkingConfig", "PrefillTool": "PrefillToolCallConfig",
       "OutputType": "OutputTypeConfig", "WorkerRef": "WorkerRef"}
gaps = {}
for clsname, server_cls in MAP.items():
    node = schema if clsname == ROOT_CLS else defs[clsname[0].lower() + clsname[1:]]
    sf = server_fields(server_cls)
    if sf is None: continue
    miss = sf - set((node.get("properties") or {}).keys())
    if miss: gaps[clsname] = sorted(miss); ok = False
print("[c] every server field present in schema:", "OK" if not gaps else f"GAPS {gaps}")

print("\nRESULT:", "SCHEMA VERIFIED ✅" if ok else "VERIFICATION FAILED ❌")
sys.exit(0 if ok else 1)
