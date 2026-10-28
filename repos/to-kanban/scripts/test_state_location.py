import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import kanban_context as context
import compile_plan

class StateLocationTests(unittest.TestCase):
    def test_first_use_and_remembered_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pointer = root / 'settings' / 'location.json'
            with patch.object(context, 'location_config_path', return_value=pointer):
                with self.assertRaises(context.ContextError):
                    context.state_root()
                self.assertFalse(pointer.parent.exists())
                target = root / 'chosen folder'
                context.configure_state(target)
                self.assertEqual(context.state_root(), target.resolve())
                self.assertEqual(compile_plan.default_config_path(), target / 'current-route.json')
                self.assertEqual(compile_plan.default_board_path(), target / 'current-board.json')
                self.assertEqual(json.loads(pointer.read_text()), {'stateDir': str(target.resolve())})
                memory = target / 'memory.json'
                original = memory.read_bytes()
                context.configure_state(target)
                self.assertEqual(memory.read_bytes(), original)

    def test_invalid_and_relative_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            pointer = Path(tmp) / 'location.json'
            with patch.object(context, 'location_config_path', return_value=pointer):
                with self.assertRaises(context.ContextError):
                    context.configure_state(Path('relative-folder'))
                self.assertFalse(pointer.exists())
                pointer.write_text('{"stateDir": "relative"}')
                with self.assertRaises(context.ContextError):
                    context.state_root()

if __name__ == '__main__':
    unittest.main()
