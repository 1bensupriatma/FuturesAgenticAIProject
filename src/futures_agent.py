import json
from pathlib import Path

try:
    from .futures_tools import TOOLS_SCHEMA, FuturesToolbox
except ImportError:
    from futures_tools import TOOLS_SCHEMA, FuturesToolbox


DEFAULT_MODEL = "gpt-4o-mini"


DEFAULT_POLICY_PATH = Path(__file__).with_name("futures_policy.txt")


class FuturesAgent:
    """Minimal tool-calling agent for grounded futures-market analysis."""

    def __init__(self, csv_path=None, policy_path=None, model_name=DEFAULT_MODEL, client=None):
        self.client = client or self._build_client()
        self.model_name = model_name
        self.toolbox = FuturesToolbox(csv_path=csv_path)
        self.system_policy = self._load_policy(policy_path or DEFAULT_POLICY_PATH)
        self.messages = [{"role": "system", "content": self.system_policy}]

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

    @staticmethod
    def _parse_tool_args(tool_call):
        raw_args = tool_call.function.arguments or "{}"
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _request_completion(self):
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=self.messages,
            temperature=0,
            tools=TOOLS_SCHEMA,
        )

    def ask(self, prompt, max_iterations=6):
        self.messages.append({"role": "user", "content": prompt})

        for _ in range(max_iterations):
            response = self._request_completion()
            message = response.choices[0].message

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
            self.messages.append(assistant_message)

            if not message.tool_calls:
                return message.content

            for tool_call in message.tool_calls:
                args = self._parse_tool_args(tool_call)
                tool_result = self.toolbox.execute(tool_call.function.name, args)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

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
