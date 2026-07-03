"""
Prompt Builder

Assembles complete prompts from registry templates.
Handles variable injection and message formatting.
"""
from datetime import datetime
from app.llm.base import LLMMessage
from app.prompts.registry import PromptRegistry


class PromptBuilder:
    """Assembles complete prompts from registry templates."""
    
    def build_rag_prompt(
        self,
        query: str,
        context_chunks: list[dict],
        conversation_history: list[LLMMessage] = [],
        company_name: str = "Our Company",
    ) -> list[LLMMessage]:
        """Build a complete RAG prompt with context and history."""
        
        # Get templates from registry
        system_template = PromptRegistry.get("document_agent_system")
        rag_template = PromptRegistry.get("rag_context")
        
        # Format system prompt with variables
        system_content = system_template["template"].format(
            company_name=company_name,
            current_date=datetime.now().strftime("%B %d, %Y"),
        )
        
        # Format context chunks for the LLM
        formatted_context = self._format_context(context_chunks)
        
        # Format user prompt with context and query
        user_content = rag_template["template"].format(
            context=formatted_context,
            query=query,
        )
        
        # Assemble standard LLM messages
        messages = [
            LLMMessage(role="system", content=system_content),
        ]
        
        # Add limited conversation history so we don't blow up token limits
        if conversation_history:
            messages.extend(conversation_history[-4:])
        
        messages.append(LLMMessage(role="user", content=user_content))
        
        return messages
    
    def _format_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks into numbered citation blocks."""
        if not chunks:
            return "No relevant documents found."
        
        formatted = []
        for i, chunk in enumerate(chunks, 1):
            formatted.append(
                f"[{i}] Source: {chunk.get('filename', 'Unknown')} "
                f"(Page {chunk.get('page_number', '?')})\n"
                f"{chunk.get('content', '')}"
            )
        
        return "\n\n---\n\n".join(formatted)