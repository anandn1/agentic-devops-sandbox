# Self-Healing Code Agent 

An autonomous agentic workflow that writes, executes, and fixes its own code using Microsoft AutoGen and Docker sandboxing.

##  How it Works
1. **The Developer Agent** writes a Python script to solve a task.
2. **The Executor (Docker)** runs the code in an isolated container (`python:3.9-slim`).
3. **The Feedback Loop:** If the code fails (e.g., missing dependencies), the agent reads the error from `stderr`, refactors the code, and retries automatically until it passes.

##  Tech Stack
- **Framework:** Microsoft AutoGen
- **Environment:** Docker (for safe execution)
- **Model:** GPT-4o / Llama 3

##  Setup
1. Clone the repo
2. `pip install -r requirements.txt`
3. Add your keys to `.env`
4. Run `python main.py`