import os
import re
import yaml
import aiofiles
import aiohttp
from typing import List, Dict, Any
from pathlib import Path

from autogen_core.memory import Memory, MemoryContent, MemoryMimeType, ListMemory
from autogen_ext.memory.chromadb import ChromaDBVectorMemory, PersistentChromaDBVectorMemoryConfig, SentenceTransformerEmbeddingFunctionConfig

# Importing LangChain Splitter
from langchain_text_splitters import RecursiveCharacterTextSplitter

class SectionedDocumentIndexer:
    """
    Advanced indexer that splits Markdown documents by sections (headers),
    extracts embedded YAML metadata blocks, and then chunks the content.
    """

    def __init__(self, memory: Memory, chunk_size: int = 800, chunk_overlap: int = 100) -> None:
        self.memory = memory
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # Initialize the splitter for content within sections
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", " ", ""]
        )

    async def _fetch_content(self, source: str) -> str:
        """Fetch content from URL or file."""
        if source.startswith(("http://", "https://")):
            async with aiohttp.ClientSession() as session:
                async with session.get(source) as response:
                    return await response.text()
        else:
            async with aiofiles.open(source, "r", encoding="utf-8") as f:
                return await f.read()

    def _extract_yaml_block(self, text: str) -> tuple[Dict[str, Any], str]:
        """
        Extracts a YAML block enclosed in ```yaml ... ``` from the text.
        Returns (metadata_dict, cleaned_text).
        Only parses the FIRST yaml block found in the text chunk.
        """
        pattern = r"```yaml\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        
        metadata = {}
        cleaned_text = text
        
        if match:
            yaml_content = match.group(1)
            try:
                metadata = yaml.safe_load(yaml_content)
                # Remove the metadata block from the text to avoid indexing it as content
                cleaned_text = text.replace(match.group(0), "")
            except Exception as e:
                print(f"[Indexer] Warning: Failed to parse YAML block: {e}")
        
        # Flatten dictionary values to strings/ints/floats for ChromaDB compatibility
        flat_metadata = {}
        for k, v in metadata.items():
            if isinstance(v, (list, dict)):
                flat_metadata[k] = str(v)
            else:
                flat_metadata[k] = v
                
        return flat_metadata, cleaned_text.strip()

    def _split_by_headers(self, text: str) -> List[str]:
        """
        Splits text by markdown headers (Level 2 '## ').
        """
        parts = re.split(r'(?=\n## )', text)
        return [p.strip() for p in parts if p.strip()]

    async def index_documents(self, sources: List[str]) -> int:
        """Index documents into memory."""
        total_chunks = 0
        # print(f"[Memory] Indexing {len(sources)} documents with Metadata Extraction...")

        for source in sources:
            try:
                content = await self._fetch_content(source)
                
                # 1. Split document by sections (headers)
                sections = self._split_by_headers(content)
                
                for section_idx, section_text in enumerate(sections):
                    # 2. Extract Metadata from this section
                    section_metadata, cleaned_content = self._extract_yaml_block(section_text)
                    
                    if not cleaned_content:
                        continue 

                    # 3. Chunk the cleaned content
                    chunks = self.splitter.split_text(cleaned_content)

                    for chunk_idx, chunk in enumerate(chunks):
                        # 4. Merge metadata
                        chunk_metadata = {
                            "source": source,
                            "section_index": section_idx,
                            "chunk_index": chunk_idx
                        }
                        chunk_metadata.update(section_metadata)
                        
                        await self.memory.add(
                            MemoryContent(
                                content=chunk, 
                                mime_type=MemoryMimeType.TEXT, 
                                metadata=chunk_metadata
                            )
                        )

                    total_chunks += len(chunks)

            except Exception as e:
                pass # print(f"[Memory] Error indexing {source}: {str(e)}")

        print(f"[Memory] Indexed {total_chunks} chunks.")
        return total_chunks

async def create_memory_system(docs_path: str = "docs") -> List[Memory]:
    """
    Creates and initializes the memory system for the agent.
    Returns a list of Memory objects to be attached to the agent.
    """
    memories: List[Memory] = []

    # 1. User Preference Memory
    user_memory = ListMemory()
    await user_memory.add(MemoryContent(content="The user is a software engineer.", mime_type=MemoryMimeType.TEXT))
    memories.append(user_memory)
    
    # 2. RAG Memory (ChromaDB)
    if os.path.exists(docs_path) and os.path.isdir(docs_path):
        db_path = os.path.join(os.getcwd(), ".chromadb_store")
        
        rag_memory = ChromaDBVectorMemory(
            config=PersistentChromaDBVectorMemoryConfig(
                collection_name="agent_knowledge",
                persistence_path=db_path,
                k=3,
                score_threshold=0.4, # Higher threshold for mpnet
                embedding_function_config=SentenceTransformerEmbeddingFunctionConfig(
                    model_name="all-mpnet-base-v2"
                )
            )
        )
        
        # Collect sources
        sources = []
        for root, _, files in os.walk(docs_path):
            for file in files:
                if file.endswith((".md", ".txt", ".html")):
                    sources.append(os.path.join(root, file))
        
        if sources:
             await rag_memory.clear()
             # Use the Sectioned Document Indexer
             indexer = SectionedDocumentIndexer(memory=rag_memory)
             await indexer.index_documents(sources)
        
        memories.append(rag_memory)
    
    return memories

if __name__ == "__main__":
    import asyncio
    async def main():
        print("Initializing memory system...")
        mems = await create_memory_system()
        print(f"Created {len(mems)} memory modules.")
        
        # Test Query
        if len(mems) > 1:
            rag = mems[1] 
            print("Querying RAG...")
            results = await rag.query(MemoryContent(content="What are the python naming conventions?", mime_type=MemoryMimeType.TEXT))
            print(f"Results: {results}")

    asyncio.run(main())
