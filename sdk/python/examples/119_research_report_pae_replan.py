#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""119 — Research report: Plan-Execute-Review-Replan loop as one Conductor execution.

A research report is generated iteratively inside a single Conductor workflow.
The loop body — plan, compile, execute (parallel writes), quality check, replan —
runs entirely server-side. There is ONE execution ID for all iterations.

The loop:
    iteration N
    ├── planner LLM   — reads quality state, decides which sections to write/rewrite
    ├── INLINE        — extract sections_to_write from LLM response
    ├── INLINE        — build PAC plan: parallel generate ops for each failing section
    │                   + sequential check_quality step
    ├── PLAN_AND_COMPILE — PAC compiles to WorkflowDef (FORK_JOIN writes + check)
    ├── SUB_WORKFLOW  — Conductor executes: sections written in parallel, then checked
    ├── INLINE        — extract quality verdict (quality_passed bool + per-section detail)
    └── SET_VARIABLE  — persist quality report to workflow.variables for iteration N+1

Key properties:
  - ONE workflow ID across all iterations.
  - Tasks appear as planner_llm__1, plan_and_compile__1, plan_exec__1,
    planner_llm__2, ... in the Conductor UI.
  - Passing sections are NOT rewritten. Only failing sections get new generate ops.
  - quality check is 100% deterministic (word count + topic presence) — no LLM judge.

What you will see in the UI:
  http://localhost:6767/execution/<id>
  → All iterations under one workflow ID.
  → FORK_JOIN branches for parallel section writes inside each sub-workflow.
  → Quality improvements iteration by iteration.

Requirements:
  - agentspan server start
  - export OPENAI_API_KEY=sk-...  (or ANTHROPIC_API_KEY)
  - uv run python3 119_research_report_pae_replan.py "AI agents in production"
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time

import requests

from conductor.ai.agents import AgentRuntime, plan_execute, tool

SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
BASE = SERVER_URL.rstrip("/").replace("/api", "")
MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "openai/gpt-4o-mini")
MAX_ITER = int(os.environ.get("REPORT_MAX_ITER", "5"))
WORKFLOW_NAME = "research_report_pae_replan"
WORKFLOW_VERSION = 3
WORK_DIR = os.path.join(tempfile.gettempdir(), "report_pae_replan")

# Report structure — the quality gate checks these per section.
# min_words chosen to require ~1 replan for a typical LLM first attempt.
SECTIONS = [
    {
        "id": "introduction",
        "title": "Introduction",
        "min_words": 120,
        "required_topics": ["agent", "production"],
    },
    {
        "id": "architecture",
        "title": "Technical Architecture",
        "min_words": 180,
        "required_topics": ["execution", "workflow", "durable"],
    },
    {
        "id": "conclusion",
        "title": "Conclusion and Future Work",
        "min_words": 80,
        "required_topics": ["benefit", "future"],
    },
]

SECTION_LIST_TEXT = "\n".join(
    f"  - {s['id']}: {s['title']} "
    f"(min {s['min_words']} words, required topics: {', '.join(s['required_topics'])})"
    for s in SECTIONS
)


def _model_split(model: str) -> tuple[str, str]:
    if "/" in model:
        p, n = model.split("/", 1)
        return p, n
    return "openai", model


PROVIDER, MODEL_NAME = _model_split(MODEL)


# ── Tools ─────────────────────────────────────────────────────────────────────


@tool
def write_section(section_id: str, title: str, content: str) -> str:
    """Write one report section to disk.

    Called by PAC via a ``generate`` op: the LLM produces
    ``{"section_id": "...", "title": "...", "content": "..."}`` and PAC
    templates those fields into the args for this tool.
    """
    os.makedirs(WORK_DIR, exist_ok=True)
    path = os.path.join(WORK_DIR, f"{section_id}.md")
    with open(path, "w") as f:
        f.write(f"## {title}\n\n{content}\n")
    words = len(content.split())
    return f"wrote {words} words to {section_id}.md"


