"""Load the policy reader owned by the installed planka-kanban skill."""
import importlib.util
import os
from pathlib import Path


def load_reader():
    candidates = []
    if os.environ.get("PLANKA_CLI_PATH"):
        candidates.append(Path(os.environ["PLANKA_CLI_PATH"]).with_name("board_policy.py"))
    candidates.append(Path(__file__).resolve().parents[2] / "planka-kanban/scripts/board_policy.py")
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    candidates.append(home / "skills/planka-kanban/scripts/board_policy.py")
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("planka_board_policy", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise RuntimeError("Install the updated planka-kanban skill alongside to-kanban (missing board_policy.py)")


reader = load_reader()
PolicyError = reader.PolicyError
read_board_policy = reader.read_board_policy
policy_cards = reader.policy_cards
