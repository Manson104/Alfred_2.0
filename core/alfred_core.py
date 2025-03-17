"""
Alfred Core - The central component of the Alfred assistant system

This component is responsible for:
- Initializing the system
- Coordinating communication between modules and agents
- Managing the global state
- Handling system events and lifecycle
"""

import os
import sys
import json
import threading
import time
from typing import Dict, List, Any, Optional, Callable, Union
from queue import Queue, Empty

# Import the module manager
from module_manager import ModuleManager

# Import du système de logging centralisé
from utils.logger import initialize as initialize_logging, get_logger

# Setup logger
logger = get_logger("AlfredCore")

class MessageBus:
    """
    Handles message passing between components in the system
    """
    
    def __init__(self):
        self.subscribers = {}
        self.message_queue = Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None
        self.logger = get_logger("core.MessageBus")
        
    def start(self):
        """Start the message processing thread"""
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._process_messages)
        self._worker_thread.daemon = True
        self._worker_thread.start()
        self.logger.info("Message bus started")
        
    def stop(self):
        """Stop the message processing thread"""
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        self.logger.info("Message bus stopped")
        
    def _process_messages(self):
        """Worker thread to process messages"""
        while not self._stop_event.is_set():
            try:
                # Get message with timeout to allow checking stop_event periodically
                try:
                    message = self.message_queue.get(timeout=0.5)
                except Empty:
                    continue
                    
                topic = message.get("topic", "")
                
                # Dispatch to subscribers
                if topic in self.subscribers:
                    for callback in self.subscribers[topic]:
                        try:
                            callback(message)
                        except Exception as e:
                            self.logger.error(f"Error in message handler for topic {topic}: {str(e)}", exc_info=True)
                
                # General subscribers (subscribe to all messages)
                if "*" in self.subscribers:
                    for callback in self.subscribers["*"]:
                        try:
                            callback(message)
                        except Exception as e:
                            self.logger.error(f"Error in global message handler: {str(e)}", exc_info=True)
                
                self.message_queue.task_done()
                
            except Exception as e:
                self.logger.error(f"Error in message processing: {str(e)}", exc_info=True)
                time.sleep(0.1)  # Prevent tight loop in case of recurring errors
    
    def publish(self, topic: str, data: Any = None, sender: str = None):
        """
        Publish a message to a topic
        
        Args:
            topic: Message topic
            data: Message payload
            sender: ID of the sending component
        """
        message = {
            "topic": topic,
            "data": data,
            "sender": sender,
            "timestamp": time.time()
        }
        self.message_queue.put(message)
        self.logger.debug(f"Message published to {topic} by {sender}")
        
    def subscribe(self, topic: str, callback: Callable[[Dict], None]):
        """
        Subscribe to a topic
        
        Args:
            topic: Topic to subscribe to, use "*" for all messages
            callback: Function to call when a message is received
        """
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)
        self.logger.debug(f"New subscriber added to topic: {topic}")
        
    def unsubscribe(self, topic: str, callback: Callable[[Dict], None]):
        """
        Unsubscribe from a topic
        
        Args:
            topic: Topic to unsubscribe from
            callback: Callback function to remove
        """
        if topic in self.subscribers and callback in self.subscribers[topic]:
            self.subscribers[topic].remove(callback)
            self.logger.debug(f"Subscriber removed from topic: {topic}")
            
            # Clean up empty subscriber lists
            if not self.subscribers[topic]:
                del self.subscribers[topic]


