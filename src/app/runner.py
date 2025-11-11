from __future__ import annotations
import os
import asyncio
from google.adk.tools.tool_context import ToolContext
from src.agents.platform_selector.flow_selector import top_pipeline, flow_selector_pipeline, HAS_LOOP

def seed_mock_state(tc: ToolContext, epic: str):
    tc.state["current_epic"] = epic

    # Mock attachments per epic
    tc.state["attachments"] = {
        epic: ["design_SDD_v1.md", "design_SDD_v2.md", "note.txt"]
    }

    # Mock file contents
    tc.state["files"] = {
        "design_SDD_v2.md": "# Service Design Doc (v2)\n\nTargets: iOS, Android, backend API.\n",
        "design_SDD_v1.md": "# SDD v1\n\nTargets: web only.\n",
        "note.txt": "random note",
    }

    # Mock Jira metadata
    tc.state["jira"] = {
        epic: {
            "summary": "Add push notification service for mobile apps",
            "description": "Change touches Android/iOS clients; backend gateway updates.",
        }
    }

    # Optional: linked epics if you want to demo the loop
    tc.state["linked_epics"] = {
        epic: [f"{epic}-A", f"{epic}-B"]
    }

async def main(epic_key: str, use_loop: bool):
    tc = ToolContext()
    seed_mock_state(tc, epic_key)

    pipeline = top_pipeline if (use_loop and HAS_LOOP) else flow_selector_pipeline
    result = await pipeline.run_async(tool_context=tc)

    print("\n=== PIPELINE RESULT ===")
    print(result)
    print("\n=== STATE SNAPSHOT ===")
    for k, v in tc.state.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    os.environ.setdefault("GOOGLE_CLOUD_MODEL_NAME", "gemini-2.5-pro")
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--epic", required=True, help="Jira epic key, e.g., PROJ-123")
    p.add_argument("--use-loop", action="store_true", help="Run with outer LoopAgent if supported")
    args = p.parse_args()
    asyncio.run(main(args.epic, args.use_loop))
