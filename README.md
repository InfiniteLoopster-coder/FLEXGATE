A production‑grade, multi‑agent pipeline built with the **Google Agent Development Kit (ADK)**. It reads epics, loads the newest SDD attachment, infers impacted platforms from **metadata** and **SDD content**, and persists a combined result. Includes a mock runner so you can execute end‑to‑end without wiring external systems, plus an optional loop to iterate linked epics.

> If you prefer a project name: **Flexgate** is a clean option. Replace the title accordingly.

---

## Features
- **Agent graph mirrors architecture** (info retrieval → flow eval → parallel SDD/metadata evaluation).
- **Every Agent has `tools=[...]` (or `[]`)** to avoid `KeyError: 'tools'` in wrappers.
- **Dynamic prompts** use the ADK *injector* when available, **falls back** to safe `.format(...)`.
- **Mock state seeding** in the runner to demo without Jira or storage.
- **Optional `LoopAgent`** wraps the full pipeline to process *linked epics*.
- Clear **state contract** (`ticket_content`, `flow_info`, `sdd_content`, `meta_eval_platforms`, `sdd_eval_platforms`, `platform_info`).

---

## Repo Structure
src/
agents/
platform_selector/
flow_selector.py # all agents wired here (Sequential/Parallel/Loop, dynamic prompts)
tools.py # domain tools (Jira stubs, SDD loader, storage)
model.py # CustomVertexAIModel wrapper (Gemini/Vertex config holder)
app/
runner.py # entrypoint: seeds mock state and runs the pipeline

---


## Agent Graph (high‑level)
root (flow_selector)
└─ flow_selector_pipeline [Sequential]
├─ info_retrieval [Parallel]
│ ├─ read_flow_info (Agent → output_key: flow_info)
│ └─ read_ticket (Agent → output_key: ticket_content)
├─ eval_flows (Agent, tools=[]; text-only, combines signals)
└─ eval_sdd_and_meta_data_for_platforms [Parallel]
├─ eval_issue_meta_data_for_platforms (Agent → store_meta_data_eval)
└─ eval_sdd_for_platforms [Sequential]
├─ get_newest_sdd_content (Agent → output_key: sdd_content)
└─ eval_content_for_platforms (Agent → store_sdd_eval + store_platform_info)

[optional]
top_pipeline = prepare_loop_items → loop_conductor_eval_linked_epics_for_platforms
(LoopAgent: iterate linked epics, running flow_selector_pipeline per item)


---

## Prerequisites

- Python 3.10+
- Access to the **Google ADK** (`google.adk` package) and a deployed **Vertex AI / Gemini** model
- (Optional) `python-dotenv` for local env management

**Environment variable**
GOOGLE_CLOUD_MODEL_NAME="gemini-2.5-pro" # or your deployed Vertex model name


Quickstart

Clone and set env
Always show details
export GOOGLE_CLOUD_MODEL_NAME="gemini-2.5-pro"
Run single epic
Always show details
python -m src.app.runner --epic PROJ-123
Run with loop (iterate linked epics)
Always show details
python -m src.app.runner --epic PROJ-123 --use-loop

You should see a final STATE SNAPSHOT printed with keys like platform_info, sdd_eval_platforms, meta_eval_platforms, etc.

How it works (end‑to‑end)

info_retrieval (Parallel)
read_ticket → lists attachments → picks newest SDD → loads markdown → sets ticket_content (and may set sdd_content).
read_flow_info → extracts flow hints from metadata → sets flow_info.
eval_flows (Agent, tools=[])
Text‑only reasoning using both signals (flow_info & ticket_content) to decide affected flows.
eval_sdd_and_meta_data_for_platforms (Parallel)
eval_sdd_for_platforms (Sequential)
get_newest_sdd_content → enforces filename listing first, special cases (“NO SDD FILES ATTACHED”), sets sdd_content.
eval_content_for_platforms → calls get_affected_platforms(source="sdd") → persists with store_sdd_eval + store_platform_info.
eval_issue_meta_data_for_platforms (Agent)
Reads Jira Summary/Description, calls store_meta_data_eval.
[Optional] Outer Loop
prepare_loop_items loads linked_epics into state.loop_items.
loop_conductor_eval_linked_epics_for_platforms (LoopAgent) pops each epic, sets current_epic, and re‑runs the entire pipeline.

Tools (stubs to replace)

All tools live in src/agents/platform_selector/tools.py and accept a ToolContext. Replace stubs with real systems:
get_epic_attachment_filenames(tc) → integrate with FS APIs.
get_attachment_and_convert_to_markdown(tc, filename) → fetch binary + convert (PDF→md, DOCX→md, etc.).
get_issue_meta_data(tc) → Jira Summary/Description.
get_affected_platforms(tc, source) → swap keyword heuristic for an LLM/classifier or rules.
store_meta_data_eval(tc, platforms) / store_sdd_eval(tc, platforms) → persist to DB.
store_platform_info(tc, info) → merge and persist unified view.
Loop helpers: get_linked_epics, get_len_state_list, get_next_state_list_item, exit_loop.
State contract (shared keys)
Always show details
current_epic: str
ticket_content: str
flow_info: str
sdd_content: str
meta_eval_platforms: List[str]
sdd_eval_platforms: List[str]
platform_info: Dict[str, Any]  # {"platforms": [...], ...}
loop_items: List[str]          # (optional, for LoopAgent)

Guardrails & Conventions

Always set tools=[...] (or []) on Agents → avoids KeyError: 'tools' in wrappers expecting this key.
Dynamic prompts: we use instruction_utils.inject_session_state if the injector exists; otherwise .format(...) is used safely.
Literal braces in prompts → use {{ and }}.
Order of actions enforced in instructions (e.g., “always call get_epic_attachment_filenames first”).
Idempotent storage: make store_* tools upsert in production to avoid duplicates when re‑running.

Testing & Eval (suggested)

Unit tests for each tool (mock Jira/FS/DB).
Golden set of epics with expected platforms:
Always show details
- epic: PROJ-123
  expect_platforms: [ios, android, backend]
  expect_has_sdd: true
CLI harness: run pipeline and compute precision/recall on platform_info["platforms"].

Troubleshooting

KeyError: 'tools'
Ensure every agent has tools=[...] or modify your wrapper to use config.get("tools", []).
KeyError with injector ({ticket_content} not found)
Injector treats {key} as a key name in session_state. Put values there first:
Always show details
ctx.session_state["ticket_content"] = tc.state.get("ticket_content", "")
Or skip injector and use .format(ticket_content=...).
No SDD chosen / wrong file
Confirm get_epic_attachment_filenames returns the expected list and your naming/date rule for “newest” is correct.
Model/token limits
Chunk large SDDs and summarize before reasoning. Set max_output_tokens in CustomVertexAIModel if your runtime uses it.

Security & Privacy (prod notes)

Avoid sending raw attachments to the LLM. Pre‑summarize or redact.
Log tool calls with minimal necessary metadata.
Enforce tool whitelisting per agent to constrain capabilities.
Store outputs with versioning and trace IDs for auditability.
