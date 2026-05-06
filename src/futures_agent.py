import json
import logging
from pathlib import Path

try:
    from .audit_logging import configure_logging, flush_transcript, start_new_session_log
    from .futures_tools import TOOLS_SCHEMA, FuturesToolbox
except ImportError:
    from audit_logging import configure_logging, flush_transcript, start_new_session_log
    from futures_tools import TOOLS_SCHEMA, FuturesToolbox


DEFAULT_MODEL = "gpt-4o"


DEFAULT_POLICY_PATH = Path(__file__).with_name("futures_policy.txt")
log = logging.getLogger("agent")


class FuturesAgent:
    """Minimal tool-calling agent for grounded futures-market analysis."""

    def __init__(self, csv_path=None, policy_path=None, model_name=DEFAULT_MODEL, client=None, preserve_history=True):
        self.active_log_path = configure_logging()
        self.client = client or self._build_client()
        self.model_name = model_name
        self.toolbox = FuturesToolbox(csv_path=csv_path)
        self.preserve_history = preserve_history
        self.system_policy = self._load_policy(policy_path or DEFAULT_POLICY_PATH)
        self.messages = [{"role": "system", "content": self.system_policy}]
        log.info("Agent initialized: model=%s preserve_history=%s log=%s", self.model_name, self.preserve_history, self.active_log_path)

    def start_new_session(self):
        """Create a fresh audit transcript for the next agent interaction."""
        self.active_log_path = start_new_session_log()
        log.info("Agent session started: model=%s log=%s", self.model_name, self.active_log_path)
        return self.active_log_path

    @staticmethod
    def _build_client():
        try:
            try:
                from .openai_client import get_client
            except ImportError:
                from openai_client import get_client
        except ImportError as exc:
            raise ImportError(
                "OpenAI client dependencies are not available. Install project dependencies first."
            ) from exc

        return get_client()

    @staticmethod
    def _load_policy(policy_path):
        path = Path(policy_path)
        try:
            policy = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"Could not read policy file: {exc}") from exc
        if not policy:
            raise ValueError(f"Policy file is empty: {path}")
        return policy

    def _parse_tool_args(self, tool_call):
        raw_args = tool_call.function.arguments or "{}"
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            log.warning(
                "Malformed tool arguments: tool=%s raw_args=%s",
                tool_call.function.name,
                raw_args,
            )
            return {}
        if not isinstance(parsed, dict):
            log.warning(
                "Malformed tool arguments: tool=%s parsed_non_object=%s",
                tool_call.function.name,
                parsed,
            )
            return {}
        return parsed

    def _request_completion(self, messages):
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0,
            tools=TOOLS_SCHEMA,
        )

    def ask(self, prompt, max_iterations=6, toolbox=None, create_session_log=True):
        if create_session_log:
            self.start_new_session()

        messages = self.messages if self.preserve_history else [{"role": "system", "content": self.system_policy}]
        active_toolbox = toolbox or self.toolbox
        messages.append({"role": "user", "content": prompt})
        log.info("User input: %s", prompt)

        for iteration in range(1, max_iterations + 1):
            log.info("Agent loop iteration %s/%s", iteration, max_iterations)
            response = self._request_completion(messages)
            message = response.choices[0].message
            log.info("Assistant intermediate response: %s", message.content or "")

            assistant_message = {
                "role": "assistant",
                "content": message.content or "",
            }
            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": call.type,
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(assistant_message)

            if not message.tool_calls:
                if self.preserve_history:
                    self.messages = messages
                log.info("Final response: %s", message.content or "")
                flush_transcript()
                return message.content

            for tool_call in message.tool_calls:
                args = self._parse_tool_args(tool_call)
                log.info(
                    "Tool call: name=%s args=%s",
                    tool_call.function.name,
                    json.dumps(args, default=str),
                )
                tool_result = active_toolbox.execute(tool_call.function.name, args)
                log.info("Tool result: name=%s result=%s", tool_call.function.name, tool_result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

        if self.preserve_history:
            self.messages = messages
        log.warning("Loop termination: maximum tool iterations reached (%s)", max_iterations)
        flush_transcript()
        return "The agent stopped after reaching the maximum tool-iteration limit."


def chat(csv_path=None, model_name=DEFAULT_MODEL):
    agent = FuturesAgent(csv_path=csv_path, model_name=model_name)
    print(f"--- Futures Agent Started ({model_name}) ---")
    print("Type 'quit' to exit.")

    while True:
        prompt = input("\nYou: ").strip()
        if prompt.lower() in {"quit", "exit"}:
            break
        print(f"\nAssistant: {agent.ask(prompt)}")


if __name__ == "__main__":
    chat()