@tool
def check_quality(report_dir: str) -> dict:
    """Read all section files and verify word count + required topics.

    100% deterministic — no LLM involved. Returns a structured verdict
    so the planner knows exactly what failed and what to fix next.
    """
    section_specs = {s["id"]: s for s in SECTIONS}
    results: dict = {}
    all_passed = True

    for section_id, spec in section_specs.items():
        path = os.path.join(report_dir, f"{section_id}.md")
        if not os.path.exists(path):
            results[section_id] = {
                "passed": False,
                "words": 0,
                "missing_topics": spec["required_topics"],
                "needed_words": spec["min_words"],
                "status": "not yet written",
            }
            all_passed = False
            continue

        with open(path) as f:
            content = f.read()

        words = len(content.split())
        lower = content.lower()
        missing = [t for t in spec["required_topics"] if t.lower() not in lower]
        passed = (words >= spec["min_words"]) and (not missing)
        if not passed:
            all_passed = False

        results[section_id] = {
            "passed": passed,
            "words": words,
            "needed_words": spec["min_words"],
            "missing_topics": missing,
        }

    return {"result": {"quality_passed": all_passed, "sections": results}}


# ── GraalJS INLINE scripts ─────────────────────────────────────────────────────
#
# Conductor INLINE tasks run GraalJS. Their inputs arrive as Java Maps/Lists,
# not JS objects — JSON.stringify on a Java Map returns {} because Map fields
# don't enumerate. toJSObj() unwraps them recursively before serialization.
# Every INLINE that touches task output must call toJSObj() first.

_TO_JS_OBJ = (
    "function toJSObj(v){"
    "  if(v===null||v===undefined)return v;"
    "  if(typeof v!=='object')return v;"
    "  if(typeof v.keySet==='function'&&typeof v.get==='function'){"
    "    var o={};var it=v.keySet().iterator();"
    "    while(it.hasNext()){var k=it.next();o[String(k)]=toJSObj(v.get(k));}"
    "    return o;"
    "  }"
    "  if(typeof v.iterator==='function'&&typeof v.size==='function'"
    "    &&typeof v.keySet!=='function'){"
    "    var a=[];var li=v.iterator();while(li.hasNext())a.push(toJSObj(li.next()));return a;"
    "  }"
    "  if(Array.isArray(v))return v.map(toJSObj);"
    "  var ks=Object.keys(v);var o2={};"
    "  for(var i=0;i<ks.length;i++)o2[ks[i]]=toJSObj(v[ks[i]]);"
    "  return o2;"
    "}"
)

# Pull sections_to_write array from the planner LLM's JSON response.
EXTRACT_PLAN_JS = _TO_JS_OBJ + (
    "(function(){"
    "  var r=$.llm_out;"
    "  if(r===null||r===undefined)return [];"
    "  var obj;"
    "  if(typeof r==='object'){obj=toJSObj(r);}"
    "  else{"
    "    var s=String(r);var m=s.match(/\\{[\\s\\S]*\\}/);"
    "    if(!m)return [];try{obj=JSON.parse(m[0]);}catch(e){return [];}"
    "  }"
    "  var st=obj.sections_to_write;"
    "  if(!st&&obj.result)st=obj.result.sections_to_write;"
    "  if(!st)return [];"
    "  return Array.isArray(st)?st:toJSObj(st);"
    "})();"
)

