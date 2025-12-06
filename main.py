import asyncio
import os
import re
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv
from autogen_core import DefaultTopicId, MessageContext, RoutedAgent, default_subscription, message_handler
from autogen_core.code_executor import CodeBlock, CodeExecutor
from autogen_core import SingleThreadedAgentRuntime
from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from autogen_ext.models.azure import AzureAIChatCompletionClient
from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
from azure.core.credentials import AzureKeyCredential

# Load environment variables
load_dotenv()

@dataclass
class Message:
    content: str

def confirm_execution(code_to_execute: str) -> bool:
    print(f"\nExample of code to execute:\n{code_to_execute}\n")
    response = input("Do you want to execute this code? (yes/no): ").strip().lower()
    return response == "yes"

def extract_markdown_code_blocks(markdown_text: str) -> List[CodeBlock]:
    pattern = re.compile(r"```(?:\s*([\w\+\-]+))?\n([\s\S]*?)```")
    matches = pattern.findall(markdown_text)
    code_blocks: List[CodeBlock] = []
    for match in matches:
        language = match[0].strip() if match[0] else ""
        code_content = match[1]
        code_blocks.append(CodeBlock(code=code_content, language=language))
    return code_blocks

@default_subscription
class Assistant(RoutedAgent):
    def __init__(self, model_client: ChatCompletionClient) -> None:
        super().__init__("Assistant")
        self._model_client = model_client
        self._chat_history: List[LLMMessage] = [
            SystemMessage(
                content="""You are an Autonomous DevOps Engineer.
                
                RULES:
                1. If you need to save a file, you MUST use Bash commands (e.g., `echo` or `cat`) to create it.
                2. If a system tool (like `git`) is missing, install it using `apt-get` (you have root access).
                3. Always verify operations (e.g., check file existence, check git log).
                4. Output "TERMINATE" only when the task is fully complete.
                """
            )
        ]

    @message_handler
    async def handle_message(self, message: Message, ctx: MessageContext) -> None:
        self._chat_history.append(UserMessage(content=message.content, source="user"))
        result = await self._model_client.create(self._chat_history)
        print(f"\n{'-'*80}\nAssistant:\n{result.content}")
        self._chat_history.append(AssistantMessage(content=result.content, source="assistant"))
        await self.publish_message(Message(content=result.content), DefaultTopicId())

@default_subscription
class Executor(RoutedAgent):
    def __init__(self, code_executor: CodeExecutor) -> None:
        super().__init__("Executor")
        self._code_executor = code_executor

    @message_handler
    async def handle_message(self, message: Message, ctx: MessageContext) -> None:
        code_blocks = extract_markdown_code_blocks(message.content)
        if code_blocks:
            code_text = "\n".join([block.code for block in code_blocks])
            
            if not confirm_execution(code_text):
                 print(f"\n{'-'*80}\nExecutor:\nCode execution rejected by user.")
                 await self.publish_message(Message(content="Code execution was not approved. Reason: User input"), DefaultTopicId())
                 return

            result = await self._code_executor.execute_code_blocks(
                code_blocks, cancellation_token=ctx.cancellation_token
            )
            print(f"\n{'-'*80}\nExecutor:\n{result.output}")
            await self.publish_message(Message(content=result.output), DefaultTopicId())

async def main():
    # Configuration for GitHub Models (Azure AI)
    model_client = AzureAIChatCompletionClient(
        model="gpt-4o",
        endpoint="https://models.inference.ai.azure.com",
        credential=AzureKeyCredential(os.environ.get("GITHUB_TOKEN")),
        model_info={
            "json_output": True,
            "function_calling": True,
            "vision": True,
            "family": "gpt-4",
            "structured_output": True,
        },
    )

    work_dir = "coding_workspace"
    os.makedirs(work_dir, exist_ok=True)

    runtime = SingleThreadedAgentRuntime()

    async with DockerCommandLineCodeExecutor(
        image="python:3.12",
        timeout=60,
        work_dir=work_dir,
    ) as executor:
        
        await Assistant.register(
            runtime, "assistant", lambda: Assistant(model_client=model_client)
        )
        await Executor.register(
            runtime, "executor", lambda: Executor(code_executor=executor)
        )

        runtime.start()

        task_prompt = """
        Initialize a Git repository.
        1. Create a '.gitignore' file that ignores '*.python', '*.bash', and '*.sh' files.
        2. Initialize git and configure user 'bot@ai.com'.
        3. Create 'app.py' that prints "Deployment Successful".
        4. Commit 'app.py' (and only app.py).
        5. Verify with 'git log'.
        """
        
        print(f"Starting Self-Healing Agent (v0.7.5 New Arch - Core) in '{work_dir}'...")
        await runtime.publish_message(Message(content=task_prompt), DefaultTopicId())

        await runtime.stop_when_idle()
    
    await model_client.close()

if __name__ == "__main__":
    asyncio.run(main())