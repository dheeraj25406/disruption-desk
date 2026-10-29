# Architecture notes

LangGraph owns the workflow lifecycle. Typed shared state includes case evidence, alternative records, deterministic decisions, trace events, and the final Pydantic report. Nodes call registered LangChain tools for database access. The policy engine is plain Python and remains authoritative. Gemini receives verified data and policy outcomes to produce concise interpretation; provider errors propagate to a failed run. There is no LLM fallback.
