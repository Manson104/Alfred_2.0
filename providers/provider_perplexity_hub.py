"""
Perplexity Hub Provider - Unified access to multiple AI models via Perplexity subscription

This module provides a single interface to access multiple AI models including:
- Claude 3.7 Sonnet
- GPT-4o
- Perplexity's native models with online search

All through a Perplexity Pro subscription.
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
logger = logging.getLogger("PerplexityHubProvider")

class PerplexityHubProvider(AIProvider):
    """
    Provider that uses Perplexity Pro subscription to access multiple AI models
    including Claude, GPT and Perplexity's native models
    """
    
    def __init__(self):
        """Initialize the Perplexity Hub provider"""
        self.client = None
        self.config = {}
        self.models = []
        self.default_model = "claude-3-7-sonnet"  # Default to Claude 3.7
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
            
            # Set default model from config
            self.default_model = config.get("default_model", "claude-3-7-sonnet")
            
            # Set available models from config or use defaults
            self.models = config.get("available_models", [
                # Claude models
                "claude-3-7-sonnet",
                "claude-3-5-sonnet",
                "claude-3-opus",
                "claude-3-sonnet",
                "claude-3-haiku",
                
                # GPT models
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo",
                
                # Perplexity models
                "pplx-7b-online",
                "pplx-70b-online",
                "pplx-7b-chat",
                "pplx-70b-chat",
                
                # Other models sometimes available
                "llama-3-70b-instruct",
                "mistral-7b-instruct",
                "mixtral-8x7b-instruct"
            ])
            
            # Make a test call to verify API key
            try:
                response = self.client.chat.completions.create(
                    model=self.default_model,
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=10
                )
                if response:
                    self.initialized = True
                    logger.info(f"Perplexity Hub provider initialized with {len(self.models)} available models")
                    logger.info(f"Default model: {self.default_model}")
                    return True
            except Exception as e:
                logger.error(f"Failed to make test call to Perplexity API: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to initialize Perplexity Hub provider: {str(e)}")
            return False
    
    def send_query(self, 
                  query: str, 
                  context: Optional[Dict[str, Any]] = None, 
                  options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a query to the appropriate model via Perplexity
        
        Args:
            query: The user's query text
            context: Additional context for the query
            options: Provider-specific options for this query
            
        Returns:
            Response dictionary
        """
        if not self.initialized or not self.client:
            return {
                "success": False,
                "response": "Perplexity Hub provider is not initialized",
                "error": "Provider not initialized"
            }
        
        # Extract options
        options = options or {}
        context = context or {}
        
        # Determine which model to use
        model = options.get("model") or self._select_best_model(query, context)
        if model not in self.models:
            logger.warning(f"Requested model {model} not available, falling back to {self.default_model}")
            model = self.default_model
        
        # Log which model is being used
        logger.info(f"Using model {model} for query")
        
        # Determine if this is for online search
        is_online_model = "online" in model
        needs_citations = options.get("citations", is_online_model)
        
        try:
            # Prepare message history
            messages = self._prepare_messages(query, context, model)
            
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
            
            # Extract sources/citations if needed
            sources = self._extract_sources(response_text) if needs_citations else []
            
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
                "sources": sources if needs_citations else [],
                "usage": usage,
                "metadata": {
                    "model": model,
                    "model_family": self._get_model_family(model),
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time": end_time - start_time,
                    "is_online_search": is_online_model
                }
            }
            
        except Exception as e:
            logger.error(f"Error calling Perplexity API with model {model}: {str(e)}")
            return {
                "success": False,
                "response": f"Error: {str(e)}",
                "error": str(e),
                "usage": {},
                "metadata": {"model": model}
            }
    
    def _select_best_model(self, query: str, context: Dict) -> str:
        """
        Select the best model for this query based on content and preferences
        
        Args:
            query: The query text
            context: Query context
            
        Returns:
            Model ID
        """
        # Check for explicit model family preference in context
        preferred_family = context.get("preferred_model_family")
        if preferred_family:
            return self._get_best_model_in_family(preferred_family)
        
        # Check if this is likely an image generation request
        if self._is_image_request(query):
            return self._get_best_model_for_capability("image_understanding")
            
        # Check if this is a search/knowledge query
        if self._is_knowledge_query(query):
            return self._get_best_model_for_capability("online_search")
            
        # Check if this is a coding query
        if self._is_code_query(query):
            return self._get_best_model_for_capability("code_generation")
            
        # Check if this is a math/reasoning query
        if self._is_reasoning_query(query):
            return self._get_best_model_for_capability("reasoning")
            
        # Default to the configured default model
        return self.default_model
        
    def _get_best_model_in_family(self, family: str) -> str:
        """
        Get the best available model in a specific family
        
        Args:
            family: Model family ("claude", "gpt", "perplexity")
            
        Returns:
            Best model ID in that family
        """
        family = family.lower()
        
        # Priority orders for each family (best first)
        family_models = {
            "claude": [
                "claude-3-7-sonnet",
                "claude-3-5-sonnet",
                "claude-3-opus", 
                "claude-3-sonnet",
                "claude-3-haiku"
            ],
            "gpt": [
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo"
            ],
            "perplexity": [
                "pplx-70b-online",
                "pplx-7b-online",
                "pplx-70b-chat",
                "pplx-7b-chat"
            ]
        }
        
        # If family not recognized, return default
        if family not in family_models:
            return self.default_model
            
        # Return first available model in priority order
        for model in family_models[family]:
            if model in self.models:
                return model
                
        # If no models in family are available, return default
        return self.default_model
        
    def _get_best_model_for_capability(self, capability: str) -> str:
        """
        Get the best model for a specific capability
        
        Args:
            capability: Capability needed
            
        Returns:
            Best model ID for that capability
        """
        # Map capabilities to models in priority order
        capability_models = {
            "online_search": [
                "pplx-70b-online",
                "pplx-7b-online"
            ],
            "reasoning": [
                "claude-3-opus",
                "claude-3-7-sonnet",
                "claude-3-5-sonnet",
                "gpt-4o",
                "gpt-4"
            ],
            "code_generation": [
                "claude-3-7-sonnet", 
                "claude-3-opus",
                "gpt-4o",
                "gpt-4",
                "claude-3-sonnet"
            ],
            "image_understanding": [
                "gpt-4o",
                "gpt-4-turbo",
                "claude-3-opus",
                "claude-3-7-sonnet"
            ]
        }
        
        # If capability not recognized, return default
        if capability not in capability_models:
            return self.default_model
            
        # Return first available model in priority order
        for model in capability_models[capability]:
            if model in self.models:
                return model
                
        # If no models with capability are available, return default
        return self.default_model
        
    def _get_model_family(self, model: str) -> str:
        """
        Get the family of a model
        
        Args:
            model: Model ID
            
        Returns:
            Model family ("claude", "gpt", "perplexity", "other")
        """
        if "claude" in model:
            return "claude"
        elif "gpt" in model:
            return "gpt"
        elif "pplx" in model:
            return "perplexity"
        else:
            return "other"
    
    def _prepare_messages(self, query, context, model):
        """
        Prepare message history for the API
        
        Args:
            query: User query
            context: Context including history
            model: Target model
            
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
            # Default system prompt for online search models
            if "online" in model:
                messages.append({
                    "role": "system",
                    "content": "Vous êtes un assistant IA qui a accès à des informations à jour grâce aux capacités "
                              "de recherche en ligne. Fournissez des réponses précises et actualisées en citant vos sources."
                })
            elif "claude" in model:
                messages.append({
                    "role": "system",
                    "content": "Vous êtes Claude, un assistant IA développé par Anthropic, conçu pour être utile, "
                              "inoffensif et honnête. Répondez aux questions de l'utilisateur de manière claire et précise."
                })
        
        # Add conversation history if present
        history = context.get("relevant_history", [])
        # For online models, limit history to keep context smaller
        if "online" in model:
            history = history[-2:] if len(history) > 2 else history
            
        for item in history:
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
        
        # Add personal data context if available
        personal_data = context.get("personal_data", {})
        if personal_data and not "online" in model:  # Don't send personal data to online models
            context_str = "Informations contextuelles sur l'utilisateur:\n"
            for key, value in personal_data.items():
                if value:
                    context_str += f"- {key}: {value}\n"
            
            if len(context_str) > 30:  # Only add if there's meaningful data
                messages.append({
                    "role": "system",
                    "content": context_str
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
        footnote_section = re.search(r'\n+Sources?:?\s*\n+((?:.+\n*)+)$', response_text)
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
            
    def _is_image_request(self, query):
        """Determine if query is requesting image generation"""
        import re
        
        image_phrases = [
            r"génère une image",
            r"crée une image", 
            r"dessine",
            r"générer une image",
            r"créer une image",
            r"illustre",
            r"visualise",
            r"montre-moi une image",
            r"image de",
            r"dall-e"
        ]
        
        for phrase in image_phrases:
            if re.search(phrase, query, re.IGNORECASE):
                return True
        
        return False
        
    def _is_knowledge_query(self, query):
        """Determine if query is seeking factual knowledge or current information"""
        import re
        
        knowledge_phrases = [
            r"qu'est[- ]ce que",
            r"qui est",
            r"quand a",
            r"où se trouve",
            r"pourquoi",
            r"comment",
            r"quelle est",
            r"quels sont",
            r"recherche",
            r"informations sur",
            r"actualités",
            r"nouvelles",
            r"récent",
            r"dernier"
        ]
        
        for phrase in knowledge_phrases:
            if re.search(phrase, query, re.IGNORECASE):
                return True
        
        return False
        
    def _is_code_query(self, query):
        """Determine if query is related to code generation"""
        import re
        
        code_phrases = [
            r"code",
            r"programme",
            r"script",
            r"fonction",
            r"classe",
            r"algorithme",
            r"développement",
            r"programmer",
            r"python",
            r"javascript",
            r"java",
            r"c\+\+",
            r"html",
            r"css"
        ]
        
        for phrase in code_phrases:
            if re.search(r'\b' + phrase + r'\b', query, re.IGNORECASE):
                return True
        
        return False
        
    def _is_reasoning_query(self, query):
        """Determine if query requires reasoning or math"""
        import re
        
        reasoning_phrases = [
            r"résoudre",
            r"calculer",
            r"résolution",
            r"problème",
            r"équation",
            r"mathématique",
            r"logique",
            r"raisonnement",
            r"analyser",
            r"analyse",
            r"évaluer",
            r"expliquer pourquoi",
            r"explication détaillée"
        ]
        
        for phrase in reasoning_phrases:
            if re.search(r'\b' + phrase + r'\b', query, re.IGNORECASE):
                return True
                
        # Look for math symbols
        math_symbols = r'[+\-*/^=<>≤≥≠≈]'
        if re.search(math_symbols, query):
            return True
        
        return False
    
    def _calculate_cost(self, usage, model):
        """
        Calculate estimated cost based on token usage
        
        Args:
            usage: Token usage information
            model: Model used
            
        Returns:
            Estimated cost in USD (0 for subscription models)
        """
        # Since we're using a Perplexity subscription, the marginal cost is effectively 0
        # This could be adjusted if there are token limits or per-query costs in the subscription
        return 0.0
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get the capabilities of this provider
        
        Returns:
            Dictionary of capabilities
        """
        capabilities = {
            "text_generation": True,
            "image_generation": "gpt-4o" in self.models,  # GPT-4o can handle images but not generate them
            "function_calling": False,
            "supports_streaming": True,
            "models": self.models,
            "search": any("online" in model for model in self.models),
            "knowledge": True,
            "citation": True,
            "reasoning": any(model in self.models for model in ["claude-3-opus", "claude-3-7-sonnet", "gpt-4o"]),
            "math": True,
            "code_generation": True,
            "model_families": ["claude", "gpt", "perplexity"] 
        }
        
        # Max context varies by model family
        if any("claude-3" in model for model in self.models):
            capabilities["max_context_length"] = 200000
        elif "gpt-4o" in self.models:
            capabilities["max_context_length"] = 128000
        else:
            capabilities["max_context_length"] = 32000
            
        return capabilities
    
    def check_availability(self) -> bool:
        """
        Check if the provider is currently available
        
        Returns:
            True if available, False otherwise
        """
        if not self.initialized or not self.client:
            return False
            
        try:
            # Make a minimal API call to check availability
            self.client.chat.completions.create(
                model=self.default_model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            return True
        except Exception as e:
            logger.warning(f"Perplexity API appears to be unavailable: {str(e)}")
            return False
    
    def get_name(self) -> str:
        """
        Get the display name of this provider
        
        Returns:
            Provider name
        """
        return "Perplexity Hub"
    
    def get_provider_id(self) -> str:
        """
        Get the unique ID of this provider
        
        Returns:
            Provider ID
        """
        return "perplexity_hub"
    
    def get_cost_estimate(self, query: str, context: Optional[Dict] = None) -> float:
        """
        Get an estimated cost for processing this query
        
        Args:
            query: The query text
            context: Additional context that would be sent
            
        Returns:
            Estimated cost in USD (0 for subscription)
        """
        # With a Perplexity subscription, marginal cost is effectively 0
        return 0.0
    
    def shutdown(self) -> None:
        """
        Clean up resources when shutting down
        """
        self.initialized = False
        self.client = None
        logger.info("Perplexity Hub provider has been shut down")


def create_provider(config: Dict[str, Any] = None) -> PerplexityHubProvider:
    """
    Create and return a Perplexity Hub provider instance
    
    Args:
        config: Provider configuration
        
    Returns:
        Configured Perplexity Hub provider
    """
    provider = PerplexityHubProvider()
    if config:
        provider.initialize(config)
    return provider