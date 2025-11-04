#!/usr/bin/env python3
"""Simple test script to verify OpenAI API key and account status."""

import os
import sys
from dotenv import load_dotenv
import httpx
import asyncio

# Load .env file
load_dotenv()

async def test_openai():
    """Test OpenAI API with a simple request."""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not found in environment variables")
        print("   Make sure your .env file exists and contains OPENAI_API_KEY=...")
        sys.exit(1)
    
    # Mask the key for display
    masked_key = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 11 else "***"
    print(f"🔑 Using API key: {masked_key} (length: {len(api_key)})")
    
    # Simple test prompt
    test_prompt = "Say 'Hello, OpenAI!' and nothing else."
    
    print("\n📤 Sending test request to OpenAI...")
    print(f"   Prompt: {test_prompt}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4",  # Try gpt-4 first
                    "messages": [
                        {"role": "user", "content": test_prompt}
                    ],
                    "max_tokens": 50,
                },
            )
            
            print(f"\n📥 Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                print(f"✅ SUCCESS! OpenAI API is working.")
                print(f"   Response: {content}")
                
                if "usage" in data:
                    usage = data["usage"]
                    print(f"\n📊 Token usage:")
                    print(f"   Prompt tokens: {usage.get('prompt_tokens', 'N/A')}")
                    print(f"   Completion tokens: {usage.get('completion_tokens', 'N/A')}")
                    print(f"   Total tokens: {usage.get('total_tokens', 'N/A')}")
                
                return True
            else:
                error_text = response.text
                print(f"❌ ERROR: Request failed with status {response.status_code}")
                print(f"   Response: {error_text}")
                
                # Try to parse JSON error
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_info = error_data["error"]
                        error_message = error_info.get("message", "Unknown error")
                        error_type = error_info.get("type", "Unknown type")
                        print(f"\n   Error type: {error_type}")
                        print(f"   Error message: {error_message}")
                        
                        if "quota" in error_message.lower() or "billing" in error_message.lower():
                            print("\n⚠️  QUOTA/BILLING ISSUE DETECTED:")
                            print("   Your OpenAI account has exceeded its quota or has billing issues.")
                            print("   Please check:")
                            print("   1. Your OpenAI account has credits/billing set up")
                            print("   2. Visit https://platform.openai.com/account/billing")
                            print("   3. Visit https://platform.openai.com/usage to check usage")
                except:
                    pass
                
                return False
                
        except httpx.TimeoutException:
            print("❌ ERROR: Request timed out after 30 seconds")
            return False
        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}")
            return False


async def test_gpt35_turbo():
    """Try with GPT-3.5 Turbo as a fallback (cheaper, might work if GPT-4 is quota-limited)."""
    api_key = os.getenv("OPENAI_API_KEY")
    
    print("\n🔄 Trying with gpt-3.5-turbo (cheaper alternative)...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "user", "content": "Say 'Hello!' and nothing else."}
                    ],
                    "max_tokens": 10,
                },
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                print(f"✅ SUCCESS with gpt-3.5-turbo!")
                print(f"   Response: {content}")
                print("\n💡 TIP: Your API key works, but GPT-4 might be quota-limited.")
                print("   Consider using gpt-3.5-turbo for testing (update OPENAI_MODEL in .env)")
                return True
            else:
                print(f"❌ gpt-3.5-turbo also failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ ERROR: {e}")
            return False


if __name__ == "__main__":
    print("=" * 60)
    print("OpenAI API Test Script")
    print("=" * 60)
    
    success = asyncio.run(test_openai())
    
    if not success:
        # Try GPT-3.5 as fallback
        asyncio.run(test_gpt35_turbo())
    
    print("\n" + "=" * 60)
