from llm_router import llm_route
import json

for q in ["Which trials are in Phase III?", "What is compound CMP-0001's therapeutic area?"]:
    print("="*70)
    print("Q:", q)
    r = llm_route(q, session_id="debug")
    print("Tool used:", r.get("tool_used"))
    print("Full result:")
    print(json.dumps(r.get("result"), indent=2, default=str))
    print()
