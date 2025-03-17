"""
Context Manager - Manages user context and personalization

This module is responsible for:
- Storing and retrieving user preferences
- Managing conversation history
- Enriching queries with personal context
- Handling personal data securely
"""

import os
import json
import logging
import time
from datetime import datetime
import re
from typing import Dict, List, Any, Optional, Tuple, Union

# Setup logging
logger = logging.getLogger("ContextManager")

class ContextManager:
    """
    Manages context and personalization for user interactions
    """
    
    def __init__(self, message_bus, state_manager, base_path="~/.alfred/user_data"):
        """
        Initialize the Context Manager
        
        Args:
            message_bus: System message bus for communication
            state_manager: System state manager
            base_path: Base directory for user data storage
        """
        self.message_bus = message_bus
        self.state_manager = state_manager
        self.base_path = os.path.expanduser(base_path)
        
        # Create directory structure if it doesn't exist
        os.makedirs(self.base_path, exist_ok=True)
        
        # User context cache: user_id -> user context
        self.user_contexts = {}
        
        # Maximum history items to keep in memory per user
        self.max_history_items = 50
        
        # Register for relevant messages
        self.message_bus.subscribe("query", self._handle_query)
        self.message_bus.subscribe("query_result", self._handle_query_result)
        self.message_bus.subscribe("user_preferences_update", self._handle_preference_update)
        
        logger.info("Context Manager initialized")
        
    def _handle_query(self, message):
        """
        Handle an incoming query message
        
        Args:
            message: The message containing the query
        """
        data = message.get("data", {})
        query_id = data.get("query_id")
        query_text = data.get("query")
        user_id = data.get("user_id")
        
        if not user_id or not query_text:
            return
        
        # Save the query in user history
        self._add_to_history(user_id, {
            "type": "query",
            "query_id": query_id,
            "text": query_text,
            "timestamp": time.time()
        })
        
        # Enrich the query with user context
        enriched_context = self.enrich_query(query_text, user_id)
        
        # Update the message with enriched context
        if enriched_context:
            # Create a new message with enriched context
            self.message_bus.publish("enriched_query", {
                "query_id": query_id,
                "query": query_text,
                "user_id": user_id,
                "context": enriched_context
            }, sender="context_manager")
        
    def _handle_query_result(self, message):
        """
        Handle a query result message
        
        Args:
            message: The message containing the query result
        """
        data = message.get("data", {})
        query_id = data.get("query_id")
        result = data.get("result", {})
        original_query = data.get("original_query", "")
        
        # Try to find the original query message to get user_id
        # In a real implementation, the query_result message would include user_id
        user_id = self._find_user_for_query(query_id)
        
        if not user_id:
            logger.warning(f"Could not find user for query {query_id}")
            return
        
        # Save the result in user history
        self._add_to_history(user_id, {
            "type": "result",
            "query_id": query_id,
            "original_query": original_query,
            "response": result.get("response", ""),
            "provider": result.get("provider", {}).get("id"),
            "timestamp": time.time()
        })
        
        # Update user preferences based on result
        if "provider" in result:
            provider_id = result.get("provider", {}).get("id")
            if provider_id:
                # Track provider usage
                self._update_provider_usage(user_id, provider_id)
        
    def _handle_preference_update(self, message):
        """
        Handle user preference updates
        
        Args:
            message: Message containing preference updates
        """
        data = message.get("data", {})
        user_id = data.get("user_id")
        preferences = data.get("preferences", {})
        
        if not user_id or not preferences:
            return
        
        # Update preferences in memory and on disk
        self._update_user_preferences(user_id, preferences)
        
    def _find_user_for_query(self, query_id):
        """
        Find the user associated with a query
        
        Args:
            query_id: ID of the query
            
        Returns:
            User ID or None if not found
        """
        # This is a simplified implementation
        # In a real system, this would be more efficient
        for user_id, context in self.user_contexts.items():
            history = context.get("history", [])
            for item in history:
                if item.get("type") == "query" and item.get("query_id") == query_id:
                    return user_id
        
        return None
        
    def _add_to_history(self, user_id, item):
        """
        Add an item to user history
        
        Args:
            user_id: User ID
            item: History item to add
        """
        # Load user context if not already in memory
        if user_id not in self.user_contexts:
            self._load_user_context(user_id)
        
        # Add item to history
        if "history" not in self.user_contexts[user_id]:
            self.user_contexts[user_id]["history"] = []
        
        self.user_contexts[user_id]["history"].insert(0, item)
        
        # Trim history to max size
        if len(self.user_contexts[user_id]["history"]) > self.max_history_items:
            self.user_contexts[user_id]["history"] = self.user_contexts[user_id]["history"][:self.max_history_items]
        
        # Save history to disk
        self._save_user_history(user_id)
        
    def _update_provider_usage(self, user_id, provider_id):
        """
        Update provider usage stats for a user
        
        Args:
            user_id: User ID
            provider_id: Provider ID
        """
        # Load user context if not already in memory
        if user_id not in self.user_contexts:
            self._load_user_context(user_id)
        
        # Initialize provider_usage if needed
        if "provider_usage" not in self.user_contexts[user_id]:
            self.user_contexts[user_id]["provider_usage"] = {}
        
        if provider_id not in self.user_contexts[user_id]["provider_usage"]:
            self.user_contexts[user_id]["provider_usage"][provider_id] = 0
        
        # Increment usage count
        self.user_contexts[user_id]["provider_usage"][provider_id] += 1
        
        # Save to disk
        self._save_user_preferences(user_id)
        
    def _update_user_preferences(self, user_id, preferences):
        """
        Update user preferences
        
        Args:
            user_id: User ID
            preferences: New preferences to update
        """
        # Load user context if not already in memory
        if user_id not in self.user_contexts:
            self._load_user_context(user_id)
        
        # Initialize preferences if needed
        if "preferences" not in self.user_contexts[user_id]:
            self.user_contexts[user_id]["preferences"] = {}
        
        # Update preferences
        self.user_contexts[user_id]["preferences"].update(preferences)
        
        # Save to disk
        self._save_user_preferences(user_id)
        
    def _load_user_context(self, user_id):
        """
        Load user context from disk
        
        Args:
            user_id: User ID
        """
        # Initialize empty context
        self.user_contexts[user_id] = {
            "user_id": user_id,
            "preferences": {},
            "history": [],
            "personal_data": {},
            "provider_usage": {}
        }
        
        # Get user data directory
        user_path = self._get_user_data_path(user_id)
        
        # Load preferences
        preferences_path = os.path.join(user_path, "preferences.json")
        if os.path.exists(preferences_path):
            try:
                with open(preferences_path, 'r') as f:
                    self.user_contexts[user_id]["preferences"] = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Failed to load preferences for user {user_id}")
        
        # Load history
        history_path = os.path.join(user_path, "history.json")
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r') as f:
                    self.user_contexts[user_id]["history"] = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Failed to load history for user {user_id}")
        
        # Load personal data
        personal_data_path = os.path.join(user_path, "personal_data.json")
        if os.path.exists(personal_data_path):
            try:
                with open(personal_data_path, 'r') as f:
                    self.user_contexts[user_id]["personal_data"] = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Failed to load personal data for user {user_id}")
        
        # Load provider usage
        usage_path = os.path.join(user_path, "provider_usage.json")
        if os.path.exists(usage_path):
            try:
                with open(usage_path, 'r') as f:
                    self.user_contexts[user_id]["provider_usage"] = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Failed to load provider usage for user {user_id}")
        
        logger.debug(f"Loaded context for user {user_id}")
        
    def _save_user_preferences(self, user_id):
        """
        Save user preferences to disk
        
        Args:
            user_id: User ID
        """
        if user_id not in self.user_contexts:
            return
        
        user_path = self._get_user_data_path(user_id)
        preferences_path = os.path.join(user_path, "preferences.json")
        
        try:
            with open(preferences_path, 'w') as f:
                json.dump(self.user_contexts[user_id].get("preferences", {}), f, indent=2)
                
            # Also save provider usage
            usage_path = os.path.join(user_path, "provider_usage.json")
            with open(usage_path, 'w') as f:
                json.dump(self.user_contexts[user_id].get("provider_usage", {}), f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save preferences for user {user_id}: {str(e)}")
        
    def _save_user_history(self, user_id):
        """
        Save user history to disk
        
        Args:
            user_id: User ID
        """
        if user_id not in self.user_contexts:
            return
        
        user_path = self._get_user_data_path(user_id)
        history_path = os.path.join(user_path, "history.json")
        
        try:
            with open(history_path, 'w') as f:
                json.dump(self.user_contexts[user_id].get("history", []), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history for user {user_id}: {str(e)}")
        
    def _save_personal_data(self, user_id):
        """
        Save user personal data to disk
        
        Args:
            user_id: User ID
        """
        if user_id not in self.user_contexts:
            return
        
        user_path = self._get_user_data_path(user_id)
        personal_data_path = os.path.join(user_path, "personal_data.json")
        
        try:
            with open(personal_data_path, 'w') as f:
                json.dump(self.user_contexts[user_id].get("personal_data", {}), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save personal data for user {user_id}: {str(e)}")
        
    def enrich_query(self, query: str, user_id: str) -> Dict:
        """
        Enrich a query with user context
        
        Args:
            query: Query text
            user_id: User ID
            
        Returns:
            Enriched context dictionary
        """
        # Load user context if not already in memory
        if user_id not in self.user_contexts:
            self._load_user_context(user_id)
        
        user_context = self.user_contexts[user_id]
        
        # Build enriched context
        enriched = {
            "user_preferences": user_context.get("preferences", {}),
            "relevant_history": self._get_relevant_history(query, user_id),
            "personal_data": self._get_relevant_personal_data(query, user_id),
            "provider_usage": user_context.get("provider_usage", {})
        }
        
        return enriched
        
    def _get_relevant_history(self, query: str, user_id: str) -> List[Dict]:
        """
        Get history items relevant to the query
        
        Args:
            query: Query text
            user_id: User ID
            
        Returns:
            List of relevant history items
        """
        if user_id not in self.user_contexts:
            return []
        
        history = self.user_contexts[user_id].get("history", [])
        
        # This is a simplified implementation
        # In a real system, this would use more sophisticated relevance calculation
        
        # Extract key terms from query
        query_terms = set(re.findall(r'\b\w{3,}\b', query.lower()))
        
        relevant_items = []
        for item in history:
            if item.get("type") == "query":
                item_text = item.get("text", "")
            elif item.get("type") == "result":
                item_text = item.get("original_query", "") + " " + item.get("response", "")[:500]
            else:
                continue
                
            # Extract terms from history item
            item_terms = set(re.findall(r'\b\w{3,}\b', item_text.lower()))
            
            # Calculate relevance (simple term overlap)
            if query_terms and item_terms:
                overlap = len(query_terms.intersection(item_terms))
                relevance = overlap / len(query_terms)
                
                # If sufficiently relevant, include it
                if relevance > 0.2:
                    relevant_items.append({
                        "type": item.get("type"),
                        "text": item.get("text", "") or item.get("original_query", ""),
                        "response": item.get("response", ""),
                        "timestamp": item.get("timestamp"),
                        "relevance": relevance
                    })
        
        # Sort by relevance
        relevant_items.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        
        # Return top items
        return relevant_items[:5]
        
    def _get_relevant_personal_data(self, query: str, user_id: str) -> Dict:
        """
        Get personal data relevant to the query
        
        Args:
            query: Query text
            user_id: User ID
            
        Returns:
            Dictionary of relevant personal data
        """
        if user_id not in self.user_contexts:
            return {}
        
        personal_data = self.user_contexts[user_id].get("personal_data", {})
        
        # This is a simplified implementation
        # In a real system, this would use more sophisticated relevance calculation
        
        # Look for specific patterns in the query to determine relevant data
        relevant_data = {}
        
        # Check for personal info references
        if re.search(r'\b(mon nom|mon adresse|mon email|mon adresse email|mon téléphone|mon numéro)\b',
                   query, re.IGNORECASE):
            relevant_data.update({
                "name": personal_data.get("name"),
                "email": personal_data.get("email"),
                "phone": personal_data.get("phone"),
                "address": personal_data.get("address")
            })
        
        # Check for preference references
        if re.search(r'\b(préférences|préféré|aime|n\'aime pas)\b', query, re.IGNORECASE):
            relevant_data.update({
                "preferences": personal_data.get("preferences")
            })
        
        # Remove None values
        return {k: v for k, v in relevant_data.items() if v is not None}
        
    def update_personal_data(self, user_id: str, data: Dict) -> bool:
        """
        Update personal data for a user
        
        Args:
            user_id: User ID
            data: Personal data to update
            
        Returns:
            True if successful, False otherwise
        """
        # Load user context if not already in memory
        if user_id not in self.user_contexts:
            self._load_user_context(user_id)
        
        # Initialize personal_data if needed
        if "personal_data" not in self.user_contexts[user_id]:
            self.user_contexts[user_id]["personal_data"] = {}
        
        # Update personal data
        self.user_contexts[user_id]["personal_data"].update(data)
        
        # Save to disk
        self._save_personal_data(user_id)
        
        return True
        
    def get_user_preferences(self, user_id: str) -> Dict:
        """
        Get user preferences
        
        Args:
            user_id: User ID
            
        Returns:
            User preferences dictionary
        """
        # Load user context if not already in memory
        if user_id not in self.user_contexts:
            self._load_user_context(user_id)
        
        return self.user_contexts[user_id].get("preferences", {})
        
    def get_user_history(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Get recent user history
        
        Args:
            user_id: User ID
            limit: Maximum number of history items to return
            
        Returns:
            List of history items
        """
        # Load user context if not already in memory
        if user_id not in self.user_contexts:
            self._load_user_context(user_id)
        
        history = self.user_contexts[user_id].get("history", [])
        return history[:limit]
        
    def _get_user_data_path(self, user_id):
        """Get the path to a user's data directory"""
        user_path = os.path.join(self.base_path, user_id)
        os.makedirs(user_path, exist_ok=True)
        return user_path