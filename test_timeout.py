import asyncio
from dotenv import load_dotenv
from getstream import AsyncStream

load_dotenv()

async def test_getstream():
    client = AsyncStream()
    print("Stream client initialized. Timeout is:", client.timeout)
    print("Testing create_user...")
    try:
        user = await client.create_user(name="Test User", id="test-timeout-user")
        print("Success! User:", user)
    except Exception as e:
        print("Failed:", type(e).__name__, str(e))

if __name__ == "__main__":
    asyncio.run(test_getstream())
