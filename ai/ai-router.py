"""
AI Router - Intelligent routing of queries to the appropriate AI provider

This module is responsible for:
- Selecting the appropriate AI provider for a given query
- Routing queries to multiple providers when needed
- Synthesizing responses from multiple providers
- Handling fallback when a provider fails
"""

import logging
import time
import json
from typing import Dict, List, Any, Optional, Tuple, Union
import re

# Setup logging
logger = logging.getLogger("AIRouter")

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
                logger.error(f"Error initializing provider {provider_id}: {str(e)}")
        
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
                logger.error(f"Error shutting down provider {provider_id}: {str(e)}")
        
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
        strategy = options.get("strategy", self.strategy)
        
        if not query_text:
            logger.warning("Received empty query, ignoring")
            return
        
        # Process the query
        logger.info(f"Processing query: {query_id}")
        
        try:
            result = self.route_query(query_text, context, strategy, options)
            
            # Publish the result
            self.message_bus.publish("query_result", {
                "query_id": query_id,
                "result": result,
                "original_query": query_text
            }, sender="ai_router")
            
        except Exception as e:
            logger.error(f"Error processing query {query_id}: {str(e)}")
            
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
                self.initialize_providers()  # Reinitialize all providers
                
        elif event == "provider_removed":
            provider_id = data.get("provider_id")
            if provider_id in self.providers:
                try:
                    self.providers[provider_id].shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down provider {provider_id}: {str(e)}")
                del self.providers[provider_id]
                
        elif event == "strategy_changed":
            self.strategy = data.get("strategy", self.strategy)
            logger.info(f"AI Router strategy changed to: {self.strategy}")
            
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
                raise ValueError(f"Invalid provider specified: {provider_id}")
            return self._query_single_provider(provider_id, query, context, options)
        elif strategy == "default":
            # Use the default provider
            default_provider = self.state_manager.get("default_ai_provider")
            if not default_provider or default_provider not in self.providers:
                # Fall back to first available provider
                default_provider = next(iter(self.providers.keys()))
            return self._query_single_provider(default_provider, query, context, options)
        else:
            raise ValueError(f"Unknown routing strategy: {strategy}")
            
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
        
        # Query the selected provider
        result = self._query_single_provider(provider_id, query, context, options)
        
        # Add metadata about the routing decision
        result["routing"] = {
            "strategy": "smart",
            "selected_provider": provider_id,
            "reason": self._get_selection_reason(query, provider_id)
        }
        
        return result
        
    def _ensemble_routing(self, query: str, context: Dict, options: Dict) -> Dict:
        """
        Ensemble routing strategy - query multiple providers and combine results
        
        Args:
            query: Query text
            context: Query context
            options: Routing options
            
        Returns:
            Combined result from multiple providers
        """
        # Determine which providers to use
        if "providers" in options:
            # Use specified providers
            provider_ids = [p for p in options["providers"] if p in self.providers]
            if not provider_ids:
                raise ValueError("None of the specified providers are available")
        else:
            # Select top N providers based on query analysis
            top_n = options.get("top_n", 2)
            provider_ids = self._select_top_providers(query, context, top_n)
        
        # Query all selected providers
        results = {}
        for provider_id in provider_ids:
            try:
                results[provider_id] = self._query_single_provider(
                    provider_id, query, context, options
                )
            except Exception as e:
                logger.error(f"Error querying provider {provider_id}: {str(e)}")
                results[provider_id] = {
                    "success": False,
                    "response": f"Error: {str(e)}",
                    "error": str(e)
                }
        
        # Combine results
        combined_result = self._synthesize_responses(results, query, context)
        
        # Add metadata about the ensemble
        combined_result["routing"] = {
            "strategy": "ensemble",
            "providers_used": list(results.keys()),
            "combine_method": options.get("combine_method", "best")
        }
        
        return combined_result
        
    def _query_single_provider(self, 
                             provider_id: str, 
                             query: str, 
                             context: Dict, 
                             options: Dict) -> Dict:
        """
        Query a single provider
        
        Args:
            provider_id: Provider ID
            query: Query text
            context: Query context
            options: Query options
            
        Returns:
            Provider's response
        """
        provider = self.providers.get(provider_id)
        if not provider:
            raise ValueError(f"Provider not available: {provider_id}")
            
        # Check if provider is available
        if not provider.check_availability():
            raise ValueError(f"Provider {provider_id} is currently unavailable")
            
        # Send the query
        start_time = time.time()
        result = provider.send_query(query, context, options)
        end_time = time.time()
        
        # Add timing information
        result["timing"] = {
            "start_time": start_time,
            "end_time": end_time,
            "elapsed_seconds": end_time - start_time
        }
        
        # Add provider information
        result["provider"] = {
            "id": provider_id,
            "name": provider.get_name()
        }
        
        return result
        
    def _select_best_provider(self, query: str, context: Dict) -> str:
        """
        Select the best provider for this query
        
        Args:
            query: Query text
            context: Query context
            
        Returns:
            ID of the best provider
        """
        # Initialize scores for each provider
        scores = {provider_id: 0 for provider_id in self.providers}
        
        # Adjust scores based on query content
        self._score_by_query_content(query, scores)
        
        # Adjust scores based on provider capabilities
        self._score_by_capabilities(query, scores)
        
        # Adjust scores based on user preferences
        self._score_by_user_preferences(query, context, scores)
        
        # Adjust scores based on previous performance
        self._score_by_historical_performance(query, context, scores)
        
        # Get the provider with the highest score
        if not scores:
            # Fall back to default provider if no scores
            return self.state_manager.get("default_ai_provider", next(iter(self.providers.keys())))
            
        return max(scores.items(), key=lambda x: x[1])[0]
        
    def _select_top_providers(self, query: str, context: Dict, n: int) -> List[str]:
        """
        Select the top N providers for this query
        
        Args:
            query: Query text
            context: Query context
            n: Number of providers to select
            
        Returns:
            List of provider IDs
        """
        # Get scores for all providers
        scores = {provider_id: 0 for provider_id in self.providers}
        
        self._score_by_query_content(query, scores)
        self._score_by_capabilities(query, scores)
        self._score_by_user_preferences(query, context, scores)
        self._score_by_historical_performance(query, context, scores)
        
        # Sort providers by score (descending)
        sorted_providers = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Return top N providers
        return [p[0] for p in sorted_providers[:min(n, len(sorted_providers))]]
        
    def _score_by_query_content(self, query: str, scores: Dict[str, float]):
        """
        Adjust scores based on query content
        
        Args:
            query: Query text
            scores: Provider scores to update
        """
        # Check for image generation requests
        if re.search(r'(crée|génère|dessine|faire).{1,20}(image|photo|dessin|illustration|graphique)', 
                    query, re.IGNORECASE):
            # Favor providers with image generation
            for provider_id, provider in self.providers.items():
                if provider.supports_feature("image_generation"):
                    scores[provider_id] += 10.0
                else:
                    scores[provider_id] -= 5.0
        
        # Check for code generation
        if re.search(r'(code|programme|script|fonction|méthode|classe)', query, re.IGNORECASE) or \
           re.search(r'(javascript|python|java|c\+\+|ruby|php|html|css|sql)', query, re.IGNORECASE):
            for provider_id, provider in self.providers.items():
                if provider.supports_feature("code_generation"):
                    scores[provider_id] += 5.0
        
        # Check for search/knowledge queries
        if re.search(r'(qui est|qu\'est-ce que|quand|où|pourquoi|comment|recherche)', query, re.IGNORECASE):
            for provider_id, provider in self.providers.items():
                if provider.supports_feature("search") or provider.supports_feature("knowledge"):
                    scores[provider_id] += 3.0
        
        # Check for math/reasoning queries
        if re.search(r'(calcule|résous|équation|mathématique|logique|raisonnement)', query, re.IGNORECASE):
            for provider_id, provider in self.providers.items():
                if provider.supports_feature("reasoning") or provider.supports_feature("math"):
                    scores[provider_id] += 4.0
        
    def _score_by_capabilities(self, query: str, scores: Dict[str, float]):
        """
        Adjust scores based on provider capabilities
        
        Args:
            query: Query text
            scores: Provider scores to update
        """
        # Get query length
        query_length = len(query)
        
        # Adjust for context length - prefer providers that can handle the query length
        for provider_id, provider in self.providers.items():
            capabilities = provider.get_capabilities()
            max_length = capabilities.get("max_context_length", 4000)
            
            # If query is approaching max length, reduce score
            if query_length > max_length * 0.8:
                scores[provider_id] -= 3.0
            elif query_length > max_length * 0.5:
                scores[provider_id] -= 1.0
        
    def _score_by_user_preferences(self, query: str, context: Dict, scores: Dict[str, float]):
        """
        Adjust scores based on user preferences
        
        Args:
            query: Query text
            context: Query context
            scores: Provider scores to update
        """
        # Get user preferences
        user_id = context.get("user_id")
        if not user_id:
            return
            
        user_preferences = self.state_manager.get(f"user_{user_id}_preferences", {})
        
        # Check for preferred providers
        preferred_providers = user_preferences.get("preferred_providers", [])
        for provider_id in preferred_providers:
            if provider_id in scores:
                scores[provider_id] += 2.0
        
        # Check for provider-specific preferences
        provider_preferences = user_preferences.get("provider_preferences", {})
        for provider_id, preference in provider_preferences.items():
            if provider_id in scores:
                # Preference is a value from -1.0 (avoid) to 1.0 (prefer)
                scores[provider_id] += preference * 3.0
        
    def _score_by_historical_performance(self, query: str, context: Dict, scores: Dict[str, float]):
        """
        Adjust scores based on historical performance
        
        Args:
            query: Query text
            context: Query context
            scores: Provider scores to update
        """
        # This would normally use a more sophisticated analysis of past performance
        # For now, use a simplified approach based on success rates
        
        for provider_id in scores:
            # Get historical success rate for this provider
            success_rate = self.state_manager.get(f"provider_{provider_id}_success_rate", 0.95)
            
            # Adjust score based on success rate
            scores[provider_id] += (success_rate - 0.9) * 10.0  # Scale to reasonable adjustment
        
    def _synthesize_responses(self, 
                            provider_results: Dict[str, Dict], 
                            query: str, 
                            context: Dict) -> Dict:
        """
        Synthesize responses from multiple providers
        
        Args:
            provider_results: Results from each provider
            query: Original query
            context: Query context
            
        Returns:
            Synthesized result
        """
        # Get the combine method from context
        combine_method = context.get("combine_method", "best")
        
        if combine_method == "best":
            # Simply pick the best response based on a heuristic
            best_provider = self._select_best_result(provider_results, query)
            result = provider_results[best_provider].copy()
            result["synthesis_method"] = "best"
            result["selected_provider"] = best_provider
            result["all_providers"] = list(provider_results.keys())
            return result
            
        elif combine_method == "concatenate":
            # Concatenate all responses with attribution
            combined_response = ""
            for provider_id, result in provider_results.items():
                if result.get("success", False):
                    provider_name = result.get("provider", {}).get("name", provider_id)
                    combined_response += f"\n\n--- Réponse de {provider_name} ---\n\n"
                    combined_response += result.get("response", "")
            
            # Create a new result with the combined response
            result = {
                "success": True,
                "response": combined_response.strip(),
                "synthesis_method": "concatenate",
                "all_providers": list(provider_results.keys())
            }
            return result
            
        elif combine_method == "summary":
            # This would ideally use an LLM to summarize multiple responses
            # For now, use a simplified approach
            responses = []
            for provider_id, result in provider_results.items():
                if result.get("success", False):
                    responses.append(result.get("response", ""))
            
            # Just take the first response for now
            # In a real implementation, this would use an LLM to create a summary
            if responses:
                result = {
                    "success": True,
                    "response": "Cette réponse combine des informations de plusieurs sources:\n\n" + responses[0],
                    "synthesis_method": "summary",
                    "all_providers": list(provider_results.keys())
                }
                return result
            else:
                return {
                    "success": False,
                    "response": "Aucune réponse valide n'a été obtenue des fournisseurs d'IA.",
                    "synthesis_method": "summary",
                    "all_providers": list(provider_results.keys())
                }
        else:
            raise ValueError(f"Unknown combine method: {combine_method}")
        
    def _select_best_result(self, provider_results: Dict[str, Dict], query: str) -> str:
        """
        Select the best result from multiple providers
        
        Args:
            provider_results: Results from each provider
            query: Original query
            
        Returns:
            ID of the provider with the best result
        """
        # For now, use a simple heuristic:
        # 1. Filter out failed results
        # 2. Prefer longer responses (which might have more detail)
        # 3. Break ties by provider preference
        
        valid_results = {}
        for provider_id, result in provider_results.items():
            if result.get("success", False):
                valid_results[provider_id] = result
        
        if not valid_results:
            # If no valid results, return the first provider anyway
            return next(iter(provider_results.keys()))
        
        # Score the results
        scores = {}
        for provider_id, result in valid_results.items():
            response = result.get("response", "")
            
            # Base score on response length, but with diminishing returns
            import math
            scores[provider_id] = math.log(len(response) + 1) * 10
            
            # Add provider preference from state
            provider_preference = self.state_manager.get(f"provider_{provider_id}_preference", 0)
            scores[provider_id] += provider_preference
        
        # Return the provider with the highest score
        return max(scores.items(), key=lambda x: x[1])[0]
        
    def _get_selection_reason(self, query: str, provider_id: str) -> str:
        """
        Get a human-readable reason for selecting a provider
        
        Args:
            query: Query text
            provider_id: Selected provider ID
            
        Returns:
            Reason for selection
        """
        provider = self.providers.get(provider_id)
        if not provider:
            return "Provider was selected but is no longer available."
            
        # Check for common patterns
        if re.search(r'(crée|génère|dessine|faire).{1,20}(image|photo|dessin|illustration)', 
                    query, re.IGNORECASE) and provider.supports_feature("image_generation"):
            return f"{provider.get_name()} a été choisi pour sa capacité à générer des images."
            
        if re.search(r'(code|programme|script|fonction)', query, re.IGNORECASE) and \
           provider.supports_feature("code_generation"):
            return f"{provider.get_name()} a été choisi pour sa capacité à générer du code."
            
        if re.search(r'(qui est|qu\'est-ce que|quand|où|pourquoi|comment|recherche)', query, re.IGNORECASE) and \
           provider.supports_feature("knowledge"):
            return f"{provider.get_name()} a été choisi pour sa connaissance et sa capacité de recherche."
            
        # Default reason
        return f"{provider.get_name()} a été choisi comme le plus approprié pour cette requête."
