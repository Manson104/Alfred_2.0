"""
AI Router - Intelligent routing of queries to the appropriate AI provider

This module is responsible for:
- Selecting the appropriate AI provider for a given query
- Routing queries to multiple providers when needed
- Synthesizing responses from multiple providers
- Handling fallback when a provider fails
"""

import time
import json
import re
from typing import Dict, List, Any, Optional, Tuple, Union

# Import the centralized logging system
from utils.logger import get_logger, log_execution_time

# Setup logging
logger = get_logger("ai.AIRouter")

class AIRouter:
    """
    Routes queries to appropriate AI providers based on query content, 
    provider capabilities, user preferences, and system state.
    """
    
    def __init__(self, message_bus, state_manager, module_manager):
        """
        Initialize the AI Router
        
        Args:
            message_bus: System message bus for communication
            state_manager: System state manager
            module_manager: Module manager for loading providers
        """
        self.message_bus = message_bus
        self.state_manager = state_manager
        self.module_manager = module_manager
        
        # Dictionary of available providers: provider_id -> provider_instance
        self.providers = {}
        
        # Routing strategy
        self.strategy = self.state_manager.get("ai_router_strategy", "smart")
        
        # Register for relevant messages
        self.message_bus.subscribe("query", self._handle_query)
        self.message_bus.subscribe("enriched_query", self._handle_enriched_query)
        self.message_bus.subscribe("system", self._handle_system_message)
        
        logger.info("AI Router initialized")
        
    def initialize_providers(self):
        """
        Initialize all configured AI providers
        """
        # Get the list of enabled providers from state
        enabled_providers = self.state_manager.get("enabled_ai_providers", [])
        
        for provider_id in enabled_providers:
            try:
                # Load the provider module
                provider_module_id = f"provider-{provider_id}"
                provider_module = self.module_manager.load_module(provider_module_id)
                
                if not provider_module:
                    logger.error(f"Failed to load provider module: {provider_module_id}")
                    continue
                
                # Get provider configuration
                provider_config = self.state_manager.get(f"ai_provider_{provider_id}_config", {})
                
                # Create provider instance
                provider = provider_module.create_provider(provider_config)
                
                # Initialize the provider
                if provider.initialize(provider_config):
                    self.providers[provider_id] = provider
                    logger.info(f"Initialized AI provider: {provider.get_name()}")
                else:
                    logger.error(f"Failed to initialize provider: {provider_id}")
                
            except Exception as e:
                logger.error(f"Error initializing provider {provider_id}: {str(e)}", exc_info=True)
        
        # Update state with available providers
        self.state_manager.set("available_ai_providers", list(self.providers.keys()))
        logger.info(f"Initialized {len(self.providers)} AI providers")
        
    def shutdown_providers(self):
        """
        Shutdown all providers and release resources
        """
        for provider_id, provider in self.providers.items():
            try:
                provider.shutdown()
                logger.info(f"Shutdown AI provider: {provider.get_name()}")
            except Exception as e:
                logger.error(f"Error shutting down provider {provider_id}: {str(e)}", exc_info=True)
        
        self.providers = {}
        
    def _handle_query(self, message):
        """
        Handle an incoming query message
        
        Args:
            message: The message containing the query
        """
        data = message.get("data", {})
        query_id = data.get("query_id")
        query_text = data.get("query")
        context = data.get("context", {})
        options = data.get("options", {})
        
        if not query_text:
            logger.warning("Received empty query, ignoring")
            return
        
        logger.debug(f"Received query: {query_id} - '{query_text[:50]}...' (waiting for context enrichment)")
    
    def _handle_enriched_query(self, message):
        """
        Handle an enriched query message (after context manager has added context)
        
        Args:
            message: The message containing the enriched query
        """
        data = message.get("data", {})
        query_id = data.get("query_id")
        query_text = data.get("query")
        context = data.get("context", {})
        options = data.get("options", {})
        strategy = options.get("strategy", self.strategy)
        
        # Process the query
        logger.info(f"Processing enriched query: {query_id}")
        logger.debug(f"Query context: {json.dumps(context, default=str)[:200]}...")
        
        try:
            result = self.route_query(query_text, context, strategy, options)
            
            # Publish the result
            self.message_bus.publish("query_result", {
                "query_id": query_id,
                "result": result,
                "original_query": query_text
            }, sender="ai_router")
            
            logger.info(f"Query {query_id} processed successfully in {result.get('timing', {}).get('elapsed_seconds', 0):.2f}s")
            
        except Exception as e:
            logger.error(f"Error processing query {query_id}: {str(e)}", exc_info=True)
            
            # Publish error
            self.message_bus.publish("query_error", {
                "query_id": query_id,
                "error": str(e),
                "original_query": query_text
            }, sender="ai_router")
            
    def _handle_system_message(self, message):
        """
        Handle system messages
        
        Args:
            message: System message
        """
        data = message.get("data", {})
        event = data.get("event")
        
        if event == "provider_added":
            provider_id = data.get("provider_id")
            if provider_id and provider_id not in self.providers:
                logger.info(f"New provider added: {provider_id}, reinitializing providers")
                self.initialize_providers()  # Reinitialize all providers
                
        elif event == "provider_removed":
            provider_id = data.get("provider_id")
            if provider_id in self.providers:
                try:
                    logger.info(f"Provider removed: {provider_id}")
                    self.providers[provider_id].shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down provider {provider_id}: {str(e)}", exc_info=True)
                del self.providers[provider_id]
                
        elif event == "strategy_changed":
            self.strategy = data.get("strategy", self.strategy)
            logger.info(f"AI Router strategy changed to: {self.strategy}")
            
    @log_execution_time
    def route_query(self, 
                   query: str, 
                   context: Optional[Dict] = None, 
                   strategy: Optional[str] = None,
                   options: Optional[Dict] = None) -> Dict:
        """
        Route a query to the appropriate provider(s) based on the strategy
        
        Args:
            query: The query text
            context: Additional context for the query
            strategy: Routing strategy to use
            options: Additional options for routing
            
        Returns:
            Result dictionary containing the response and metadata
        """
        context = context or {}
        options = options or {}
        strategy = strategy or self.strategy
        
        if not self.providers:
            logger.error("No AI providers available")
            raise ValueError("No AI providers available")
        
        # Use different routing strategies
        if strategy == "smart":
            return self._smart_routing(query, context, options)
        elif strategy == "ensemble":
            return self._ensemble_routing(query, context, options)
        elif strategy == "specified":
            # Use a specific provider
            provider_id = options.get("provider_id")
            if not provider_id or provider_id not in self.providers:
                logger.error(f"Invalid provider specified: {provider_id}")
                raise ValueError(f"Invalid provider specified: {provider_id}")
            return self._query_single_provider(provider_id, query, context, options)
        elif strategy == "default":
            # Use the default provider
            default_provider = self.state_manager.get("default_ai_provider")
            if not default_provider or default_provider not in self.providers:
                # Fall back to first available provider
                default_provider = next(iter(self.providers.keys()))
                logger.warning(f"Default provider not available, using {default_provider}")
            return self._query_single_provider(default_provider, query, context, options)
        else:
            logger.error(f"Unknown routing strategy: {strategy}")
            raise ValueError(f"Unknown routing strategy: {strategy}")
            
    @log_execution_time
    def _smart_routing(self, query: str, context: Dict, options: Dict) -> Dict:
        """
        Smart routing strategy - select the best provider for this query
        
        Args:
            query: Query text
            context: Query context
            options: Routing options
            
        Returns:
            Result from the selected provider
        """
        # Analyze the query to determine the best provider
        provider_id = self._select_best_provider(query, context)
        logger.debug(f"Smart routing selected provider: {provider_id}")
        
        # Query the selected provider
        result = self._query_single_provider(provider_id, query, context, options)
        
        # Add metadata about the routing decision
        result["routing"] = {
            "strategy": "smart",
            "selected_provider": provider_id,
            "reason": self._get_selection_reason(query, provider_id)
        }
        
        return result
        
    # Les autres méthodes restent inchangées...