# Build a PAC plan JSON from the sections_to_write list.
# Each section becomes a `generate` op (LLM writes content) for write_section.
# The final step is a deterministic check_quality call.
# work_dir is injected via $.work_dir from the task's inputParameters.
BUILD_PAC_PLAN_JS = _TO_JS_OBJ + (
    "(function(){"
    "  var wd=$.work_dir;"
    "  var raw=$.sections_to_write;"
    "  var arr;"
    "  if(raw===null||raw===undefined){arr=[];}"
    "  else if(Array.isArray(raw)){arr=raw.map(toJSObj);}"
    "  else if(typeof raw==='object'){arr=toJSObj(raw);if(!Array.isArray(arr))arr=[];}"
    "  else{try{arr=JSON.parse(String(raw));}catch(e){arr=[];}}"
    "  var ops=[];"
    "  for(var i=0;i<arr.length;i++){"
    "    var s=toJSObj(arr[i]);"
    "    var topics=Array.isArray(s.required_topics)?s.required_topics.join(', '):String(s.required_topics||'');"
    "    var instr='Write the section titled \"'+(s.title||s.id)+'\" for a research report on the given topic. '"
    "      +'Write AT LEAST '+(s.min_words||100)+' words. '"
    "      +'You MUST explicitly mention these topics in the text: '+topics+'. '"
    "      +(s.instructions||'');"
    "    ops.push({"
    "      tool:'write_section',"
    "      generate:{"
    "        instructions:instr,"
    "        output_schema:JSON.stringify({section_id:s.id||'',title:s.title||'',content:'...'})"
    "      }"
    "    });"
    "  }"
    "  if(ops.length===0){"
    "    ops.push({tool:'write_section',generate:{"
    "      instructions:'Write a brief placeholder.',"
    "      output_schema:JSON.stringify({section_id:'placeholder',title:'Placeholder',content:'...'})"
    "    }});"
    "  }"
    "  var plan={"
    "    steps:["
    "      {id:'write_sections',parallel:true,operations:ops},"
    "      {id:'check',depends_on:['write_sections'],operations:["
    "        {tool:'check_quality',args:{report_dir:wd}}"
    "      ]}"
    "    ]"
    "  };"
    "  return JSON.stringify(plan);"
    "})();"
)

# Serialize quality result to a JSON string for storage in workflow.variables.
# Conductor substitutes workflow.variables.* into LLM prompts as-is — if the
# value is a Java Map object, it renders as Java toString() (not JSON), which
# confuses the planner LLM. Storing it as a JSON string ensures the LLM sees
# proper JSON in every iteration.
SERIALIZE_STATE_JS = _TO_JS_OBJ + (
    "(function(){"
    "  var r=$.quality_result;"
    "  if(!r)return '{}';"
    "  return JSON.stringify(toJSObj(r));"
    "})();"
)

# Extract quality_passed + sections detail from the compiled sub-workflow output.
EXTRACT_QUALITY_JS = _TO_JS_OBJ + (
    "(function(){"
    "  var ex=$.exec_output;"
    "  if(!ex)return {quality_passed:false,error:'no exec output'};"
    "  var result=ex.result;"
    "  if(result&&typeof result==='object')return toJSObj(result);"
    "  if(typeof result==='string'){try{return JSON.parse(result);}catch(e){}}"
    "  return {quality_passed:false,error:'unparseable result'};"
    "})();"
)


# ── Planner prompts ────────────────────────────────────────────────────────────

PLANNER_SYSTEM = (
    "You are a research report writer. Your job is to write sections of a multi-section "
    "technical report, iterating until all sections pass quality checks.\n\n"
    "Each iteration:\n"
    "  1. Review the quality report to see which sections passed and which failed.\n"
    "  2. Plan to write ONLY the sections that need work:\n"
    "     - If quality_report is empty (first iteration): include ALL sections.\n"
    "     - Otherwise: include ONLY sections where 'passed' is false.\n"
    "  3. For failing sections, add specific instructions on what to improve.\n\n"
    "IMPORTANT: Do NOT include sections that already passed.\n\n"
    f"Available sections:\n{SECTION_LIST_TEXT}\n\n"
    "Output ONLY a JSON object — no prose, no markdown fences:\n"
    "{\n"
    '  "sections_to_write": [\n'
    "    {\n"
    '      "id": "section_id",\n'
    '      "title": "Section Title",\n'
    '      "min_words": 150,\n'
    '      "required_topics": ["topic1", "topic2"],\n'
    '      "instructions": "specific improvement guidance based on the failure"\n'
    "    }\n"
    "  ]\n"
    "}"
)

