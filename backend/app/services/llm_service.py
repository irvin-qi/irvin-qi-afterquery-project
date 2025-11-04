"""LLM service for code analysis and Q&A."""

from __future__ import annotations

import asyncio
import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable

import httpx
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

_DOTENV_PATH = find_dotenv(filename=".env", raise_error_if_not_found=False, usecwd=True)
if _DOTENV_PATH:
    load_dotenv(_DOTENV_PATH)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate_analysis(
        self,
        rubric: str,
        diff_text: str,
        file_summary: str,
    ) -> dict:
        """Generate analysis from rubric and diffs.
        
        NOTE: rubric MUST always be included as primary context.
        
        Returns dict with 'text' and 'model' keys.
        """
        pass

    @abstractmethod
    async def answer_question(
        self,
        rubric: str,
        diff_text: str,
        file_summary: str,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        initial_analysis: Optional[str] = None,
    ) -> dict:
        """Answer a question about the codebase with full context.
        
        Args:
            rubric: The review rubric (ALWAYS included as primary context)
            diff_text: Full diff text
            file_summary: Summary of changed files
            question: User's question
            conversation_history: Previous messages in format [{"role": "user"/"assistant", "content": "..."}]
            initial_analysis: The initial LLM analysis if it exists
        
        Returns dict with 'text' and 'model' keys.
        """
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider for LLM functionality."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.api_base_url = "https://api.openai.com/v1"
        
        # Debug logging for API key (masked for security)
        if self.api_key:
            masked_key = f"{self.api_key[:7]}...{self.api_key[-4:]}" if len(self.api_key) > 11 else "***"
            logger.debug(f"🔑 OpenAI API key loaded: {masked_key} (length: {len(self.api_key)})")
        else:
            logger.error("❌ OPENAI_API_KEY not found in environment variables")
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        # Check if key looks valid (starts with sk-)
        if not self.api_key.startswith(("sk-", "sk-proj-")):
            logger.warning(f"⚠️  OpenAI API key format looks unusual (doesn't start with 'sk-' or 'sk-proj-'): {self.api_key[:10]}...")

    def _build_analysis_prompt(self, rubric: str, diff_text: str, file_summary: str) -> str:
        """Build the prompt for initial analysis."""
        return f"""You are an expert code reviewer analyzing a candidate's submission for a coding assessment.

## Review Rubric
The following rubric defines the criteria for evaluating this submission. Use this rubric as the primary reference for all your assessments:

{rubric}

## Code Changes
The candidate has made the following changes to the codebase:

### File Summary
{file_summary}

### Detailed Diffs
{diff_text}

## Your Task
Please provide:
1. A concise summary of what the code does and its overall quality
2. An evaluation of how well the code adheres to EACH criterion in the rubric above
3. Specific strengths and areas for improvement, referencing the rubric criteria
4. A final assessment score (1-5) if appropriate

Format your response in clear, structured markdown."""

    def _build_question_prompt(
        self,
        rubric: str,
        diff_text: str,
        file_summary: str,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        initial_analysis: Optional[str] = None,
    ) -> list[dict]:
        """Build the messages array for Q&A with conversation history."""
        messages = [
            {
                "role": "system",
                "content": "You are an expert code reviewer helping evaluate a candidate's submission for a coding assessment. Always reference the review rubric when answering questions about code quality.",
            },
            {
                "role": "user",
                "content": f"""## Review Rubric
Use this rubric as the primary reference for all evaluations:

{rubric}

## Code Changes Summary
The candidate has made the following changes to the codebase:

### File Summary
{file_summary}

### Detailed Diffs
{diff_text}

## Previous Analysis
{initial_analysis if initial_analysis else "No initial analysis available yet."}

## Conversation History
{self._format_conversation_history(conversation_history) if conversation_history else "No previous conversation."}

## Current Question
{question}

Please answer the question with reference to:
- The review rubric above
- The code changes shown
- Any relevant context from the previous analysis
- Be specific and cite examples from the code when possible""",
            },
        ]
        return messages

    def _format_conversation_history(self, history: list[dict]) -> str:
        """Format conversation history for inclusion in prompt."""
        if not history:
            return "No previous conversation."
        
        formatted = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted.append(f"{role.capitalize()}: {content}")
        
        return "\n\n".join(formatted)

    async def _make_api_call_with_retry(
        self,
        api_call: Callable[[], Awaitable[httpx.Response]],
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ) -> httpx.Response:
        """Make an API call with exponential backoff retry on rate limits.
        
        Args:
            api_call: Async function that returns an httpx.Response
            max_retries: Maximum number of retry attempts (default: 5)
            initial_backoff: Initial backoff delay in seconds (default: 1.0)
            max_backoff: Maximum backoff delay in seconds (default: 60.0)
        
        Returns:
            httpx.Response: The successful response
            
        Raises:
            httpx.HTTPStatusError: If all retries are exhausted or a non-retryable error occurs
        """
        last_exception = None
        consecutive_429s = 0  # Track consecutive rate limit errors
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"🔄 Retry attempt {attempt + 1}/{max_retries}")
                response = await api_call()
                response.raise_for_status()
                if attempt > 0:
                    logger.info(f"✅ Request succeeded on retry attempt {attempt + 1}")
                # Reset consecutive 429 counter on success
                consecutive_429s = 0
                return response
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                last_exception = exc
                
                # Retry on rate limit (429) and server errors (500, 502, 503, 504)
                if status_code in (429, 500, 502, 503, 504):
                    if status_code == 429:
                        consecutive_429s += 1
                        # If we've gotten multiple 429s in a row, be more conservative
                        if consecutive_429s >= 3:
                            logger.error(
                                f"❌ Rate limited repeatedly ({consecutive_429s} consecutive 429 errors). "
                                f"OpenAI rate limit is strict - please wait before trying again. "
                                f"Consider checking your OpenAI usage/quota at https://platform.openai.com/usage"
                            )
                            # For multiple 429s, wait longer before giving up
                            if attempt < max_retries - 1:
                                wait_time = min(30.0 + (attempt * 10), max_backoff)  # 30s, 40s, 50s, etc.
                                logger.warning(f"⏳ Waiting {wait_time:.0f}s before final retry...")
                                await asyncio.sleep(wait_time)
                                continue
                    
                    if attempt < max_retries - 1:  # Don't log on last attempt
                        # Check for Retry-After header (in seconds)
                        retry_after = exc.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait_time = float(retry_after)
                                logger.warning(
                                    f"⚠️  Rate limited (429). Server suggests waiting {wait_time}s. Retrying after {wait_time}s (attempt {attempt + 1}/{max_retries})"
                                )
                                # Log response body for debugging
                                try:
                                    error_body = exc.response.json()
                                    logger.debug(f"📄 Error response body: {error_body}")
                                    # Extract rate limit info if available
                                    if isinstance(error_body, dict):
                                        if "error" in error_body and isinstance(error_body["error"], dict):
                                            error_info = error_body["error"]
                                            logger.warning(
                                                f"📋 Rate limit details: {error_info.get('message', 'N/A')} "
                                                f"(type: {error_info.get('type', 'N/A')})"
                                            )
                                except:
                                    error_text = exc.response.text[:500]
                                    logger.debug(f"📄 Error response text: {error_text}")
                                await asyncio.sleep(wait_time)
                                continue
                            except (ValueError, TypeError):
                                pass  # Fall through to exponential backoff
                        
                        # For 429 errors, use longer initial backoff (5s instead of 1s)
                        # Exponential backoff: 5s, 10s, 20s, 40s, 60s for rate limits
                        # Or: 1s, 2s, 4s, 8s, 16s for server errors
                        if status_code == 429:
                            initial_wait = 5.0  # Start with 5 seconds for rate limits
                            wait_time = min(initial_wait * (2 ** attempt), max_backoff)
                        else:
                            wait_time = min(initial_backoff * (2 ** attempt), max_backoff)
                        
                        logger.warning(
                            f"⚠️  API error {status_code}. Retrying after {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                        )
                        # Log response body for debugging
                        try:
                            error_body = exc.response.json()
                            logger.debug(f"📄 Error response body: {error_body}")
                            if status_code == 429 and isinstance(error_body, dict):
                                if "error" in error_body and isinstance(error_body["error"], dict):
                                    error_info = error_body["error"]
                                    logger.warning(
                                        f"📋 Rate limit details: {error_info.get('message', 'N/A')}"
                                    )
                        except:
                            error_text = exc.response.text[:500]
                            logger.debug(f"📄 Error response text: {error_text}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Last attempt failed
                        if status_code == 429:
                            logger.error(
                                f"❌ Rate limit error persists after {max_retries} attempts. "
                                f"Please check your OpenAI rate limits and account quota at https://platform.openai.com/usage. "
                                f"Rate limits vary by tier and usage."
                            )
                        else:
                            logger.error(
                                f"❌ API call failed after {max_retries} attempts. Last error: {status_code}"
                            )
                        raise
                else:
                    # Non-retryable error (e.g., 400, 401, 403) - reset counter
                    consecutive_429s = 0
                    raise
            except Exception as exc:
                # For other exceptions (network errors, etc.), retry with backoff
                if attempt < max_retries - 1:
                    wait_time = min(initial_backoff * (2 ** attempt), max_backoff)
                    logger.warning(
                        f"API call failed with exception: {exc}. Retrying after {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    last_exception = exc
                    continue
                else:
                    logger.error(f"API call failed after {max_retries} attempts. Last error: {exc}")
                    raise
        
        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("API call failed for unknown reason")

    async def generate_analysis(
        self,
        rubric: str,
        diff_text: str,
        file_summary: str,
    ) -> dict:
        """Generate analysis using OpenAI API with automatic retry on rate limits."""
        logger.info("🔄 Starting LLM analysis generation")
        logger.debug(f"📋 Rubric length: {len(rubric)} chars")
        logger.debug(f"📝 Diff text length: {len(diff_text)} chars")
        logger.debug(f"📁 File summary length: {len(file_summary)} chars")
        
        prompt = self._build_analysis_prompt(rubric, diff_text, file_summary)
        logger.debug(f"📤 Total prompt length: {len(prompt)} chars")
        logger.debug(f"📤 Prompt preview (first 200 chars): {prompt[:200]}...")
        
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert code reviewer analyzing a candidate's submission for a coding assessment."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        
        # Estimate token count (rough approximation: 1 token ≈ 4 chars)
        estimated_tokens = sum(len(msg["content"]) for msg in request_payload["messages"]) // 4
        logger.info(f"🔢 Estimated token count: ~{estimated_tokens} tokens")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async def api_call():
                logger.info(f"🌐 Making API call to OpenAI ({self.model})")
                logger.debug(f"🔗 Endpoint: {self.api_base_url}/chat/completions")
                # Log masked API key for debugging (first 7 + last 4 chars)
                masked_key = f"{self.api_key[:7]}...{self.api_key[-4:]}" if self.api_key and len(self.api_key) > 11 else "None"
                logger.debug(f"🔑 Using API key: {masked_key} (full length: {len(self.api_key) if self.api_key else 0})")
                
                response = await client.post(
                    f"{self.api_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
                logger.debug(f"📥 Response status: {response.status_code}")
                return response
            
            try:
                response = await self._make_api_call_with_retry(api_call)
                data = response.json()
                
                # Log response metadata
                if "usage" in data:
                    usage = data["usage"]
                    logger.info(f"✅ API call successful. Tokens used: {usage.get('total_tokens', 'unknown')} (prompt: {usage.get('prompt_tokens', 'unknown')}, completion: {usage.get('completion_tokens', 'unknown')})")
                
                content = data["choices"][0]["message"]["content"]
                logger.info(f"📄 Generated analysis length: {len(content)} chars")
                
                return {
                    "text": content,
                    "model": self.model,
                }
            except Exception as e:
                logger.error(f"❌ Failed to generate analysis: {type(e).__name__}: {e}")
                raise

    async def answer_question(
        self,
        rubric: str,
        diff_text: str,
        file_summary: str,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        initial_analysis: Optional[str] = None,
    ) -> dict:
        """Answer a question using OpenAI API with full context and automatic retry on rate limits."""
        messages = self._build_question_prompt(
            rubric, diff_text, file_summary, question, conversation_history, initial_analysis
        )
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async def api_call():
                return await client.post(
                    f"{self.api_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.3,
                    },
                )
            
            response = await self._make_api_call_with_retry(api_call)
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            return {
                "text": content,
                "model": self.model,
            }


def get_llm_provider() -> LLMProvider:
    """Factory function to get the configured LLM provider."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    if provider == "openai":
        return OpenAIProvider(model=os.getenv("OPENAI_MODEL", "gpt-4"))
    elif provider == "anthropic":
        # TODO: Implement AnthropicProvider when needed
        raise NotImplementedError("Anthropic provider not yet implemented")
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
