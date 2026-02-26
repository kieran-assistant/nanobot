# nanobot/cli/commands.py
import asyncio
import typer
from typing import Optional
from loguru import logger
from nanobot.runtime.bus import bus
from nanobot.runtime.agent_loop import agent

app = typer.Typer(help="Nanobot-DB CLI")

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)

async def initialize_system():
    from nanobot.db.engine import db
    from nanobot.core.adapter import initialize_kernel
    
    await db.connect()
    await initialize_kernel()
    
    def print_response(event):
        typer.echo(f"Agent: {event.payload['content']}")
    bus.subscribe("agent.response", print_response)

@app.command()
def start():
    """
    Start the interactive CLI chat.
    """
    typer.echo("Initializing Nanobot-DB...")
    run_async(initialize_system())
    
    bus.subscribe("user.message", agent.process_event)
    
    typer.echo("System ready. Type 'exit' to quit.")
    
    while True:
        try:
            user_input = typer.prompt("You")
            if user_input.lower() == 'exit':
                typer.echo("Shutting down...")
                break
            
            asyncio.get_event_loop().run_until_complete(
                bus.publish("user.message", {"content": user_input})
            )
            
        except KeyboardInterrupt:
            break

@app.command()
def evolve():
    """
    Manually trigger the evolution engine.
    """
    typer.echo("🔄 Triggering Evolution Cycle...")
    async def run_evolve():
        from nanobot.db.engine import db
        from nanobot.meta.evolution_engine import evolution_engine
        await db.connect()
        await evolution_engine.run_cycle()
        await db.disconnect()
    run_async(run_evolve())
    typer.echo("✅ Evolution Cycle Finished.")

@app.command()
def status():
    """
    Display current system status.
    """
    async def check_status():
        from nanobot.db.engine import db
        await db.connect()
        
        tools = await db.fetch("SELECT component_name, source_layer FROM system_model WHERE component_type = 'tool'")
        
        typer.echo("\n--- Registered Tools ---")
        for tool in tools:
            typer.echo(f"- {tool['component_name']} ({tool['source_layer']})")
            
        queue = await db.fetch("SELECT count(*) FROM evolution_queue WHERE status = 'pending'")
        typer.echo(f"\nPending Evolution Tasks: {queue[0]['count']}")
        
        await db.disconnect()
        
    run_async(check_status())

if __name__ == "__main__":
    app()
