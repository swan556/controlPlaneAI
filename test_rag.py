from rag.retriever import RAGRetriever
import os

rag_retriever = RAGRetriever(min_grounding_score=0.60)
mock_policies_path = "mock_policies.md"
with open(mock_policies_path, "r") as f:
    rag_retriever.add_documents([f.read()])

text = "Welcome to our customer support."
contexts = rag_retriever.retrieve(text)
context_str = " ".join(contexts) if contexts else ""
result = rag_retriever.check_grounding(context_str, text)
print("Score:", result.grounding_score)
print("Grounded:", result.is_grounded)
