import asyncio
import os
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent, CodeExecutorAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_ext.models.azure import AzureAIChatCompletionClient
from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
from azure.core.credentials import AzureKeyCredential
from autogen_core import EVENT_LOGGER_NAME
from autogen_core.logging import LLMCallEvent

import logging
# Load environment variables
load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.DEBUG)
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
    with open(os.path.join("prompts", filename), "r") as f:
        return f.read()

async def main():
    # Model Configuration
    model_client = AzureAIChatCompletionClient(
        model="gpt-4o",
        endpoint="https://models.inference.ai.azure.com",
        credential=AzureKeyCredential(os.environ.get("GITHUB_TOKEN")),
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

    work_dir = os.path.abspath("full_stack_workspace")
    os.makedirs(work_dir, exist_ok=True)

    # Load Prompts
    manager_prompt = load_prompt("manager.txt")
    backend_prompt = load_prompt("backend_dev.txt")
    frontend_prompt = load_prompt("frontend_dev.txt")
    qa_prompt = load_prompt("qa_engineer.txt")
    task_prompt = load_prompt("task.txt")

    # 1. Define Agents
    
    # Manager (Planning Agent)
    manager = AssistantAgent(
        name="Manager",
        description="The Planning Agent. Breaks down complex tasks into subtasks for the team. First to engage.",
        model_client=model_client,
        system_message=manager_prompt
    )

    # Backend_Dev
    backend_dev = AssistantAgent(
        name="Backend_Dev",
        description="The Backend Developer. Writes app.py using Flask and bash commands for file creation.",
        model_client=model_client,
        system_message=backend_prompt
    )

    # Frontend_Dev
    frontend_dev = AssistantAgent(
        name="Frontend_Dev",
        description="The Frontend Developer. Writes templates/index.html using bash commands.",
        model_client=model_client,
        system_message=frontend_prompt
    )
    
    # QA_Engineer
    qa_engineer = AssistantAgent(
        name="QA_Engineer",
        description="The QA Engineer. Verifies the app runs and checks for correctness.",
        model_client=model_client,
        system_message=qa_prompt
    )

    # Executor (DOCKER)
    async with DockerCommandLineCodeExecutor(
        image="flask-agent-env", # Pre-baked image
        work_dir=work_dir,
        timeout=60
    ) as code_executor:
        
        executor_agent = CodeExecutorAgent(
            name="Executor",
            description="The Tool Executor. Executes bash and python code blocks.",
            code_executor=code_executor,
        )

        # 2. Define Team (SelectorGroupChat)
        participants = [manager, backend_dev, frontend_dev, qa_engineer, executor_agent]
        
        # Termination condition
        termination = TextMentionTermination("TERMINATE")

        # Custom Selector Function to enforce "Dev -> Executor -> Dev" loop
        def custom_selector(messages) -> str | None:
            # print(f"[DEBUG] Selector called. Messages count: {len(messages)}")
            if not messages:
                return None
            
            last_msg = messages[-1]
            last_speaker = getattr(last_msg, "source", "Unknown")
            # print(f"[DEBUG] Last speaker: {last_speaker}")

            # 1. If Executor just finished -> Hand back to the previous developer
            if last_speaker == "Executor":
                # Search backwards for the last dev who spoke
                for m in reversed(messages[:-1]):
                    src = getattr(m, "source", "Unknown")
                    if src in ["Backend_Dev", "Frontend_Dev", "QA_Engineer"]:
                        print(f"[DEBUG] Executor done. Returning to: {src}")
                        return src
                return "Manager"

            # 2. If Developer wrote code -> Force Executor
            if last_speaker in ["Backend_Dev", "Frontend_Dev", "QA_Engineer"]:
                content = getattr(last_msg, "content", "")
                if "```" in content:
                    print("[DEBUG] Code detected. Forcing Executor.")
                    return "Executor"
            
            # 3. If QA Passed -> Manager (to terminate)
            if last_speaker == "QA_Engineer" and "PASS" in getattr(last_msg, "content", ""):
                 print("[DEBUG] QA Passed. Returning to Manager.")
                 return "Manager"

            # print("[DEBUG] Returning None (Let LLM decide)")
            return None # Let the LLM decide (e.g., Manager -> Dev)

        team = SelectorGroupChat(
            participants,
            model_client=model_client,
            termination_condition=termination,
            max_turns=20, # Optimized for speed
            selector_func=custom_selector,
            # Explicit selector prompt to guide the model when func returns None
            selector_prompt="""Select the next speaker. 
            Available roles: {roles}. 
            Chat History: {history}. 
            Output only the role name."""
        )

        print(f"Starting High-Level Selector Squad (Docker) in '{work_dir}'...")
        
        # 4. Run using .run()
        result = await team.run(task=task_prompt)
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
        
        print(f"\n{'-'*20} Token Usage {'-'*20}")
        print(f"Prompt Tokens: {llm_usage.prompt_tokens}")
        print(f"Completion Tokens: {llm_usage.completion_tokens}")
        print(f"Total Tokens: {llm_usage.tokens}")

    await model_client.close()

if __name__ == "__main__":
    asyncio.run(main())