PLANNER_USER = (
    "Research topic: ${workflow.input.topic}\n\n"
    "Quality report from last iteration:\n${workflow.variables.report_state}\n\n"
    "Iteration: ${loop.output.iteration}\n\n"
    "Instructions:\n"
    "- If quality report is empty or {}: list ALL sections.\n"
    "- Otherwise: list ONLY sections where 'passed' is false.\n"
    "- For each failed section, set instructions to explicitly address the failure "
    "(e.g. 'Previous attempt had X words, write at least Y. Ensure you mention: topic1, topic2.').\n"
    "- If sections_to_write is empty but quality_passed is not true, list ALL sections again."
)


# ── Workflow definition ────────────────────────────────────────────────────────


def build_workflow_def(tool_defs: list[dict]) -> dict:
    known_tool_names = [t["name"] for t in tool_defs]

    return {
        "name": WORKFLOW_NAME,
        "version": WORKFLOW_VERSION,
        "description": (
            "Research report PAE-replan loop — "
            "plan → PAC compile → parallel section writes → quality check → replan, "
            "all inside one DO_WHILE as a single execution."
        ),
        "tasks": [
            # ── Init ────────────────────────────────────────────────────────
            {
                "name": "SET_VARIABLE",
                "taskReferenceName": "init",
                "type": "SET_VARIABLE",
                "inputParameters": {
                    "report_state": {},
                    "topic": "${workflow.input.topic}",
                },
            },
            # ── DO_WHILE loop ────────────────────────────────────────────────
            {
                "name": "DO_WHILE",
                "taskReferenceName": "loop",
                "type": "DO_WHILE",
                "inputParameters": {
                    "loop": "${loop}",
                    "extract_quality": "${extract_quality}",
                },
                "loopCondition": (
                    f"if ($.loop['iteration'] < {MAX_ITER} "
                    f"&& $.extract_quality['result']['quality_passed'] != true) "
                    f"{{ true; }} else {{ false; }}"
                ),
                "loopOver": [
                    # 1. Planner LLM: which sections to write this iteration
                    {
                        "name": "LLM_CHAT_COMPLETE",
                        "taskReferenceName": "planner_llm",
                        "type": "LLM_CHAT_COMPLETE",
                        "inputParameters": {
                            "llmProvider": PROVIDER,
                            "model": MODEL_NAME,
                            "maxTokens": 1000,
                            "messages": [
                                {"role": "system", "message": PLANNER_SYSTEM},
                                {"role": "user", "message": PLANNER_USER},
                            ],
                        },
                    },
                    # 2. Extract sections_to_write array from LLM response
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_plan",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_PLAN_JS,
                            "llm_out": "${planner_llm.output.result}",
                        },
                    },
                    # 3. Build PAC plan JSON: parallel generate ops + check_quality
                    {
                        "name": "INLINE",
                        "taskReferenceName": "build_pac_plan",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": BUILD_PAC_PLAN_JS,
                            "sections_to_write": "${extract_plan.output.result}",
                            "work_dir": "${workflow.input.work_dir}",
                        },
                    },
                    # 4. PAC compiles the plan to a Conductor WorkflowDef
                    {
                        "name": "plan_and_compile",
                        "taskReferenceName": "plan_and_compile",
                        "type": "PLAN_AND_COMPILE",
                        "inputParameters": {
                            "planJson": "${build_pac_plan.output.result}",
                            "parentName": WORKFLOW_NAME,
                            "model": MODEL,
                            "knownToolNames": known_tool_names,
                            "parentTools": list(tool_defs),
                        },
                    },
                    # 5. SUB_WORKFLOW executes the compiled plan:
                    #    FORK_JOIN (parallel section writes) → JOIN → check_quality
                    {
                        "name": "SUB_WORKFLOW",
                        "taskReferenceName": "plan_exec",
                        "type": "SUB_WORKFLOW",
                        "subWorkflowParam": {
                            "name": f"pe_{WORKFLOW_NAME}_plan",
                            "version": 1,
                            "workflowDefinition": "${plan_and_compile.output.workflowDef}",
                        },
                        "inputParameters": {
                            "prompt": "${workflow.input.topic}",
                        },
                        "optional": True,
                    },
                    # 6. Extract quality verdict from sub-workflow output
                    {
                        "name": "INLINE",
                        "taskReferenceName": "extract_quality",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": EXTRACT_QUALITY_JS,
                            "exec_output": "${plan_exec.output}",
                        },
                    },
                    # 7. Serialize quality result to a JSON string.
                    #    workflow.variables.* are substituted raw into LLM prompts —
                    #    Java Map objects render as toString(), not JSON. Storing as
                    #    a string guarantees the planner sees valid JSON every iteration.
                    {
                        "name": "INLINE",
                        "taskReferenceName": "serialize_state",
                        "type": "INLINE",
                        "inputParameters": {
                            "evaluatorType": "graaljs",
                            "expression": SERIALIZE_STATE_JS,
                            "quality_result": "${extract_quality.output.result}",
                        },
                    },
                    # 8. Persist quality report string for next iteration's planner
                    {
                        "name": "SET_VARIABLE",
                        "taskReferenceName": "update_state",
                        "type": "SET_VARIABLE",
                        "inputParameters": {
                            "report_state": "${serialize_state.output.result}",
                            "topic": "${workflow.variables.topic}",
                        },
                    },
                ],
            },
        ],
        "inputParameters": ["topic", "work_dir"],
        "outputParameters": {
            "result": "${extract_quality.output.result}",
            "iterations": "${loop.output.iteration}",
        },
        "schemaVersion": 2,
        "ownerEmail": "demo@example.com",
    }


