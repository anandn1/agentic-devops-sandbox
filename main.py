import asyncio
import os
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent, CodeExecutorAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_ext.models.azure import AzureAIChatCompletionClient
from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from autogen_core import EVENT_LOGGER_NAME
from autogen_core.logging import LLMCallEvent

import logging
import datetime
from pathlib import Path
from memory import create_memory_system
# Load environment variables
load_dotenv()

# Configure Logging
# 1. File Handler (Detailed Debug Logs)
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"agent_run_{timestamp}.log"
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# 2. Console Handler (Minimal Info)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR) # Only show errors on console (and custom prints)

# 3. Setup Root Logger
root_logger = logging.getLogger()
# Clear any default handlers (like those added by basicConfig or libraries)
if root_logger.handlers:
    root_logger.handlers.clear()

root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# 4. Specific Loggers
openai_logger = logging.getLogger("openai")
openai_logger.setLevel(logging.INFO)
http_logger = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
http_logger.setLevel(logging.DEBUG)

class LLMUsageTracker(logging.Handler):
    def __init__(self) -> None:
        """Logging handler that tracks the number of tokens used in the prompt and completion."""
        super().__init__()
        self._prompt_tokens = 0
        self._completion_tokens = 0

    @property
    def tokens(self) -> int:
        return self._prompt_tokens + self._completion_tokens

    @property
    def prompt_tokens(self) -> int:
        return self._prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self._completion_tokens

    def reset(self) -> None:
        self._prompt_tokens = 0
        self._completion_tokens = 0

    def emit(self, record: logging.LogRecord) -> None:
        """Emit the log record. To be used by the logging module."""
        try:
            # Use the StructuredMessage if the message is an instance of it
            if isinstance(record.msg, LLMCallEvent):
                event = record.msg
                self._prompt_tokens += event.prompt_tokens
                self._completion_tokens += event.completion_tokens
        except Exception:
            self.handleError(record)


def load_prompt(filename):
    return (Path("prompts") / filename).read_text()

async def run_team_cycle(work_dir, model_client, memories, prompts):
    """
    Executes one cycle of the agent team.
    Returns the result if successful, or raises exceptions.
    """
    manager_prompt, backend_prompt, frontend_prompt, qa_prompt, task_prompt = prompts

    # 1. Define Agents (Re-created fresh each cycle to clear chat history)
    manager = AssistantAgent(
        name="Manager",
        description="The Planning Agent. Breaks down complex tasks into subtasks for the team. First to engage.",
        model_client=model_client,
        system_message=manager_prompt,
        memory=memories
    )

    backend_dev = AssistantAgent(
        name="Backend_Dev",
        description="The Backend Developer. Writes app.py using Flask and bash commands for file creation.",
        model_client=model_client,
        system_message=backend_prompt,
    )

    frontend_dev = AssistantAgent(
        name="Frontend_Dev",
        description="The Frontend Developer. Writes templates/index.html using bash commands.",
        model_client=model_client,
        system_message=frontend_prompt,
    )
    
    qa_engineer = AssistantAgent(
        name="QA_Engineer",
        description="The QA Engineer. Verifies the app runs and checks for correctness.",
        model_client=model_client,
        system_message=qa_prompt,
    )

    # 2. Context Manager for Docker
    async with DockerCommandLineCodeExecutor(
        image="flask-agent-env", 
        work_dir=work_dir,
        timeout=60
    ) as code_executor:
        
        executor_agent = CodeExecutorAgent(
            name="Executor",
            description="The Tool Executor. Executes bash and python code blocks.",
            code_executor=code_executor,
        )

        participants = [manager, backend_dev, frontend_dev, qa_engineer, executor_agent]
        termination = TextMentionTermination("TERMINATE_TASK")

        # Custom Selector Function
        def custom_selector(messages) -> str | None:
            try:
                if not messages: return None
                last_msg = messages[-1]
                last_speaker = getattr(last_msg, "source", "Unknown")
                print(f">> Agent Working: {last_speaker}")

                if last_speaker == "Executor":
                    for m in reversed(messages[:-1]):
                        src = getattr(m, "source", "Unknown")
                        if src in ["Backend_Dev", "Frontend_Dev", "QA_Engineer"]:
                            return src
                    return "Manager"

                if last_speaker in ["Backend_Dev", "Frontend_Dev", "QA_Engineer"]:
                    content = getattr(last_msg, "content", "")
                    if last_speaker == "Backend_Dev" and ("<html>" in content or "<!DOCTYPE html>" in content):
                        return "Frontend_Dev"
                    if "```" in content:
                        return "Executor"
                
                if last_speaker == "QA_Engineer" and "PASS" in getattr(last_msg, "content", ""):
                    return "Manager"

                return None 
            except Exception as e:
                print(f"[ERROR] Selector Exception: {e}")
                return None

        team = SelectorGroupChat(
            participants,
            model_client=model_client,
            termination_condition=termination,
            max_turns=20, 
            selector_func=custom_selector,
            selector_prompt="Select the next speaker. Chat History: {history}. Output only the role name."
        )

        print("Starting Agent Team Cycle...")
        return await team.run(task=task_prompt)


