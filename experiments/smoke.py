"""Smoke test: one Noul call against Jev. Run: .venv/bin/python experiments/smoke.py"""
import asyncio
from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, Noul

load_dotenv()


async def main():
    async with AsyncTypeSafeClient() as client:
        r = await client.system_one(
            state={"document": "I was charged twice. Please fix this ASAP."},
            questions={"billing": Noul(instructions="Is this about billing?")},
        )
        print(r.nouls["billing"].noul)


asyncio.run(main())
