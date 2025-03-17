"""
AI Provider Base - Abstract interface for all AI providers

This module defines the standard interface that all AI providers must implement
to be compatible with the Alfred system.
"""

import abc
from typing import Dict, List, Any, Optional, Union

class AIProvider(abc.ABC):
    """
    Abstract base class for AI providers
    
    All AI service integrations (OpenAI, Anthropic, Perplexity, etc.) 
    must implement this interface.
    """
    
    @abc.abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the provider with the given configuration
        
        Args:
            config: Provider-specific configuration dict
            
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    def send_query(self, 
                  query: str, 
                  context: Optional[Dict[str, Any]] = None, 
                  options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a query to the AI provider
        
        Args:
            query: The user's query text
            context: Additional context for the query (history, preferences, etc.)
            options: Provider-specific options for this query
            
        Returns:
            Response dict containing at minimum:
            {
                "success": bool,
                "response": str,
                "raw_response": Any,  # Provider-specific raw response
                "usage": Dict,  # Usage statistics (tokens, costs, etc.)
                "metadata": Dict  # Additional provider-specific metadata
            }
        """
        pass
    
    @abc.abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get the capabilities of this provider
        
        Returns:
            Dictionary of capabilities, e.g.:
            {
                "text_generation": True,
                "image_generation": False,
                "function_calling": True,
                "max_context_length": 16000,
                "supports_streaming": True,
                "models": ["gpt-4", "gpt-3.5-turbo", ...],
                ...
            }
        """
        pass
    
    @abc.abstractmethod
    def check_availability(self) -> bool:
        """
        Check if the provider is currently available
        
        Returns:
            True if available, False otherwise
        """
        pass
    
    @abc.abstractmethod
    def get_name(self) -> str:
        """
        Get the display name of this provider
        
        Returns:
            Provider name (e.g. "OpenAI GPT-4", "Claude 3 Opus")
        """
        pass
    
    @abc.abstractmethod
    def get_provider_id(self) -> str:
        """
        Get the unique ID of this provider
        
        Returns:
            Provider ID (e.g. "openai", "anthropic", "perplexity")
        """
        pass
    
    def supports_feature(self, feature_name: str) -> bool:
        """
        Check if this provider supports a specific feature
        
        Args:
            feature_name: Name of the feature to check
            
        Returns:
            True if the feature is supported, False otherwise
        """
        return self.get_capabilities().get(feature_name, False)
    
    def get_cost_estimate(self, query: str, context: Optional[Dict] = None) -> float:
        """
        Get an estimated cost for processing this query
        
        Args:
            query: The query text
            context: Additional context that would be sent
            
        Returns:
            Estimated cost in USD
        """
        # Default implementation - providers should override this
        return 0.0
    
    def shutdown(self) -> None:
        """
        Clean up resources when shutting down
        """
        # Default implementation does nothing
        pass
