# Open-WebUI Tools

A collection of extensions and agents to enhance your Open-WebUI experience. This repository contains:

- **Chat Context Window Tracker**  
  A high-throughput, low-latency filter that monitors token usage and conversation turns.  
  ▶️ See [Open-WebUI Context Counter & Turn Tracker Function README](README_OPEN_WEBUI_CONTEXT_COUNTER_FUNCTION.md)

- **Jira Agent**  
  Search, view, create, comment on, and manage Jira issues directly from Open-WebUI.  
  ▶️ See [Open-WebUI Jira Agent README](README_JIRA.md)

---

## Getting Started

1. **Clone the repo**  
   ```bash
   git clone https://github.com/taylorwilsdon/open-webui-tools.git
   cd open-webui-tools
   ```

2. **Install dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

3. **Pick a tool**  
   - To enable the Context Window Tracker, follow the instructions in `filter/README.md`.  
   - To use the Jira Agent, follow the instructions in `README_JIRA.md`.

---

## Contributing

1. Fork the repository  
2. Create a feature branch (`git checkout -b feature/XYZ`)  
3. Commit your changes (`git commit -m "Add XYZ"`)  
4. Push to your fork (`git push origin feature/XYZ`)  
5. Open a pull request

Please read individual README files for coding standards, testing guidelines, and configuration examples.

---

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