class StateManager:
    """
    Manages the global state of the system and notifies components of changes
    """
    
    def __init__(self, message_bus: MessageBus):
        self.state = {}
        self.message_bus = message_bus
        self.logger = get_logger("core.StateManager")
        
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the state"""
        return self.state.get(key, default)
        
    def set(self, key: str, value: Any, publish: bool = True):
        """
        Set a value in the state
        
        Args:
            key: State key
            value: State value
            publish: Whether to publish a state change message
        """
        old_value = self.state.get(key)
        self.state[key] = value
        
        if publish and old_value != value:
            self.logger.debug(f"State changed: {key} = {value}")
            self.message_bus.publish("state_changed", {
                "key": key,
                "old_value": old_value,
                "new_value": value
            }, sender="state_manager")
            
    def update(self, new_state: Dict):
        """
        Update multiple state values at once
        
        Args:
            new_state: Dictionary of key-value pairs to update
        """
        for key, value in new_state.items():
            self.set(key, value)
            
    def get_all(self) -> Dict:
        """Get a copy of the entire state"""
        return self.state.copy()


class AlfredCore:
    """
    Main class that ties all components together and manages the system
    """
    
    def __init__(self, config_path: str = "~/.alfred/config.json"):
        """
        Initialize the Alfred core system
        
        Args:
            config_path: Path to the configuration file
        """
        self.config_path = os.path.expanduser(config_path)
        self.config = self._load_config()
        
        # Initialize logging
        logging_config = self.config.get("logging", {})
        initialize_logging(logging_config)
        self.logger = get_logger("core.Alfred")
        
        # Initialize core components
        self.message_bus = MessageBus()
        self.state_manager = StateManager(self.message_bus)
        self.module_manager = ModuleManager(
            github_org=self.config.get("github_org", "alfred-project"),
            base_path=self.config.get("base_path", "~/.alfred"),
            sync_time=self.config.get("sync_time", "03:00")
        )
        
        # Loaded agents and active components
        self.agents = {}
        self.running = False
        
        self.logger.info("Alfred Core initialized")
        
        # Subscribe to message bus for internal events
        self.message_bus.subscribe("module_loaded", self._handle_module_loaded)
        self.message_bus.subscribe("module_unloaded", self._handle_module_unloaded)
        
    def _load_config(self) -> Dict:
        """Load configuration from file or create default"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Corrupted config file: {self.config_path}")
        
        # Default configuration
        default_config = {
            "name": "Alfred",
            "version": "0.1.0",
            "github_org": "alfred-project",
            "base_path": "~/.alfred",
            "sync_time": "03:00",
            "startup_modules": [],
            "logging": {
                "log_level": "INFO",
                "log_dir": "~/.alfred/logs",
                "console_output": True,
                "module_levels": {
                    "core.Alfred": "INFO",
                    "core.MessageBus": "INFO",
                    "ModuleManager": "INFO"
                }
            }
        }
        
        # Create directories and save default config
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
            
        return default_config
        
    def save_config(self):
        """Save current configuration to file"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        self.logger.debug("Configuration saved")
        
    def start(self):
        """Start the Alfred system"""
        if self.running:
            self.logger.warning("Alfred is already running")
            return
            
        self.logger.info("Starting Alfred")
        
        try:
            # Start the message bus
            self.message_bus.start()
            
            # Register core message handlers
            self.message_bus.subscribe("core_command", self._handle_core_command)
            
            # Set initial state
            self.state_manager.set("system_status", "starting")
            self.state_manager.set("start_time", time.time())
            
            # Load startup modules defined in config
            for module_id in self.config.get("startup_modules", []):
                self._load_module(module_id)
                
            # Mark system as running
            self.running = True
            self.state_manager.set("system_status", "running")
            
            self.logger.info("Alfred started successfully")
            
            # Publish system startup message
            self.message_bus.publish("system", {
                "event": "startup",
                "version": self.config.get("version", "0.1.0")
            }, sender="core")
            
        except Exception as e:
            self.logger.error(f"Failed to start Alfred: {str(e)}", exc_info=True)
            self.stop()
            raise
            
    def stop(self):
        """Stop the Alfred system"""
        if not self.running:
            self.logger.warning("Alfred is not running")
            return
            
        self.logger.info("Stopping Alfred")
        
        try:
            # Mark system as stopping
            self.state_manager.set("system_status", "stopping")
            
            # Publish system shutdown message
            self.message_bus.publish("system", {
                "event": "shutdown",
                "uptime": time.time() - self.state_manager.get("start_time", time.time())
            }, sender="core")
            
            # Unload all agents
            for agent_id in list(self.agents.keys()):
                self._unload_agent(agent_id)
                
            # Stop message bus
            self.message_bus.stop()
            
            # Mark system as stopped
            self.running = False
            self.state_manager.set("system_status", "stopped")
            
            self.logger.info("Alfred stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping Alfred: {str(e)}", exc_info=True)
            # Ensure we're marked as stopped even if there's an error
            self.running = False
            
    def _handle_core_command(self, message):
        """
        Handle commands directed at the core system
        
        Args:
            message: Command message
        """
        data = message.get("data", {})
        command = data.get("command")
        
        if command == "stop":
            self.logger.info("Received stop command")
            self.stop()
            
        elif command == "restart":
            self.logger.info("Received restart command")
            self.stop()
            self.start()
            
        elif command == "load_module":
            module_id = data.get("module_id")
            if module_id:
                self._load_module(module_id)
            else:
                self.logger.error("load_module command missing module_id")
                
        elif command == "unload_module":
            module_id = data.get("module_id")
            if module_id:
                self._unload_module(module_id)
            else:
                self.logger.error("unload_module command missing module_id")
                
        elif command == "load_agent":
            agent_id = data.get("agent_id")
            if agent_id:
                self._load_agent(agent_id)
            else:
                self.logger.error("load_agent command missing agent_id")
                
        elif command == "unload_agent":
            agent_id = data.get("agent_id")
            if agent_id:
                self._unload_agent(agent_id)
            else:
                self.logger.error("unload_agent command missing agent_id")
                
        else:
            self.logger.warning(f"Unknown core command: {command}")
            
    def _handle_module_loaded(self, message):
        """Handle module loaded events"""
        data = message.get("data", {})
        module_id = data.get("module_id")
        
        if module_id:
            # Update system state with loaded modules
            loaded_modules = self.state_manager.get("loaded_modules", [])
            if module_id not in loaded_modules:
                loaded_modules.append(module_id)
                self.state_manager.set("loaded_modules", loaded_modules)
                
    def _handle_module_unloaded(self, message):
        """Handle module unloaded events"""
        data = message.get("data", {})
        module_id = data.get("module_id")
        
        if module_id:
            # Update system state with loaded modules
            loaded_modules = self.state_manager.get("loaded_modules", [])
            if module_id in loaded_modules:
                loaded_modules.remove(module_id)
                self.state_manager.set("loaded_modules", loaded_modules)
                
    def _load_module(self, module_id: str) -> bool:
        """
        Load a module
        
        Args:
            module_id: ID of the module to load
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Loading module: {module_id}")
        
        try:
            # Check if we need to download the module
            module_info = self.module_manager.get_module_info(module_id)
            if not module_info.get("locally_available", False):
                self.logger.info(f"Module {module_id} not available locally, downloading...")
                if not self.module_manager.download_module(module_id):
                    self.logger.error(f"Failed to download module {module_id}")
                    return False
            
            # Load the module
            module = self.module_manager.load_module(module_id)
            if not module:
                # Try fallback if normal loading fails
                self.logger.warning(f"Failed to load module {module_id}, trying fallback...")
                if self.module_manager.use_fallback(module_id):
                    module = self.module_manager.load_module(module_id)
                    
            if not module:
                self.logger.error(f"Failed to load module {module_id} even with fallback")
                return False
                
            # Publish module loaded event
            self.message_bus.publish("module_loaded", {
                "module_id": module_id
            }, sender="core")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading module {module_id}: {str(e)}", exc_info=True)
            return False
            
    def _unload_module(self, module_id: str) -> bool:
        """
        Unload a module
        
        Args:
            module_id: ID of the module to unload
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Unloading module: {module_id}")
        
        try:
            # Unload the module
            if not self.module_manager.unload_module(module_id):
                self.logger.error(f"Failed to unload module {module_id}")
                return False
                
            # Publish module unloaded event
            self.message_bus.publish("module_unloaded", {
                "module_id": module_id
            }, sender="core")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error unloading module {module_id}: {str(e)}", exc_info=True)
            return False
            
    def _load_agent(self, agent_id: str) -> bool:
        """
        Load an agent
        
        Args:
            agent_id: ID of the agent to load
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Loading agent: {agent_id}")
        
        # Agents are special modules that are tracked separately
        if agent_id in self.agents:
            self.logger.warning(f"Agent {agent_id} is already loaded")
            return True
            
        try:
            # Load the agent module
            if not self._load_module(agent_id):
                return False
                
            # Get the loaded module
            agent_module = self.module_manager.loaded_modules.get(agent_id)
            if not agent_module:
                self.logger.error(f"Agent module {agent_id} not found in loaded modules")
                return False
                
            # Check if it has the required agent interface
            if not hasattr(agent_module, "start_agent") or not hasattr(agent_module, "stop_agent"):
                self.logger.error(f"Module {agent_id} does not have the required agent interface")
                self._unload_module(agent_id)
                return False
                
            # Start the agent
            agent_instance = agent_module.start_agent(
                message_bus=self.message_bus,
                state_manager=self.state_manager
            )
            
            # Store the agent instance
            self.agents[agent_id] = {
                "module": agent_module,
                "instance": agent_instance
            }
            
            # Publish agent loaded event
            self.message_bus.publish("agent_loaded", {
                "agent_id": agent_id
            }, sender="core")
            
            # Update system state
            loaded_agents = self.state_manager.get("loaded_agents", [])
            if agent_id not in loaded_agents:
                loaded_agents.append(agent_id)
                self.state_manager.set("loaded_agents", loaded_agents)
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading agent {agent_id}: {str(e)}", exc_info=True)
            # Clean up if there was an error
            if agent_id in self.module_manager.loaded_modules:
                self._unload_module(agent_id)
            return False
            
    def _unload_agent(self, agent_id: str) -> bool:
        """
        Unload an agent
        
        Args:
            agent_id: ID of the agent to unload
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Unloading agent: {agent_id}")
        
        if agent_id not in self.agents:
            self.logger.warning(f"Agent {agent_id} is not loaded")
            return True
            
        try:
            # Get the agent
            agent_data = self.agents[agent_id]
            
            # Stop the agent
            agent_data["module"].stop_agent(agent_data["instance"])
            
            # Remove from agents dict
            del self.agents[agent_id]
            
            # Unload the module
            self._unload_module(agent_id)
            
            # Publish agent unloaded event
            self.message_bus.publish("agent_unloaded", {
                "agent_id": agent_id
            }, sender="core")
            
            # Update system state
            loaded_agents = self.state_manager.get("loaded_agents", [])
            if agent_id in loaded_agents:
                loaded_agents.remove(agent_id)
                self.state_manager.set("loaded_agents", loaded_agents)
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error unloading agent {agent_id}: {str(e)}", exc_info=True)
            return False

# Example usage
if __name__ == "__main__":
    # Create and start Alfred
    alfred = AlfredCore()
    alfred.start()
    
    try:
        # Keep the main thread alive
        while alfred.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down Alfred...")
        alfred.stop()