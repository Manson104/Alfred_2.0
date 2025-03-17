#!/usr/bin/env python3
"""
Alfred - Intelligent Personal Assistant

Main entry point for the Alfred system.
This script initializes the core components and provides CLI interface.
"""

import os
import sys
import time
import argparse
import signal
import json
from typing import List, Dict, Any

# Import core components
from core.alfred_core import AlfredCore

# Import logging system
from utils.logger import initialize as initialize_logging, get_logger

# Setup logger
logger = get_logger("Main")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Alfred - Intelligent Personal Assistant')
    
    parser.add_argument('--config', '-c', type=str, default='~/.alfred/config.json',
                        help='Path to configuration file')
    
    parser.add_argument('--list-modules', '-l', action='store_true',
                        help='List available modules and exit')
    
    parser.add_argument('--load', type=str, nargs='+',
                        help='Load specific modules or agents at startup')
    
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')

    parser.add_argument('--log-file', type=str,
                        help='Specify a custom log file location')
    
    return parser.parse_args()

def handle_signal(signum, frame):
    """Handle termination signals"""
    if hasattr(handle_signal, 'alfred'):
        logger.info(f"Received signal {signum}, shutting down...")
        handle_signal.alfred.stop()
    sys.exit(0)

def list_available_modules(alfred):
    """List all available modules and agents"""
    print("\nAvailable Modules:")
    print("=================")
    
    modules = alfred.module_manager.list_available_modules("module")
    for module in sorted(modules, key=lambda m: m['id']):
        status = "✓" if module.get('locally_available') else " "
        print(f"[{status}] {module['id']} - {module['name']} (v{module['version']})")
    
    print("\nAvailable Agents:")
    print("================")
    
    agents = alfred.module_manager.list_available_modules("agent")
    for agent in sorted(agents, key=lambda a: a['id']):
        status = "✓" if agent.get('locally_available') else " "
        print(f"[{status}] {agent['id']} - {agent['name']} (v{agent['version']})")
    
    print("\n✓ = Locally available\n")

