"""
Provider Factory - Creates and manages AI provider instances

This module centralizes the creation and management of AI providers.
"""

import logging
import importlib
import os
from typing import Dict, List, Any, Optional, Union

# Setup logging
logger = logging.getLogger("ProviderFactory")

class ProviderFactory:
    """Factory for creating and managing AI provider instances"""
    
    def __init__(self, base_path="~/.alfred"):
        """
        Initialize the provider factory
        
        Args:
            base_path: Base directory for provider modules
        """
        self.base_path = os.path.expanduser(base_path)
        self.provider_modules = {}
        self.available_providers = self._discover_providers()
        
    def _discover_providers(self) -> List[str]:
        """
        Discover available provider modules
        
        Returns:
            List of available provider IDs
        """
        providers = []
        
        # Check for built-in providers first
        builtin_providers = ["openai", "anthropic", "perplexity"]
        for provider_id in builtin_providers:
            module_name = f"provider_{provider_id}"
            try:
                # Try to import the module
                module = importlib.import_module(module_name)
                if hasattr(module, 'create_provider'):
                    self.provider_modules[provider_id] = module
                    providers.append(provider_id)
                    logger.info(f"Discovered built-in provider: {provider_id}")
            except ImportError:
                logger.debug(f"Built-in provider {provider_id} not available")
        
        # Now check for custom providers in the providers directory
        providers_dir = os.path.join(self.base_path, "providers")
        if os.path.exists(providers_dir) and os.path.isdir(providers_dir):
            for filename in os.listdir(providers_dir):
                if filename.startswith("provider_") and filename.endswith(".py"):
                    provider_id = filename[9:-3]  # Remove 'provider_' prefix and '.py' suffix
                    if provider_id in self.provider_modules:
                        continue  # Skip if already loaded as built-in
                    
                    try:
                        # Try to load the module from file
                        module_path = os.path.join(providers_dir, filename)
                        spec = importlib.util.spec_from_file_location(f"provider_{provider_id}", module_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        if hasattr(module, 'create_provider'):
                            self.provider_modules[provider_id] = module
                            providers.append(provider_id)
                            logger.info(f"Discovered custom provider: {provider_id}")
                    except Exception as e:
                        logger.error(f"Error loading custom provider {provider_id}: {str(e)}")
        
        return providers
    
    def create_provider(self, provider_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Create a provider instance
        
        Args:
            provider_id: ID of the provider to create
            config: Provider configuration
            
        Returns:
            Provider instance or None if creation failed
        """
        if provider_id not in self.provider_modules:
            logger.error(f"Unknown provider: {provider_id}")
            return None
        
        try:
            module = self.provider_modules[provider_id]
            return module.create_provider(config)
        except Exception as e:
            logger.error(f"Error creating provider {provider_id}: {str(e)}")
            return None
    
    def get_available_providers(self) -> List[str]:
        """
        Get the list of available providers
        
        Returns:
            List of provider IDs
        """
        return self.available_providers
    
    def reload_providers(self) -> List[str]:
        """
        Reload the provider modules
        
        Returns:
            Updated list of available providers
        """
        self.provider_modules = {}
        self.available_providers = self._discover_providers()
        return self.available_providers


# Example usage
if __name__ == "__main__":
    # Create provider factory
    factory = ProviderFactory()
    
    # List available providers
    providers = factory.get_available_providers()
    print(f"Available providers: {providers}")
    
    # Create OpenAI provider
    if "openai" in providers:
        config = {"api_key": os.environ.get("OPENAI_API_KEY")}
        provider = factory.create_provider("openai", config)
        print(f"Created {provider.get_name()} provider")
        print(f"Available models: {provider.get_capabilities().get('models', [])}")
