from __future__ import annotations
from typing import Dict, List, Any
from google.adk.tools.tool_context import ToolContext

def _ensure_list(val) -> List[Any]:
    if isinstance(val, list): return val
    if val is None: return []
    return [val]

def _detect_platforms_from_text(text: str) -> List[str]:
    text_low = (text or "").lower()
    found = [p for p in ["ios", "android", "web", "backend", "api"] if p in text_low]
    return sorted(set(found)) or ["unknown"]

def get_epic_attachment_filenames(tool_context: ToolContext) -> Dict[str, Any]:
    current = tool_context.state.get("current_epic", "EPIC-UNKNOWN")
    attachments = tool_context.state.get("attachments", {})
    return {"status": "success", "filenames": attachments.get(current, [])}

def get_attachment_and_convert_to_markdown(tool_context: ToolContext, filename: str) -> Dict[str, Any]:
    files = tool_context.state.get("files", {})
    content = files.get(filename, f"# MOCK SDD\n\nFile: {filename}\n\n(No real content found.)")
    tool_context.state["sdd_content"] = content
    return {"status": "success", "markdown": content}

def get_issue_meta_data(tool_context: ToolContext) -> Dict[str, Any]:
    current = tool_context.state.get("current_epic", "EPIC-UNKNOWN")
    jira = tool_context.state.get("jira", {})
    info = jira.get(current, {"summary": "(none)", "description": "(none)"})
    return {"status": "success", "summary": info.get("summary", ""), "description": info.get("description", "")}

def get_affected_platforms(tool_context: ToolContext, source: str = "sdd") -> Dict[str, Any]:
    text = tool_context.state.get("sdd_content" if source == "sdd" else "ticket_content", "")
    return {"status": "success", "platforms": _detect_platforms_from_text(text)}

def store_meta_data_eval(tool_context: ToolContext, platforms: List[str]) -> Dict[str, Any]:
    tool_context.state["meta_eval_platforms"] = _ensure_list(platforms)
    return {"status": "success", "meta_eval_platforms": tool_context.state["meta_eval_platforms"]}

def store_sdd_eval(tool_context: ToolContext, platforms: List[str]) -> Dict[str, Any]:
    tool_context.state["sdd_eval_platforms"] = _ensure_list(platforms)
    return {"status": "success", "sdd_eval_platforms": tool_context.state["sdd_eval_platforms"]}

def store_platform_info(tool_context: ToolContext, info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    meta = set(tool_context.state.get("meta_eval_platforms", []))
    sdd = set(tool_context.state.get("sdd_eval_platforms", []))
    union = sorted(meta | sdd)
    tool_context.state["platform_info"] = {"platforms": union, **(info or {})}
    return {"status": "success", "platform_info": tool_context.state["platform_info"]}

#------------------------ Looping tools for epics ------------------------

def get_linked_epics(tool_context: ToolContext) -> Dict[str, Any]:
    cur = tool_context.state.get("current_epic", "EPIC-UNKNOWN")
    linked = tool_context.state.get("linked_epics", {}).get(cur, [])
    tool_context.state["loop_items"] = list(linked)
    return {"status": "success", "items": linked}

def get_len_state_list(tool_context: ToolContext, key: str = "loop_items") -> Dict[str, Any]:
    return {"status": "success", "length": len(tool_context.state.get(key, []))}

def get_next_state_list_item(tool_context: ToolContext, key: str = "loop_items") -> Dict[str, Any]:
    items = tool_context.state.get(key, [])
    if not items:
        return {"status": "done", "item": None}
    item = items.pop(0)
    tool_context.state[key] = items
    tool_context.state["current_epic"] = item
    return {"status": "success", "item": item}

def exit_loop(tool_context: ToolContext) -> Dict[str, Any]:
    return {"status": "exit"}
