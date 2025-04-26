# Chat Context Window Tracking for Open-WebUI

**Version:** 0.1.1  
**License:** MIT  
**Author:** [Taylor Wilsdon](https://github.com/taylorwilsdon)

A performant, lightweight context-window tracker for Open-WebUI, built with minimal latency in mind. Tracks token usage and conversation turns, displaying progress and warnings as your chat unfolds.

---

## 📦 Requirements

- Python 3.8 or newer  
- [tiktoken](https://pypi.org/project/tiktoken/)  
- [open-webui](https://github.com/open-webui/open-webui) (for `Models`)  
- [pydantic](https://pypi.org/project/pydantic/)  

---

## 🚀 Installation

1. **Clone** this repo (or copy `filter.py` into your project’s filters folder):
   ```bash
   git clone https://github.com/taylorwilsdon/open-webui-context-tracker.git
   cd open-webui-context-tracker
   ```

2. **Install** runtime dependencies:
   ```bash
   pip install tiktoken pydantic open-webui
   ```

3. **Enable** the filter in your Open-WebUI config (e.g. `config.yaml`):
   ```yaml
   filters:
     - module: filter
       class: Filter
       valves:
         log_level: INFO
         show_status: true
         show_progress_bar: true
         bar_length: 5
         warn_at_percentage: 75.0
         critical_at_percentage: 90.0
         max_turns: 8
         turn_warn_at_percentage: 75.0
         turn_critical_at_percentage: 90.0
         show_turn_status: true
         custom_models_plaintext: |
           # One override per line:
           # <model-id> <context-size>
           my-custom-model 65536
   ```

---

## ⚙️ Configuration (Valves)

| Option                        | Type    | Default | Description                                                        |
| ----------------------------- | ------- | ------- | ------------------------------------------------------------------ |
| `log_level`                   | `str`   | `"INFO"`| Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, etc.)  |
| `show_status`                 | `bool`  | `true`  | Emit a `"status"` event with token/turn usage                      |
| `show_progress_bar`           | `bool`  | `true`  | Render a textual progress bar alongside the status                 |
| `bar_length`                  | `int`   | `5`     | Number of characters in the progress bar                           |
| `warn_at_percentage`          | `float` | `75.0`  | When context usage ≥ this %, prefix status with `Warning:`         |
| `critical_at_percentage`      | `float` | `90.0`  | When context usage ≥ this %, prefix status with `Critical:`        |
| `max_turns`                   | `int`   | `8`     | Maximum user-assistant turns before warning                        |
| `turn_warn_at_percentage`     | `float` | `75.0`  | When turns ≥ this % of `max_turns`, prefix with `Warning:`         |
| `turn_critical_at_percentage` | `float` | `90.0`  | When turns ≥ this % of `max_turns`, prefix with `Critical:`        |
| `show_turn_status`            | `bool`  | `true`  | Include turn-count in the status string                            |
| `custom_models_plaintext`     | `str`   | `""`    | Multi-line override of `<model-id> <num_ctx>` per line             |

---

## 🎯 How It Works

1. **Initialization**  
   - Loads a hard-coded map of common model context sizes.  
   - Parses any user-provided overrides.  
   - Sets up a cached SHA-1 digest to re-parse overrides only on change.

2. **Token Counting**  
   - Uses `tiktoken`’s `cl100k_base` encoder to count tokens for all messages.  
   - Splits total vs. assistant-only tokens to show both input and output usage.

3. **Turn Counting**  
   - Counts each user+assistant pair as one “turn”.  
   - Triggers warnings or critical alerts based on configured thresholds.

4. **Status Emission**  
   - Constructs a status string like  
     ```
     Warning:Context: 4.2K/8K (52.5%) [⬢⬢⬢⬡⬡] | Input: 3.4K – Output: 800 | Turns: 4/8
     ```  
   - Emits via Open-WebUI’s event emitter when enabled.

---

## 🛠️ Example Usage

```python
from open_webui import OpenWebUI
from filter import Filter

app = OpenWebUI(config_path="config.yaml")
# The Filter will automatically hook into the request pipeline
app.add_filter(Filter())
app.run()
```

---

## 📝 Development

- **Linting:** `flake8 filter.py`  
- **Type-checking:** `mypy filter.py`  
- **Tests:** (You can mock `__event_emitter__` and verify status events.)

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🙋‍♂️ Author

**Taylor Wilsdon**  
– GitHub: [@taylorwilsdon](https://github.com/taylorwilsdon)  
– Feel free to open issues or submit pull requests!