# ── Server interactions ────────────────────────────────────────────────────────


def register_workflow(wf: dict) -> None:
    r = requests.post(
        f"{BASE}/api/metadata/workflow",
        json=[wf],
        headers={"Content-Type": "application/json"},
    )
    if r.status_code not in (200, 204):
        r2 = requests.put(
            f"{BASE}/api/metadata/workflow",
            json=[wf],
            headers={"Content-Type": "application/json"},
        )
        if r2.status_code not in (200, 204):
            raise RuntimeError(
                f"workflow registration failed: POST {r.status_code}; "
                f"PUT {r2.status_code} {r2.text}"
            )


def start_execution(topic: str, work_dir: str) -> str:
    r = requests.post(
        f"{BASE}/api/workflow/{WORKFLOW_NAME}?version={WORKFLOW_VERSION}",
        json={"topic": topic, "work_dir": work_dir},
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r.text.strip().strip('"')


def poll_until_done(execution_id: str, timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/workflow/{execution_id}?includeTasks=true")
        r.raise_for_status()
        wf = r.json()
        if wf.get("status") in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"):
            return wf
        time.sleep(2)
    raise TimeoutError(f"workflow {execution_id} did not complete in {timeout}s")


# ── Pretty printing ────────────────────────────────────────────────────────────


def print_iteration_trace(wf: dict) -> None:
    """Print one row per iteration showing what changed."""
    tasks = wf.get("tasks", [])
    suffix_re = re.compile(r"^(.+?)__(\d+)$")
    by_iter: dict[int, dict] = {}
    for t in tasks:
        ref = t.get("referenceTaskName", "")
        m = suffix_re.match(ref)
        if not m:
            continue
        base, n = m.group(1), int(m.group(2))
        by_iter.setdefault(n, {})[base] = t

    def _get_output(t: dict, key: str = "result"):
        return (t.get("outputData") or {}).get(key)

    print(f"{'iter':>5}  {'sections written':<30}  quality")
    print("─" * 80)
    for n in sorted(by_iter):
        row = by_iter[n]

        # What did the planner decide to write?
        plan_task = row.get("extract_plan", {})
        sections_raw = _get_output(plan_task)
        if isinstance(sections_raw, list):
            written = [s.get("id", "?") if isinstance(s, dict) else str(s) for s in sections_raw]
        else:
            written = ["?"]

        # What did quality check return?
        quality_task = row.get("extract_quality", {})
        quality_raw = _get_output(quality_task)
        if isinstance(quality_raw, dict):
            passed_all = quality_raw.get("quality_passed", False)
            secs = quality_raw.get("sections", {})
            if isinstance(secs, dict):
                counts = sum(1 for v in secs.values() if isinstance(v, dict) and v.get("passed"))
                quality_str = f"{counts}/{len(SECTIONS)} passed" + (" ✓ ALL" if passed_all else "")
            else:
                quality_str = "ALL PASSED" if passed_all else "failed"
        else:
            quality_str = "pending"

        print(f"{n:>5}  {', '.join(written):<30}  {quality_str}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str]) -> None:
    topic = argv[1] if len(argv) > 1 else "AI agents in production"

    print(f"server:     {BASE}")
    print(f"model:      {MODEL}")
    print(f"topic:      {topic}")
    print(f"sections:   {len(SECTIONS)} ({', '.join(s['id'] for s in SECTIONS)})")
    print(f"max iters:  {MAX_ITER}")
    print(f"output dir: {WORK_DIR}\n")

    # Clean slate
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)

    # Serialize tools via a plan_execute harness (same pattern as example 113)
    harness = plan_execute(
        name="report_tools_harness",
        tools=[write_section, check_quality],
        planner_instructions="(unused — workflow def is hand-built)",
        model=MODEL,
    )

    from conductor.ai.agents.config_serializer import AgentConfigSerializer

    ac = AgentConfigSerializer().serialize(harness)
    tool_defs = ac.get("tools", [])
    if not tool_defs:
        raise RuntimeError("could not serialize tools — check AgentConfigSerializer")

    with AgentRuntime() as runtime:
        runtime.serve(harness, blocking=False)
        print(f"workers serving: {[write_section.__name__, check_quality.__name__]}\n")

        wf_def = build_workflow_def(tool_defs)
        print("registering workflow...")
        register_workflow(wf_def)
        print(f"  OK: {WORKFLOW_NAME} v{WORKFLOW_VERSION}\n")

        print("starting PAE-replan loop...")
        execution_id = start_execution(topic, WORK_DIR)
        print(f"  execution_id: {execution_id}")
        print(f"  view:         http://localhost:6767/execution/{execution_id}\n")

        print("polling until done (all sections pass or max iterations reached)...\n")
        wf = poll_until_done(execution_id)
        print(f"  status: {wf['status']}\n")

    output = wf.get("output") or {}
    quality = output.get("result") or {}
    iterations = output.get("iterations", "?")

    print("── iteration trace ─────────────────────────────────────────────────────")
    print_iteration_trace(wf)
    print()

    print("── final quality report ────────────────────────────────────────────────")
    sections_result = quality.get("sections") or {}
    for sec_id, data in sections_result.items():
        if not isinstance(data, dict):
            continue
        status = "✓ PASSED" if data.get("passed") else "✗ FAILED"
        words = data.get("words", "?")
        needed = data.get("needed_words", "?")
        missing = data.get("missing_topics") or []
        line = f"  {sec_id:22s} {status}  ({words}/{needed} words)"
        if missing:
            line += f"  missing: {missing}"
        print(line)

    print()
    if quality.get("quality_passed"):
        total_words = sum(
            data.get("words", 0)
            for data in sections_result.values()
            if isinstance(data, dict)
        )
        print(f"✓  All sections passed in {iterations} iteration(s).  "
              f"Total: {total_words} words.")
        print(f"   Report written to {WORK_DIR}/")
        for s in SECTIONS:
            path = os.path.join(WORK_DIR, f"{s['id']}.md")
            if os.path.exists(path):
                w = len(open(path).read().split())
                print(f"   {s['id']}.md ({w} words)")
    else:
        print(f"✗  Did not converge in {iterations} iteration(s).")

    print(f"\nfull trace: {BASE.replace('/api', '')}/execution/{execution_id}")


if __name__ == "__main__":
    main(sys.argv)
