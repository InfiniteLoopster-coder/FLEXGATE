from __future__ import annotations
import os
from google.adk.agents import Agent, SequentialAgent, ParallelAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext

# Optional LoopAgent (ADK version dependent)
try:
    from google.adk.agents import LoopAgent
    HAS_LOOP = True
except Exception:
    HAS_LOOP = False

# Optional injector helper (ADK version dependent)
try:
    from google.adk.utils import instruction_utils
    HAS_INJECTOR = True
except Exception:
    HAS_INJECTOR = False

from src.agents.model import CustomVertexAIModel
from src.agents.platform_selector.tools import (
    get_epic_attachment_filenames,
    get_attachment_and_convert_to_markdown,
    get_issue_meta_data,
    get_affected_platforms,
    store_meta_data_eval,
    store_sdd_eval,
    store_platform_info,
    get_linked_epics,
    get_len_state_list,
    get_next_state_list_item,
    exit_loop,
)

MODEL = CustomVertexAIModel(os.environ["GOOGLE_CLOUD_MODEL_NAME"])

def _tools(*fns):
    return list(fns) if fns else []  # always a list → prevents KeyError: 'tools'

# ---------- Dynamic instruction providers with injector fallback ----------

async def ip_read_ticket(tc: ToolContext, ctx: ReadonlyContext) -> str:
    ctx.session_state["current_epic"] = tc.state.get("current_epic", "")
    template = (
        "1) Call get_epic_attachment_filenames first.\n"
        "2) Identify newest SDD.\n"
        "3) Load exact content via get_attachment_and_convert_to_markdown.\n"
        "Return only markdown. Current epic: {current_epic}"
    )
    if HAS_INJECTOR:
        return await instruction_utils.inject_session_state(template, ctx)
    return template.format(current_epic=tc.state.get("current_epic", ""))

async def ip_eval_flows(tc: ToolContext, ctx: ReadonlyContext) -> str:
    ctx.session_state["flow_info"] = tc.state.get("flow_info", "")
    ctx.session_state["ticket_content"] = tc.state.get("ticket_content", "")
    template = (
        "Using both signals, decide affected flows.\n\n"
        "flow information:\n{flow_info}\n\n"
        "ticket content:\n{ticket_content}\n\n"
        "Return a bullet list 'platform_flows' with one entry per flow and a short reason."
    )
    if HAS_INJECTOR:
        return await instruction_utils.inject_session_state(template, ctx)
    return template.format(
        flow_info=tc.state.get("flow_info", ""),
        ticket_content=tc.state.get("ticket_content", ""),
    )

async def ip_eval_issue_meta(tc: ToolContext, ctx: ReadonlyContext) -> str:
    return "Use Jira metadata only. Persist via store_meta_data_eval."

async def ip_get_newest_sdd(tc: ToolContext, ctx: ReadonlyContext) -> str:
    return ("Always call get_epic_attachment_filenames first. If no SDD → reply "
            "'NO SDD FILES ATTACHED'. If multiple, choose newest. Then convert to markdown. Output key: sdd_content.")

async def ip_eval_content_for_platforms(tc: ToolContext, ctx: ReadonlyContext) -> str:
    ctx.session_state["sdd_content"] = tc.state.get("sdd_content", "")
    template = "From SDD content below, derive platforms and persist via store_sdd_eval & store_platform_info.\n\n{sdd_content}"
    if HAS_INJECTOR:
        return await instruction_utils.inject_session_state(template, ctx)
    return template.format(sdd_content=tc.state.get("sdd_content", ""))

async def ip_loop_linked_epics(tc: ToolContext, ctx: ReadonlyContext) -> str:
    return "Iterate 'loop_items'; for each item set 'current_epic' and run the body. Exit when list is empty."

# ---------- Leaf Agents (all have tools=[...] or []) ----------

read_ticket = Agent(
    name="read_ticket",
    model=MODEL,
    tools=_tools(
        get_epic_attachment_filenames,
        get_attachment_and_convert_to_markdown,
        get_issue_meta_data,
    ),
    output_key="ticket_content",
    instructions=ip_read_ticket,
)

read_flow_info = Agent(
    name="read_flow_info",
    model=MODEL,
    tools=_tools(get_issue_meta_data),
    output_key="flow_info",
    instructions="Extract flow info hints from the Jira metadata. Output plain text.",
)

get_newest_sdd_content = Agent(
    name="get_newest_sdd_content",
    model=MODEL,
    tools=_tools(get_epic_attachment_filenames, get_attachment_and_convert_to_markdown),
    output_key="sdd_content",
    instructions=ip_get_newest_sdd,
)

eval_content_for_platforms = Agent(
    name="eval_content_for_platforms",
    model=MODEL,
    tools=_tools(get_affected_platforms, store_sdd_eval, store_platform_info),
    instructions=ip_eval_content_for_platforms,
)

eval_issue_meta_data_for_platforms = Agent(
    name="eval_issue_meta_data_for_platforms",
    model=MODEL,
    tools=_tools(get_issue_meta_data, store_meta_data_eval),
    instructions=ip_eval_issue_meta,
)

# ---------- Mid-level Agents ----------

info_retrieval = ParallelAgent(
    name="info_retrieval",
    sub_agents=[read_flow_info, read_ticket],
)

eval_flows = Agent(
    name="eval_flows",
    model=MODEL,
    tools=_tools(),  # text-only agent; explicit empty list -> safe
    instructions=ip_eval_flows,
)

eval_sdd_for_platforms = SequentialAgent(
    name="eval_sdd_for_platforms",
    sub_agents=[get_newest_sdd_content, eval_content_for_platforms],
)

eval_sdd_and_meta_data_for_platforms = ParallelAgent(
    name="eval_sdd_and_meta_data_for_platforms",
    sub_agents=[eval_issue_meta_data_for_platforms, eval_sdd_for_platforms],
)

# ---------- Optional outer loop around the whole pipeline ----------

# Prepare loop items (populate state.loop_items via get_linked_epics)
prepare_loop_items = Agent(
    name="prepare_loop_items",
    model=MODEL,
    tools=_tools(get_linked_epics, get_len_state_list),
    instructions="Call get_linked_epics to populate 'loop_items'. Optionally call get_len_state_list to log length.",
)

# The core pipeline for a single epic
flow_selector_pipeline = SequentialAgent(
    name="flow_selector_pipeline",
    sub_agents=[info_retrieval, eval_flows, eval_sdd_and_meta_data_for_platforms],
)

if HAS_LOOP:
    loop_conductor_eval_linked_epics_for_platforms = LoopAgent(
        name="loop_conductor_eval_linked_epics_for_platforms",
        tools=_tools(get_len_state_list, get_next_state_list_item, exit_loop),
        body=flow_selector_pipeline,  # run the full pipeline per epic
        instructions=ip_loop_linked_epics,
    )
    # Top pipeline with loop
    top_pipeline = SequentialAgent(
        name="top_pipeline",
        sub_agents=[prepare_loop_items, loop_conductor_eval_linked_epics_for_platforms],
    )
else:
    loop_conductor_eval_linked_epics_for_platforms = None
    top_pipeline = flow_selector_pipeline  # fallback

__all__ = [
    "top_pipeline",
    "flow_selector_pipeline",
    "loop_conductor_eval_linked_epics_for_platforms",
    "HAS_LOOP",
]
