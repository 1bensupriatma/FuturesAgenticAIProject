from pathlib import Path

try:
    from .futures_repository import FuturesDataRepository
except ImportError:
    from futures_repository import FuturesDataRepository


DEFAULT_FUTURES_CSV = Path("data/sample_futures_data.csv")


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_available_contracts",
            "description": "List symbols and contracts available in the futures dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Optional root symbol filter such as ES or CL.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contract_snapshot",
            "description": "Return the latest row, or a row for a specific date, for a futures contract.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "contract": {"type": "string"},
                    "date": {"type": "string", "description": "ISO date such as 2025-01-15."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_price_move",
            "description": "Summarize start-to-end price movement for a symbol or contract over a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "contract": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["symbol", "start_date", "end_date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_term_structure",
            "description": "Compare same-day prices across expiries to infer contango, backwardation, or flat structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_rollover",
            "description": "Detect dominant contract handoff over time using open interest or volume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
        },
    },
]


class FuturesToolbox:
    def __init__(self, csv_path=None):
        self.repository = FuturesDataRepository.from_default_path(csv_path or DEFAULT_FUTURES_CSV)

    def execute(self, tool_name, args):
        if tool_name == "list_available_contracts":
            payload = self.repository.list_contracts(symbol=args.get("symbol"))
        elif tool_name == "get_contract_snapshot":
            payload = self.repository.get_contract_snapshot(
                symbol=args.get("symbol"),
                contract=args.get("contract"),
                date=args.get("date"),
            )
        elif tool_name == "summarize_price_move":
            payload = self.repository.summarize_price_move(
                symbol=args.get("symbol"),
                contract=args.get("contract"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date"),
            )
        elif tool_name == "calculate_term_structure":
            payload = self.repository.calculate_term_structure(
                symbol=args.get("symbol"),
                date=args.get("date"),
            )
        elif tool_name == "detect_rollover":
            payload = self.repository.detect_rollover(
                symbol=args.get("symbol"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date"),
            )
        else:
            payload = {"error": f"Unknown tool: {tool_name}"}

        return self.repository.to_json(payload)