async def main():
    # Model Configuration
    model_client = AzureAIChatCompletionClient(
        model="gpt-4o",
        endpoint="https://models.inference.ai.azure.com",
        credential=AzureKeyCredential(os.environ.get("GITHUB_ACCESS_TOKEN1")),
        model_info={
            "json_output": False,
            "function_calling": True,
            "vision": True,
            "family": "gpt-4",
            "structured_output": False, 
        },
    )

    # Setup LLM Usage Logger
    logger = logging.getLogger(EVENT_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    llm_usage = LLMUsageTracker()
    logger.addHandler(llm_usage)

    work_dir = Path("full_stack_workspace").resolve()
    work_dir.mkdir(exist_ok=True)

    # Load Prompts
    prompts = (
        load_prompt("manager.txt"),
        load_prompt("backend_dev.txt"),
        load_prompt("frontend_dev.txt"),
        load_prompt("qa_engineer.txt"),
        load_prompt("task.txt")
    )

    # Initialize Memory System
    memories = await create_memory_system()

    # --- MAIN LOOP FOR CONTEXT RESET ---
    max_resets = 3
    reset_count = 0

    while True:
        try:
            if reset_count > 0:
                print(f"\n[System] Context Reset #{reset_count}. Resuming task with fresh agent memory...")
                # Optional: Append a system note to the task prompt to inform Manager of the reset
                # prompts = (prompts[0], prompts[1], prompts[2], prompts[3], prompts[4] + "\n[SYSTEM NOTE: Previous context was reset due to length. Please scan existing files to resume work.]")

            result = await run_team_cycle(work_dir, model_client, memories, prompts)
            
            # Print Final Result
            print(f"\n{'-'*20} Task Result {'-'*20}")
            for message in result.messages:
                script_source = getattr(message, "source", "Unknown")
                print(f"\n{'-'*20} {script_source} {'-'*20}")
                if hasattr(message, "content"):
                    print(message.content)
                elif hasattr(message, "models_usage"):
                    print(f"[Task Result] Usage: {message.models_usage}")
                else:
                    print(message)
            
            print(f"\n[System] Task Completed Successfully.")
            break # Exit loop on success

        except HttpResponseError as e:
            # Check for 429 Rate Limit
            if e.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                print(f"\n[System] Rate Limit Exceeded (429). Retry-After: {retry_after}s")
                
                if retry_after < 60:
                    print(f"[System] Wait time is short. Sleeping for {retry_after}s and retrying...")
                    import time
                    time.sleep(retry_after + 1) # Add buffer
                    continue
                else:
                    hours = retry_after / 3600
                    print(f"[System] Wait time is too long ({hours:.2f} hours). Exiting .")
                    print(f"[System] You can resume the agent after this duration.")
                    break

            # Check for Token Limit Error (413 Payload Too Large)
            error_msg = str(e).lower()
            if "tokens_limit_reached" in error_msg or e.status_code == 413:
                print(f"\n[System] CRITICAL: Token Limit Reached during cycle.")
                reset_count += 1
                if reset_count > max_resets:
                    print(f"[System] Max resets ({max_resets}) reached. Aborting.")
                    break
                print("[System] Triggering Context Reset (Clearing Chat History)...")
                continue # Restart loop
            else:
                print(f"\n[ERROR] Unhandled Azure API Error: {e}")
                break
        
        except Exception as e:
            if "GroupChatError" in str(type(e)):
                 # Sometimes GroupChatError wraps the underlying API error
                 print(f"\n[System] GroupChatError detected. Retrying might fix transient issues.")
                 # Decide whether to reset or just retry. For now, let's treat it as a crash and break, 
                 # unless we parse the inner error. 
                 # Given the user's log, the inner error WAS tokens_limit_reached.
                 print(f"[ERROR] Detail: {e}")
                 break
            
            print(f"\n[ERROR] Unexpected error: {e}")
            break

    # Stats Output
    print(f"\n{'-'*20} Token Usage {'-'*20}")
    print(f"Prompt Tokens: {llm_usage.prompt_tokens}")
    print(f"Completion Tokens: {llm_usage.completion_tokens}")
    print(f"Total Tokens: {llm_usage.tokens}")

    await model_client.close()

if __name__ == "__main__":
    asyncio.run(main())
