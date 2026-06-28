import os
import asyncio
from groq import Groq

async def call_llm(system_prompt: str, message: str,
                   max_tokens: int = 1024) -> str:
    def _sync_call():
        client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content

    return await asyncio.to_thread(_sync_call)