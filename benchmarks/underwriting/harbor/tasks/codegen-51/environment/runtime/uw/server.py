"""MCP server for one underwriting case, run as a sidecar next to the agent's container.

It serves what the original harness (harness/run.py) gave the copilot, with the original code:
- the six read-only tools over the rebuilt database and guidelines (run.Env, run.TOOLS);
- `ask_underwriter`: the simulated underwriter (run.underwriter_reply: Claude Haiku 5.5 with the application in its
  prompt, never the answer), limited to run.MAX_TURNS replies as in the original;
- `submit_final_answer`: ends the case. Only the first submission counts.

The grader reads the outcome from GET /state. The agent can read it too; it holds nothing the agent has not seen
(no reference answer exists in this container). Writes happen only through the MCP tools.

Layout (built by harbor/generate_tasks.py): /opt/uw/harness/run.py (+ llm.py, judge.py), /opt/uw/src/models_client,
/opt/uw/env/insurance.db and guidelines.txt, /opt/uw/case.json (case id, question type, application; no answer).
"""
import json
import os
import re
import sys
import threading
import time

ROOT = os.environ.get("UW_ROOT", "/opt/uw")
sys.path.insert(0, os.path.join(ROOT, "harness"))
import run as uw  # noqa: E402  the benchmark's own tools, simulator prompt and limits

ENDED = {
    "finished": "The case is closed: a final answer was already submitted.",
    "turn_limit": "The underwriter has ended the conversation (turn limit reached). The case is closed.",
    "simulator_error": "The underwriter is unavailable (simulator error). The case is closed.",
}


class Case:
    """State of one case: transcript, counters and the final answer. Thread-safe."""

    def __init__(self, case, reply_fn=None, env=None):
        self.case = case
        self.reply_fn = reply_fn or uw.underwriter_reply
        self.env = env or uw.Env()
        self.lock = threading.Lock()
        self.transcript = [("underwriter", uw.SEEDS[case["task"]])]
        self.status = "open"
        self.final_answer = None
        self.turns = 0
        self.tool_calls = 0
        self.sim_cost = 0.0
        self.errors = []
        self.events = []
        self.t0 = time.time()

    def _log(self, kind, **kw):
        self.events.append(dict(t=round(time.time() - self.t0, 3), kind=kind, **kw))

    def tool(self, name, args):
        with self.lock:
            self.tool_calls += 1
            out = self.env.run(name, args)[:20000]
            self._log("tool", name=name, args=args, chars=len(out))
            return out

    def ask(self, message):
        with self.lock:
            if self.status != "open":
                return ENDED[self.status]
            message = (message or "").strip()
            if not message:
                return "Error: the message is empty."
            self.transcript.append(("copilot", message))
            self.turns += 1
            if self.turns > uw.MAX_TURNS:
                self.status = "turn_limit"
                self._log("turn_limit")
                return ENDED["turn_limit"]
            try:
                reply, cost = self.reply_fn(self.case, self.transcript)
            except Exception as e:  # noqa: BLE001 - an API failure is an infrastructure error, not a wrong answer
                self.status = "simulator_error"
                self.errors.append(repr(e)[:300])
                self._log("simulator_error")
                return ENDED["simulator_error"]
            self.sim_cost += cost
            self.transcript.append(("underwriter", reply))
            self._log("ask", turn=self.turns)
            return reply

    def submit(self, answer):
        with self.lock:
            if self.status != "open":
                return ENDED[self.status]
            text = (answer or "").strip()
            if not text:
                return "Error: the answer is empty. Nothing was submitted."
            # The original episode kept the reply from "FINAL ANSWER:" on; the judges saw that text.
            m = re.search(r"FINAL ANSWER\s*:", text)
            self.final_answer = text[m.start():] if m else "FINAL ANSWER: " + text
            self.transcript.append(("copilot", self.final_answer))
            self.status = "finished"
            self._log("submit")
            return "Final answer recorded. The case is closed."

    def state(self):
        with self.lock:
            return dict(case_id=self.case["id"], task_type=self.case["task"], status=self.status,
                        final_answer=self.final_answer, underwriter_turns=self.turns, tool_calls=self.tool_calls,
                        sim_cost=self.sim_cost, errors=list(self.errors), transcript=list(self.transcript),
                        events=list(self.events))


def _description(name):
    return next(t["function"]["description"] for t in uw.TOOLS if t["function"]["name"] == name)


def build_server(case_obj, host="0.0.0.0", port=8000):
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.responses import JSONResponse

    mcp = FastMCP("underwriting", host=host, port=port, stateless_http=True, json_response=True,
                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    def list_tables() -> str:
        return case_obj.tool("list_tables", {})

    def get_table_descriptions() -> str:
        return case_obj.tool("get_table_descriptions", {})

    def get_table_schema(table_name: str) -> str:
        return case_obj.tool("get_table_schema", {"table_name": table_name})

    def get_table_data_dictionary(table: str) -> str:
        return case_obj.tool("get_table_data_dictionary", {"table": table})

    def read_query(query: str) -> str:
        return case_obj.tool("read_query", {"query": query})

    def get_underwriting_guidelines() -> str:
        return case_obj.tool("get_underwriting_guidelines", {})

    for fn in (list_tables, get_table_descriptions, get_table_schema, get_table_data_dictionary, read_query,
               get_underwriting_guidelines):
        mcp.add_tool(fn, name=fn.__name__, description=_description(fn.__name__))

    def ask_underwriter(message: str) -> str:
        return case_obj.ask(message)

    def submit_final_answer(answer: str) -> str:
        return case_obj.submit(answer)

    mcp.add_tool(ask_underwriter, name="ask_underwriter", description=(
        "Send a message to the underwriter, who has the application details, and get their reply. Use it to ask "
        f"for any information you need. At most {uw.MAX_TURNS} messages per case."))
    mcp.add_tool(submit_final_answer, name="submit_final_answer", description=(
        "Submit your final answer to the underwriter's request, with a short rationale. Only the first submission "
        "counts, and it closes the case."))

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request):
        return JSONResponse({"ok": True})

    @mcp.custom_route("/state", methods=["GET"])
    async def state(request):
        return JSONResponse(case_obj.state())

    return mcp


def main():
    case = json.load(open(os.path.join(ROOT, "case.json")))
    build_server(Case(case), port=int(os.environ.get("UW_PORT", "8000"))).run(transport="streamable-http")


if __name__ == "__main__":
    main()
