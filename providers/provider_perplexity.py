"""
Perplexity Provider - Integration with Perplexity AI services

This module provides integration with Perplexity AI, which offers search-enhanced LLMs
that can provide up-to-date information along with citations.
"""

import logging
import time
import json
import os
import re
from typing import Dict, List, Any, Optional, Union

# Since Perplexity uses OpenAI-compatible API, we use the openai client
try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from provider_base import AIProvider

# Setup logging
logger = logging.getLogger("PerplexityProvider")

class PerplexityProvider(AIProvider):
    """Provider for Perplexity AI's search-enhanced language models"""
    
    def __init__(self):
        """Initialize the Perplexity provider"""
        self.client = None
        self.config = {}
        self.models = []
        self.default_model = "pplx-70b-online"  # Default model with online search
        self.initialized = False
        self.base_url = "https://api.perplexity.ai"
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the provider with the given configuration
        
        Args:
            config: Perplexity configuration including API key
            
        Returns:
            True if initialization was successful
        """
        if not OPENAI_AVAILABLE:
            logger.error("OpenAI package is not installed. Please install with: pip install openai")
            return False
        
        self.config = config
        
        # Get API key from config or environment
        api_key = config.get("api_key") or os.environ.get("PERPLEXITY_API_KEY")
        if not api_key:
            logger.error("No Perplexity API key provided")
            return False
        
        try:
            # Initialize the client with the Perplexity base URL
            self.client = OpenAI(
                api_key=api_key,
                base_url=self.base_url
            )
            
            # Set default model
            self.default_model = config.get("default_model", "pplx-70b-online")
            
            # Available models (as of April 2024)
            self.models = [
                "pplx-7b-online",
                "pplx-70b-online",
                "pplx-7b-chat",
                "pplx-70b-chat",
                "llama-3-70b-instruct",
                "mistral-7b-instruct",
                "mixtral-8x7b-instruct"
            ]
            
            # Make a test call to verify API key
            try:
                response = self.client.chat.completions.create(
                    model=self.default_model,
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=10
                )
                if response:
                    self.initialized = True
                    logger.info(f"Perplexity provider initialized with model {self.default_model}")
                    return True
            except Exception as e:
                logger.error(f"Failed to make test call to Perplexity API: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to initialize Perplexity provider: {str(e)}")
            return False
    
    def send_query(self, 
                  query: str, 
                  context: Optional[Dict[str, Any]] = None, 
                  options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a query to Perplexity
        
        Args:
            query: The user's query text
            context: Additional context for the query
            options: Perplexity-specific options for this query
            
        Returns:
            Response dictionary
        """
        if not self.initialized or not self.client:
            return {
                "success": False,
                "response": "Perplexity provider is not initialized",
                "error": "Provider not initialized"
            }
        
        # Default response in case of error
        response_data = {
            "success": False,
            "response": "",
            "error": None,
            "usage": {},
            "metadata": {}
        }
        
        # Extract options
        options = options or {}
        context = context or {}
        
        try:
            # Get model to use
            model = options.get("model") or self.default_model
            if model not in self.models:
                model = self.default_model
            
            # Prepare message history
            messages = self._prepare_messages(query, context)
            
            # Extract additional parameters
            temperature = options.get("temperature", 0.7)
            max_tokens = options.get("max_tokens", 1024)
            
            # Call the API
            start_time = time.time()
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            end_time = time.time()
            
            # Extract response text
            response_text = response.choices[0].message.content if response.choices else ""
            
            # Extract sources/citations if present
            sources = self._extract_sources(response_text)
            
            # Format response with proper source formatting if needed
            if sources and not options.get("raw_response", False):
                formatted_response = self._format_response_with_sources(response_text, sources)
            else:
                formatted_response = response_text
            
            # Calculate token usage and cost
            usage = {}
            if hasattr(response, 'usage'):
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "estimated_cost": self._calculate_cost(response.usage, model)
                }
            
            return {
                "success": True,
                "response": formatted_response,
                "raw_response": response,
                "sources": sources,
                "usage": usage,
                "metadata": {
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time": end_time - start_time
                }
            }
            
        except Exception as e:
            logger.error(f"Error calling Perplexity API: {str(e)}")
            return {
                "success": False,
                "response": f"Error: {str(e)}",
                "error": str(e),
                "usage": {},
                "metadata": {}
            }
    
    def _prepare_messages(self, query, context):
        """
        Prepare message history for the Perplexity API
        
        Args:
            query: User query
            context: Context including history
            
        Returns:
            List of message dictionaries
        """
        messages = []
        
        # Add system message if provided
        system_prompt = self.config.get("system_prompt") or context.get("system_prompt")
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        else:
            # Default system prompt for search-enhanced models
            if "online" in self.default_model:
                messages.append({
                    "role": "system",
                    "content": "Vous êtes un assistant IA qui a accès à des informations à jour grâce aux capacités "
                              "de recherche en ligne. Fournissez des réponses précises et actualisées en citant vos sources."
                })
        
        # Add conversation history if present (limited)
        history = context.get("relevant_history", [])
        # Only use last 2 history items to keep context smaller for search models
        for item in history[-2:]:
            if item.get("type") == "query":
                messages.append({
                    "role": "user",
                    "content": item.get("text", "")
                })
            elif item.get("type") == "result":
                messages.append({
                    "role": "assistant",
                    "content": item.get("response", "")
                })
        
        # Add the current query
        messages.append({
            "role": "user",
            "content": query
        })
        
        return messages
    
    def _extract_sources(self, response_text):
        """
        Extract sources/citations from the response
        
        Args:
            response_text: Text response from Perplexity
            
        Returns:
            List of sources
        """
        sources = []
        
        # Look for source patterns like [1], [2], etc.
        source_refs = re.findall(r'\[\d+\]', response_text)
        
        # Extract source URLs - look for URLs after references
        for ref in source_refs:
            # Search for the reference followed by a URL or text
            pattern = rf'{re.escape(ref)}[:\s]+([^\s\[\]]+(?:\.[a-zA-Z]+)+[^\s\[\]]*)'
            urls = re.findall(pattern, response_text)
            if urls:
                sources.append({
                    "ref": ref,
                    "url": urls[0]
                })
        
        # Also look for footnotes section
        footnotes_match = re.search(r'Sources?:?\s*\n+((?:.+\n*)+)', response_text)
        if footnotes_match:
            footnotes = footnotes_match.group(1)
            # Extract numbered sources
            numbered_sources = re.findall(r'(?:\[?(\d+)\]?\.?\s+)([^\n]+)', footnotes)
            for num, source in numbered_sources:
                # Check if we already have this reference
                ref = f"[{num}]"
                if not any(s["ref"] == ref for s in sources):
                    # Extract URL if present
                    url_match = re.search(r'(https?://[^\s]+)', source)
                    url = url_match.group(1) if url_match else source
                    sources.append({
                        "ref": ref,
                        "url": url
                    })
        
        return sources
    
    def _format_response_with_sources(self, response_text, sources):
        """
        Format the response text with properly formatted sources
        
        Args:
            response_text: Original response text
            sources: List of extracted sources
            
        Returns:
            Formatted response
        """
        # Check if there's a footnote section to remove
        footnote_section = re.search(r'\n+Sources?:?\s*\n+((?:.+\n*)+)
        , response_text)
        if footnote_section:
            # Remove the footnote section
            cleaned_text = response_text[:footnote_section.start()]
        else:
            cleaned_text = response_text
        
        # Add a formatted sources section at the end
        if sources:
            formatted_text = cleaned_text.strip() + "\n\n## Sources\n"
            for source in sources:
                formatted_text += f"{source['ref']} {source['url']}\n"
            return formatted_text
        else:
            return cleaned_text
        