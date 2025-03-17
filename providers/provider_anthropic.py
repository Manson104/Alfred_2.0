"""
Anthropic Provider - Integration with Anthropic Claude services

This module provides integration with Anthropic's Claude language models.
"""

import logging
import time
import json
import os
from typing import Dict, List, Any, Optional, Union

try:
    import anthropic
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from provider_base import AIProvider

# Setup logging
logger = logging.getLogger("AnthropicProvider")

class AnthropicProvider(AIProvider):
    """Provider for Anthropic's Claude language models"""
    
    def __init__(self):
        """Initialize the Anthropic provider"""
        self.client = None
        self.config = {}
        self.models = []
        self.default_model = "claude-3-5-sonnet-20240620"
        self.initialized = False
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the provider with the given configuration
        
        Args:
            config: Anthropic configuration including API key
            
        Returns:
            True if initialization was successful
        """
        if not ANTHROPIC_AVAILABLE:
            logger.error("Anthropic package is not installed. Please install with: pip install anthropic")
            return False
        
        self.config = config
        
        # Get API key from config or environment
        api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("No Anthropic API key provided")
            return False
        
        try:
            # Initialize the client
            self.client = Anthropic(api_key=api_key)
            
            # Set default model
            self.default_model = config.get("default_model", "claude-3-5-sonnet-20240620")
            
            # Available models as of April 2024
            self.models = [
                "claude-3-opus-20240229",
                "claude-3-5-sonnet-20240620",
                "claude-3-sonnet-20240229", 
                "claude-3-haiku-20240307",
                "claude-2.1",
                "claude-2.0",
                "claude-instant-1.2"
            ]
            
            self.initialized = True
            logger.info(f"Anthropic provider initialized with model {self.default_model}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic provider: {str(e)}")
            return False
    
    def send_query(self, 
                  query: str, 
                  context: Optional[Dict[str, Any]] = None, 
                  options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a query to Anthropic Claude
        
        Args:
            query: The user's query text
            context: Additional context for the query
            options: Anthropic-specific options for this query
            
        Returns:
            Response dictionary
        """
        if not self.initialized or not self.client:
            return {
                "success": False,
                "response": "Anthropic provider is not initialized",
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
            max_tokens = options.get("max_tokens", 4000)
            system = self._prepare_system_prompt(context)
            
            # Call the API
            start_time = time.time()
            response = self.client.messages.create(
                model=model,
                messages=messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens
            )
            end_time = time.time()
            
            # Extract response text
            response_text = response.content[0].text if response.content else ""
            
            # Calculate token usage and cost
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                "estimated_cost": self._calculate_cost(response.usage, model)
            }
            
            return {
                "success": True,
                "response": response_text,
                "raw_response": response,
                "usage": usage,
                "metadata": {
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time": end_time - start_time
                }
            }
            
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {str(e)}")
            return {
                "success": False,
                "response": f"Error: {str(e)}",
                "error": str(e),
                "usage": {},
                "metadata": {}
            }
    
    def _prepare_messages(self, query, context):
        """
        Prepare message history for the Anthropic API
        
        Args:
            query: User query
            context: Context including history
            
        Returns:
            List of message dictionaries
        """
        messages = []
        
        # Add conversation history if present
        history = context.get("relevant_history", [])
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
        
        # Add the current query
        messages.append({
            "role": "user",
            "content": query
        })
        
        return messages
    
    def _prepare_system_prompt(self, context):
        """
        Prepare system prompt from context
        
        Args:
            context: Query context
            
        Returns:
            System prompt string
        """
        # Start with base system prompt
        system_prompt = self.config.get("system_prompt", "")
        
        # Add personal data context if available
        personal_data = context.get("personal_data", {})
        if personal_data:
            context_str = "\n\nInformations contextuelles sur l'utilisateur:\n"
            for key, value in personal_data.items():
                if value:
                    context_str += f"- {key}: {value}\n"
            
            if len(context_str) > 30:  # Only add if there's meaningful data
                system_prompt += context_str
        
        # Add user preferences if available
        user_preferences = context.get("user_preferences", {})
        if user_preferences:
            pref_str = "\n\nPréférences de l'utilisateur:\n"
            for key, value in user_preferences.items():
                if value:
                    pref_str += f"- {key}: {value}\n"
            
            if len(pref_str) > 30:  # Only add if there's meaningful data
                system_prompt += pref_str
        
        return system_prompt
    
    def _calculate_cost(self, usage, model):
        """
        Calculate estimated cost based on token usage
        
        Args:
            usage: Token usage information
            model: Model used
            
        Returns:
            Estimated cost in USD
        """
        # Pricing as of April 2024 (simplified)
        pricing = {
            "claude-3-opus-20240229": {
                "input": 15.0 / 1000000,  # $15 per 1M input tokens
                "output": 75.0 / 1000000  # $75 per 1M output tokens
            },
            "claude-3-5-sonnet-20240620": {
                "input": 3.0 / 1000000,  # $3 per 1M input tokens
                "output": 15.0 / 1000000  # $15 per 1M output tokens
            },
            "claude-3-sonnet-20240229": {
                "input": 3.0 / 1000000,
                "output": 15.0 / 1000000
            },
            "claude-3-haiku-20240307": {
                "input": 0.25 / 1000000,
                "output": 1.25 / 1000000
            }
        }
        
        # Use claude-3-sonnet pricing as default
        model_pricing = pricing.get(model, pricing["claude-3-sonnet-20240229"])
        
        input_cost = usage.input_tokens * model_pricing["input"]
        output_cost = usage.output_tokens * model_pricing["output"]
        
        return input_cost + output_cost
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get the capabilities of this provider
        
        Returns:
            Dictionary of capabilities
        """
        # Base capabilities
        capabilities = {
            "text_generation": True,
            "image_generation": False,
            "function_calling": False,
            "max_context_length": 200000,  # Claude 3 models have very large context
            "supports_streaming": True,
            "models": self.models,
            "reasoning": True,
            "math": True,
            "code_generation": True
        }
        
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
            self.client.messages.create(
                model=self.default_model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hello"}]
            )
            return True
        except Exception as e:
            logger.warning(f"Anthropic API appears to be unavailable: {str(e)}")
            return False
    
    def get_name(self) -> str:
        """
        Get the display name of this provider
        
        Returns:
            Provider name
        """
        return "Anthropic Claude"
    
    def get_provider_id(self) -> str:
        """
        Get the unique ID of this provider
        
        Returns:
            Provider ID
        """
        return "anthropic"
    
    def get_cost_estimate(self, query: str, context: Optional[Dict] = None) -> float:
        """
        Get an estimated cost for processing this query
        
        Args:
            query: The query text
            context: Additional context that would be sent
            
        Returns:
            Estimated cost in USD
        """
        # For text completion, estimate token count
        token_estimate = len(query.split()) * 1.3  # Rough token estimate
        
        # Add context tokens if provided
        if context and "relevant_history" in context:
            for item in context["relevant_history"]:
                if "text" in item:
                    token_estimate += len(item["text"].split()) * 1.3
                if "response" in item:
                    token_estimate += len(item["response"].split()) * 1.3
        
        # Assume response is 2x query length
        completion_tokens = token_estimate * 2
        
        # Use default model for pricing
        if "opus" in self.default_model:
            return (token_estimate * 15.0 / 1000000) + (completion_tokens * 75.0 / 1000000)
        elif "sonnet" in self.default_model:
            return (token_estimate * 3.0 / 1000000) + (completion_tokens * 15.0 / 1000000)
        else:  # haiku
            return (token_estimate * 0.25 / 1000000) + (completion_tokens * 1.25 / 1000000)
    
    def shutdown(self) -> None:
        """
        Clean up resources when shutting down
        """
        self.initialized = False
        self.client = None
        logger.info("Anthropic provider has been shut down")


def create_provider(config: Dict[str, Any] = None) -> AnthropicProvider:
    """
    Create and return an Anthropic provider instance
    
    Args:
        config: Provider configuration
        
    Returns:
        Configured Anthropic provider
    """
    provider = AnthropicProvider()
    if config:
        provider.initialize(config)
    return provider