import os
import json
from datetime import datetime, timezone
from typing import Literal

from dotenv import load_dotenv
load_dotenv()
os.environ['GOOGLE_API_KEY'] = os.getenv("GEMINI_API_KEY")

from pydantic import BaseModel, Field

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command



model = init_chat_model("google_genai:gemini-3.5-flash")



class SubmitDiagnosis(BaseModel):
    """Call this ONLY when there is enough evidence to conclude a diagnosis."""
    root_cause: str = Field(..., description="The identified root cause of the fault")
    osi_layer: str = Field(..., description="OSI layer, e.g. 'Layer 3'")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score between 0 and 1")
    evidence: list[str] = Field(..., description="Specific evidence lines supporting this diagnosis")
    fix_steps: list[str] = Field(..., description="Concrete steps to fix the issue")
    severity: Literal["Low", "Medium", "High"] = Field(..., description="Severity of the fault")


class RequestMoreEvidence(BaseModel):
    """Call this when the current evidence is NOT enough to conclude a diagnosis."""
    next_command: str = Field(..., description="The exact show command needed next")
    reasoning: str = Field(..., description="Why this command is needed")

CASES = {
    "V1_03": {
        "symptom": "PC0 can reach the gateway but cannot reach the application server.",
        "checker_findings": {"gateway_mismatch": False, "vlan_mismatch": False, "route_missing": False},
        "initial_evidence": "show ip route: 192.168.10.0/24 is directly connected, GigabitEthernet0/0\n"
                             "show ip interface brief: GigabitEthernet0/0 192.168.10.1 up up",
        "expected_next_command": "show access-lists",
        "additional_evidence": "show access-lists:\n"
                                "Extended IP access list 100\n"
                                "    10 deny ip host 192.168.10.10 host 192.168.10.100\n"
                                "    20 permit ip any any",
    },
}

_current_case_id = None
_original_ai_diagnosis = None


@tool(args_schema=RequestMoreEvidence)
def request_more_evidence(next_command, reasoning):
    """Request an additional show command when current evidence is insufficient."""
    case = CASES.get(_current_case_id, {})
    expected_cmd = case.get("expected_next_command", "")

    if expected_cmd and next_command.strip().lower() not in expected_cmd.lower():
        output = f"No recorded evidence for '{next_command}' in this case."
    else:
        output = case.get("additional_evidence", "No additional evidence available.")

    return {
        "status": "more_evidence_needed",
        "requested_command": next_command,
        "reasoning": reasoning,
        "evidence_output": output,
    }


@tool(args_schema=SubmitDiagnosis)
def submit_diagnosis(root_cause, osi_layer, confidence, evidence, fix_steps, severity):
    """Submit a final diagnosis once evidence is sufficient."""
    final = {
        "root_cause": root_cause, "osi_layer": osi_layer, "confidence": confidence,
        "evidence": evidence, "fix_steps": fix_steps, "severity": severity,
    }
    was_edited = final != _original_ai_diagnosis
    log_case(_current_case_id, {
        "final_status": "edited" if was_edited else "accepted",
        "ai_diagnosis": _original_ai_diagnosis,
        "final_diagnosis": final,
    })
    return {"status": "diagnosis_submitted", **final}




SYSTEM_PROMPT = """You are NetSage AI, a network troubleshooting assistant for Cisco
Packet Tracer labs.

You are given:
1. A user-reported symptom.
2. Findings from a deterministic rule checker.
3. One or more show-command outputs.

Your job is to identify the most likely root cause ONLY when the
available evidence supports that conclusion.

IMPORTANT RULES:

1. Never infer a configuration fault merely because it is possible.
2. Do not treat the absence of evidence as evidence of a fault.
3. If multiple root causes could explain the symptom and the supplied
   evidence does not distinguish between them, you MUST call
   request_more_evidence.
4. Do not submit a diagnosis until the supplied evidence directly
   supports the root cause.
5. For reachability problems, routing information alone is NOT
   sufficient to conclude that an ACL is not involved.
6. If the symptom indicates that the gateway is reachable but a
   destination is unreachable, and ACL evidence has not been provided,
   request `show access-lists` before diagnosing an ACL or routing fault.
7. Only use facts explicitly present in the symptom, deterministic
   findings,
   or show-command outputs.
8. Never invent IP addresses, routes, ACL entries, interfaces, or
   configuration.
9. If more evidence is required, call request_more_evidence with the
   exact show command needed.
10. Call exactly one tool per turn:
    - request_more_evidence when evidence is insufficient
    - submit_diagnosis when evidence is sufficient.
    
When proposing a fix:
- Prefer the smallest configuration change that resolves the identified fault.
- Do not recommend removing an entire ACL, route, VLAN, or security control
  when only a specific rule or parameter is faulty.
- Preserve unrelated network policies."""

checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=[submit_diagnosis, request_more_evidence],
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
    middleware=[
        HumanInTheLoopMiddleware(interrupt_on={
            "submit_diagnosis": {"allowed_decisions": ["approve", "edit", "reject"]},
            "request_more_evidence": False,  # auto-approved, no human review needed here
        })
    ],
)




def build_human_message(symptom: str, checker_findings: dict, evidence: str) -> HumanMessage:
    content = f"""SYMPTOM:
{symptom}

DETERMINISTIC CHECKER FINDINGS:
{json.dumps(checker_findings, indent=2)}

SHOW COMMAND EVIDENCE:
{evidence}
"""
    return HumanMessage(content=content)




def log_case(case_id: str, record: dict):
    record["case_id"] = case_id
    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open("case_history.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")




def edit_diagnosis_args(original_args: dict) -> dict:
    print("\nEditing diagnosis — press Enter on any field to keep its current value.\n")
    edited = dict(original_args)

    for key, value in original_args.items():
        if isinstance(value, list):
            print(f"{key} (current): {' | '.join(str(v) for v in value)}")
            new_val = input(f"New {key} (separate items with ' | ', Enter to keep): ").strip()
            if new_val:
                edited[key] = [item.strip() for item in new_val.split("|")]
        else:
            print(f"{key} (current): {value}")
            new_val = input(f"New {key} (Enter to keep): ").strip()
            if new_val:
                if isinstance(value, float):
                    try:
                        new_val = float(new_val)
                    except ValueError:
                        pass
                edited[key] = new_val
        print()

    return edited

MAX_REJECTIONS = 1  # after this many rejects, escalate to full human takeover

def review_and_resume(case_id: str, result: dict, reject_count: int = 0):
    global _original_ai_diagnosis
    config = {"configurable": {"thread_id": case_id}}
    interrupt = result["__interrupt__"][0]
    action_requests = interrupt.value["action_requests"]

    decisions = []
    for action in action_requests:
        if action["name"] == "submit_diagnosis":
            _original_ai_diagnosis = action["args"]

        print(f"\n--- Reviewing: {action['name']} ---")
        print(json.dumps(action["args"], indent=2))

        if reject_count >= MAX_REJECTIONS:
            print(f"[{case_id}] Max rejections reached — escalating to human takeover.")
            log_case(case_id, {"final_status": "human_takeover", "last_ai_diagnosis": action["args"]})
            return None

        choice = input("Decision? [approve/edit/reject]: ").strip().lower()

        if choice == "approve":
            decisions.append({"type": "approve"})
        elif choice == "edit":
            edited_args = edit_diagnosis_args(action["args"])
            decisions.append({"type": "edit", "edited_action": {"name": action["name"], "args": edited_args}})
        elif choice == "reject":
            message = input("Reason for rejection: ").strip()
            decisions.append({"type": "reject", "message": message or "Rejected by reviewer."})
            reject_count += 1
        else:
            decisions.append({"type": "reject", "message": "Invalid reviewer input."})
            reject_count += 1

    resumed = agent.invoke(Command(resume={"decisions": decisions}), config=config)

    if "__interrupt__" in resumed:
        return review_and_resume(case_id, resumed, reject_count=reject_count)

    print(f"[{case_id}] Case resolved.")
    return resumed





def run_case(case_id: str):
    global _current_case_id
    _current_case_id = case_id
    case = CASES[case_id]

    human_msg = build_human_message(case["symptom"], case["checker_findings"], case["initial_evidence"])
    config = {"configurable": {"thread_id": case_id}}

    result = agent.invoke({"messages": [human_msg]}, config=config)

    if "__interrupt__" in result:
        return review_and_resume(case_id, result)

    print(f"[{case_id}] Finished without needing review.")
    return result



if __name__ == "__main__":
    run_case("V1_03")
