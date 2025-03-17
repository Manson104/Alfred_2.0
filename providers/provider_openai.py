"""
OpenAI Provider - Integration with OpenAI services

This module provides integration with OpenAI's various AI services
including text generation (GPT models) and image generation (DALL-E).
"""

import logging
import time
import json
import os
from typing import Dict, List, Any, Optional, Union

try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from provider_base import AIProvider

# Setup logging
logger = logging.getLogger("OpenAIProvider")

class OpenAIProvider(AIProvider):
    """Provider for OpenAI's text and image generation services"""
    
    def __init__(self):
        """Initialize the OpenAI provider"""
        self.client = None
        self.config = {}
        self.models = []
        self.default_model = "gpt-4o"
        self.initialized = False
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the provider with the given configuration
        
        Args:
            config: OpenAI configuration including API key
            
        Returns:
            True if initialization was successful
        """
        if not OPENAI_AVAILABLE:
            logger.error("OpenAI package is not installed. Please install with: pip install openai")
            return False
        
        self.config = config
        
        # Get API key from config or environment
        api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("No OpenAI API key provided")
            return False
        
        try:
            # Initialize the client
            self.client = OpenAI(api_key=api_key)
            
            # Set default model
            self.default_model = config.get("default_model", "gpt-4o")
            
            # Try to list models to verify API key
            response = self.client.models.list()
            self.models = [model.id for model in response.data]
            
            self.initialized = True
            logger.info(f"OpenAI provider initialized with {len(self.models)} available models")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI provider: {str(e)}")
            return False
    
    def send_query(self, 
                  query: str, 
                  context: Optional[Dict[str, Any]] = None, 
                  options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a query to OpenAI
        
        Args:
            query: The user's query text
            context: Additional context for the query
            options: OpenAI-specific options for this query
            
        Returns:
            Response dictionary
        """
        if not self.initialized or not self.client:
            return {
                "success": False,
                "response": "OpenAI provider is not initialized",
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
        
        # Determine what type of query this is
        if "image" in options.get("type", "").lower() or self._is_image_request(query):
            return self._handle_image_generation(query, context, options)
        else:
            return self._handle_text_generation(query, context, options)
    
    def _handle_text_generation(self, query, context, options):
        """Handle text generation requests"""
        try:
            # Get model to use
            model = options.get("model") or self.default_model
            if model not in self.models:
                model = self.default_model
            
            # Prepare message history
            messages = self._prepare_messages(query, context)
            
            # Extract additional parameters
            temperature = options.get("temperature", 0.7)
            max_tokens = options.get("max_tokens", 1500)
            
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
            if response.choices and len(response.choices) > 0:
                response_text = response.choices[0].message.content
            else:
                response_text = ""
            
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
            logger.error(f"Error calling OpenAI API: {str(e)}")
            return {
                "success": False,
                "response": f"Error: {str(e)}",
                "error": str(e),
                "usage": {},
                "metadata": {}
            }
    
    def _handle_image_generation(self, query, context, options):
        """Handle image generation requests"""
        try:
            # Extract image generation options
            size = options.get("size", "1024x1024")  # Default is 1024x1024
            quality = options.get("quality", "standard")  # or "hd"
            style = options.get("style", "vivid")  # or "natural"
            model = options.get("model", "dall-e-3")
            
            # Clean the prompt
            prompt = self._clean_image_prompt(query)
            
            # Call the API
            start_time = time.time()
            response = self.client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
                n=1  # Generate 1 image
            )
            end_time = time.time()
            
            # Get the image URL
            if response.data and len(response.data) > 0:
                image_url = response.data[0].url
                image_prompt = response.data[0].revised_prompt if hasattr(response.data[0], 'revised_prompt') else prompt
                
                # Calculate cost (simplified)
                cost = 0.04  # Approximate cost for standard DALL-E 3 image
                
                return {
                    "success": True,
                    "response": f"J'ai généré cette image basée sur votre demande. Voici l'URL: {image_url}",
                    "raw_response": response,
                    "image_url": image_url,
                    "usage": {
                        "estimated_cost": cost
                    },
                    "metadata": {
                        "model": model,
                        "size": size,
                        "quality": quality,
                        "style": style,
                        "prompt": prompt,
                        "revised_prompt": image_prompt,
                        "response_time": end_time - start_time
                    }
                }
            else:
                return {
                    "success": False,
                    "response": "Aucune image n'a été générée",
                    "error": "No images returned",
                    "usage": {},
                    "metadata": {}
                }
                
        except Exception as e:
            logger.error(f"Error generating image with DALL-E: {str(e)}")
            return {
                "success": False,
                "response": f"Erreur lors de la génération de l'image: {str(e)}",
                "error": str(e),
                "usage": {},
                "metadata": {}
            }
    
    def _prepare_messages(self, query, context):
        """
        Prepare message history for the OpenAI API
        
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
        
        # Add personal data context if available
        personal_data = context.get("personal_data", {})
        if personal_data:
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
    
    def _calculate_cost(self, usage, model):
        """
        Calculate estimated cost based on token usage
        
        Args:
            usage: Token usage information
            model: Model used
            
        Returns:
            Estimated cost in USD
        """
        # Pricing as of May 2023 (simplified)
        pricing = {
            "gpt-4o": {
                "input": 0.01 / 1000,  # $0.01 per 1K input tokens
                "output": 0.03 / 1000  # $0.03 per 1K output tokens
            },
            "gpt-4": {
                "input": 0.03 / 1000,
                "output": 0.06 / 1000
            },
            "gpt-3.5-turbo": {
                "input": 0.0015 / 1000,
                "output": 0.002 / 1000
            }
        }
        
        # Use gpt-3.5-turbo pricing as default
        model_pricing = pricing.get(model, pricing["gpt-3.5-turbo"])
        
        input_cost = usage.prompt_tokens * model_pricing["input"]
        output_cost = usage.completion_tokens * model_pricing["output"]
        
        return input_cost + output_cost
    
    def _is_image_request(self, query):
        """
        Determine if a query is requesting image generation
        
        Args:
            query: Query text
            
        Returns:
            True if this appears to be an image generation request
        """
        import re
        
        # Check for common image generation phrases
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