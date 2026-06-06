import asyncio
from app.core.engine import Engine

async def main():
    print("Starting reset process...")
    engine = Engine()
    await engine.reset_state()
    # close the client session manually if it was created
    if hasattr(engine.client, 'session') and engine.client.session:
        await engine.client.session.close()
    print("Reset completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