def interactive_cli(alfred):
    """Provide an interactive CLI for Alfred"""
    print(f"\nAlfred CLI")
    print("==========")
    print("Type 'help' for available commands")
    
    commands = {
        'help': "Show this help message",
        'list': "List available modules and agents",
        'status': "Show system status",
        'load <module_id>': "Load a module or agent",
        'unload <module_id>': "Unload a module or agent",
        'send <topic> <message>': "Send a message to the message bus",
        'state': "Display the current system state",
        'restart': "Restart Alfred",
        'log <level>': "Change the global logging level (DEBUG, INFO, WARNING, ERROR)",
        'exit': "Exit Alfred"
    }
    
    running = True
    while running and alfred.running:
        try:
            cmd = input("\nalfred> ").strip()
            parts = cmd.split()
            
            if not parts:
                continue
                
            if parts[0] == 'exit':
                running = False
                alfred.stop()
                
            elif parts[0] == 'help':
                for cmd, desc in commands.items():
                    print(f"{cmd:<20} - {desc}")
                    
            elif parts[0] == 'list':
                list_available_modules(alfred)
                
            elif parts[0] == 'status':
                status = alfred.state_manager.get("system_status", "unknown")
                uptime = time.time() - alfred.state_manager.get("start_time", time.time())
                loaded_modules = alfred.state_manager.get("loaded_modules", [])
                loaded_agents = alfred.state_manager.get("loaded_agents", [])
                
                print(f"\nSystem Status: {status}")
                print(f"Uptime: {int(uptime)} seconds")
                print(f"Loaded modules: {len(loaded_modules)}")
                print(f"Loaded agents: {len(loaded_agents)}")
                
                if loaded_modules:
                    print("\nLoaded Modules:")
                    for module in loaded_modules:
                        print(f"  - {module}")
                        
                if loaded_agents:
                    print("\nLoaded Agents:")
                    for agent in loaded_agents:
                        print(f"  - {agent}")
                
            elif parts[0] == 'load' and len(parts) > 1:
                module_id = parts[1]
                # Determine if it's an agent or module
                module_info = alfred.module_manager.get_module_info(module_id)
                
                if not module_info or "error" in module_info:
                    print(f"Unknown module: {module_id}")
                elif module_info.get("type") == "agent":
                    if alfred._load_agent(module_id):
                        print(f"Agent {module_id} loaded successfully")
                    else:
                        print(f"Failed to load agent {module_id}")
                else:
                    if alfred._load_module(module_id):
                        print(f"Module {module_id} loaded successfully")
                    else:
                        print(f"Failed to load module {module_id}")
                
            elif parts[0] == 'unload' and len(parts) > 1:
                module_id = parts[1]
                
                if module_id in alfred.agents:
                    if alfred._unload_agent(module_id):
                        print(f"Agent {module_id} unloaded successfully")
                    else:
                        print(f"Failed to unload agent {module_id}")
                else:
                    if alfred._unload_module(module_id):
                        print(f"Module {module_id} unloaded successfully")
                    else:
                        print(f"Failed to unload module {module_id}")
                
            elif parts[0] == 'send' and len(parts) >= 3:
                topic = parts[1]
                message = " ".join(parts[2:])
                
                alfred.message_bus.publish(topic, {
                    "content": message
                }, sender="cli")
                
                print(f"Message sent to topic: {topic}")
                
            elif parts[0] == 'state':
                state = alfred.state_manager.get_all()
                print(json.dumps(state, indent=2))
                
            elif parts[0] == 'restart':
                print("Restarting Alfred...")
                alfred.stop()
                alfred.start()
                
            elif parts[0] == 'log' and len(parts) > 1:
                level = parts[1].upper()
                if level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                    # Get the logger system
                    logger_system = initialize_logging()
                    logger_system.set_global_level(level)
                    print(f"Global logging level set to {level}")
                else:
                    print(f"Invalid log level: {level}")
                    print("Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL")
                
            else:
                print(f"Unknown command: {cmd}")
                print("Type 'help' for available commands")
                
        except KeyboardInterrupt:
            print("\nUse 'exit' to quit")
        except Exception as e:
            print(f"Error: {str(e)}")

def main():
    """Main entry point"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Load config file to initialize logging
    config_path = os.path.expanduser(args.config)
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                logging_config = config.get("logging", {})
                
                # Override config with command line arguments
                if args.debug:
                    logging_config["log_level"] = "DEBUG"
                if args.log_file:
                    logging_config["log_dir"] = os.path.dirname(args.log_file)
                    
                # Initialize logging
                initialize_logging(logging_config)
        except Exception as e:
            # Cannot use logger yet, use print
            print(f"Error loading config: {str(e)}")
            # Set up basic logging
            initialize_logging({"log_level": "DEBUG" if args.debug else "INFO"})
    else:
        # Set up basic logging
        initialize_logging({"log_level": "DEBUG" if args.debug else "INFO"})
        
    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Create Alfred core
    alfred = AlfredCore(config_path=args.config)
    handle_signal.alfred = alfred  # Store for signal handler
    
    # Start Alfred
    try:
        alfred.start()
        
        # If --list-modules, just list and exit
        if args.list_modules:
            list_available_modules(alfred)
            alfred.stop()
            return
            
        # Load specific modules if requested
        if args.load:
            for module_id in args.load:
                # Check if it's an agent or module
                module_info = alfred.module_manager.get_module_info(module_id)
                
                if not module_info or "error" in module_info:
                    logger.warning(f"Unknown module: {module_id}")
                elif module_info.get("type") == "agent":
                    if alfred._load_agent(module_id):
                        logger.info(f"Agent {module_id} loaded successfully")
                    else:
                        logger.error(f"Failed to load agent {module_id}")
                else:
                    if alfred._load_module(module_id):
                        logger.info(f"Module {module_id} loaded successfully")
                    else:
                        logger.error(f"Failed to load module {module_id}")
        
        # Start interactive CLI
        interactive_cli(alfred)
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)
    finally:
        # Ensure Alfred is stopped properly
        if alfred.running:
            alfred.stop()

if __name__ == "__main__":
    main()
