"""
Abstract Prompt Templates (Jergen)

Production-grade legal prompt bodies are intentionally excluded from source.
Store full prompts in a private environment secret or secure data store.
"""

BASE_JERGEN_PROMPT = "Internal proprietary prompt structure for {topic}."

JERGEN_PERSONAL_INFO_PROMPT = """
Internal proprietary extraction prompt for consumer personal information.
Use private legal prompt configuration in production.

<retrieved_context>
{rag_context}
</retrieved_context>
"""

JERGEN_ACCOUNTS_PROMPT = """
Internal proprietary extraction prompt for trade lines/accounts.
Use private legal prompt configuration in production.

<retrieved_context>
{rag_context}
</retrieved_context>
"""

JERGEN_INQUIRIES_PROMPT = """
Internal proprietary extraction prompt for hard inquiries.
Use private legal prompt configuration in production.

<retrieved_context>
{rag_context}
</retrieved_context>
"""

JERGEN_PUBLIC_RECORDS_PROMPT = """
Internal proprietary extraction prompt for public records.
Use private legal prompt configuration in production.

<retrieved_context>
{rag_context}
</retrieved_context>
"""

JERGEN_DRAFTING_LETTER_PROMPT = """
Internal proprietary dispute-letter assembly prompt.
Use private legal prompt configuration in production.

<writer_rag_context>
{$WRITER_RAG_CONTEXT}
</writer_rag_context>

<bureau>{$BUREAU}</bureau>
<consumer_name>{$CONSUMER_NAME}</consumer_name>
<dispute_data>{$DISPUTE_DATA}</dispute_data>
"""

JERGEN_DISAMBIGUATION_PROMPT = """
Internal proprietary creditor disambiguation prompt.
Use private legal prompt configuration in production.

<filter_rag_context>
{$FILTER_RAG_CONTEXT}
</filter_rag_context>
"""

JERGEN_RATIONALE_PROMPT = """
Internal proprietary dispute rationale prompt.
Use private legal prompt configuration in production.

<filter_rag_context>
{$FILTER_RAG_CONTEXT}
</filter_rag_context>
"""

JERGEN_AUDIT_EXPLANATION_PROMPT = """
Internal proprietary audit explanation prompt.
Use private legal prompt configuration in production.

<filter_rag_context>
{$FILTER_RAG_CONTEXT}
</filter_rag_context>
"""

JERGEN_FRIVOLOUS_REVIEW_PROMPT = """
Internal proprietary frivolous-review guardrail prompt.
Use private legal prompt configuration in production.

<guardrail_rag_context>
{$GUARDRAIL_RAG_CONTEXT}
</guardrail_rag_context>
"""

JERGEN_IRRELEVANT_REVIEW_PROMPT = """
Internal proprietary irrelevant-review guardrail prompt.
Use private legal prompt configuration in production.

<guardrail_rag_context>
{$GUARDRAIL_RAG_CONTEXT}
</guardrail_rag_context>
"""

JERGEN_RISK_ASSESSMENT_PROMPT = """
Internal proprietary tradeline risk-assessment prompt.
Use private legal prompt configuration in production.

<guardrail_rag_context>
{$GUARDRAIL_RAG_CONTEXT}
</guardrail_rag_context>
"""
