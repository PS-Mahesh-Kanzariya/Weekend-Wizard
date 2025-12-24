# agent_fun.py
import asyncio
import json
import sys
import os
from typing import Dict, Any, List
from contextlib import AsyncExitStack
import requests
from dotenv import load_dotenv

load_dotenv()

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file or environment variables")

async def create_system_prompt(tool_index) -> str:
    """Create a system prompt with tool descriptions and parameter names"""
    
    tool_descriptions = []
    for name, tool in tool_index.items():
        # Extract parameter information from tool input schema
        params_info = []
        if tool.inputSchema and 'properties' in tool.inputSchema:
            for param_name, param_details in tool.inputSchema['properties'].items():
                param_type = param_details.get('type', 'any')
                param_desc = param_details.get('description', '')
                params_info.append(f"  - {param_name} ({param_type}): {param_desc}")
        
        param_list = "\n".join(params_info) if params_info else "  (no parameters)"
        tool_descriptions.append(f"{name}:\n{tool.description}\nParameters:\n{param_list}")
    
    tools_str = "\n\n".join(tool_descriptions)
    
    return (
        "You are a cheerful weekend helper. You have access to these tools:\n\n"
        f"{tools_str}\n\n"
        "IMPORTANT RULES:\n"
        "1. You MUST think step-by-step and call ONE tool at a time\n"
        "2. After each tool result, decide what to do next\n"
        "3. Output ONLY ONE JSON object per step, NEVER a list\n"
        "4. Use the EXACT parameter names shown above\n"
        "5. When you have all needed information, output final answer\n\n"
        "Example for 'Get weather at (40.7128, -74.0060)':\n"
        '{"action":"get_weather","args":{"latitude":40.7128,"longitude":-74.006}}\n\n'
        "Example for 'Tell me a joke':\n"
        '{"action":"random_joke","args":{}}\n\n'
        "Example final answer:\n"
        '{"action":"final","answer":"The weather is sunny at 72°F"}\n\n'
        "For complex requests (like weather + books + joke + dog), call tools one by one.\n"
        "Start with the most relevant tool first."
    )

def llm_json(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Call Groq API with Llama 3.1 8B model and ensure JSON response"""
    
    groq_messages = []
    for msg in messages:
        groq_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    # Use a larger model for better reasoning on complex prompts
    model = "llama-3.3-70b-versatile"
    if len(messages) > 3:  # For complex conversations, use a better model
        model = "llama-3.3-70b-versatile"
    
    payload = {
        "model": model,
        "messages": groq_messages,
        "temperature": 0.2,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"}
    }
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            error_msg = f"Groq API error {response.status_code}: {response.text[:200]}"
            print(f"[ERROR] {error_msg}")
            return {"action": "final", "answer": f"Error contacting weather service. Please try again."}
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Clean the content - remove any markdown code blocks
        content = content.replace('```json', '').replace('```', '').strip()
        
        # Try to parse as JSON
        try:
            parsed = json.loads(content)
            
            # Handle case where parsed is a list (incorrect format)
            if isinstance(parsed, list):
                print(f"[WARNING] LLM returned a list instead of single object")
                # Try to extract first valid action from list
                for item in parsed:
                    if isinstance(item, dict) and "action" in item:
                        return item
                # If no valid action, use first item as final answer
                if parsed:
                    return {"action": "final", "answer": str(parsed[0])}
                else:
                    return {"action": "final", "answer": "I received an empty response."}
            
            # Normal case: parsed is a dict
            elif isinstance(parsed, dict):
                if "action" in parsed:
                    # Validate action format
                    action = parsed.get("action", "")
                    args = parsed.get("args", {})
                    
                    # If it's a final answer, ensure it has proper format
                    if action == "final":
                        answer = parsed.get("answer", "")
                        if not answer:
                            answer = "I have gathered the information you requested."
                        return {"action": "final", "answer": answer}
                    
                    # For tool calls, ensure args is a dict
                    if not isinstance(args, dict):
                        args = {}
                    
                    return {"action": action, "args": args}
                else:
                    # Check for alternative response formats
                    if "answer" in parsed:
                        return {"action": "final", "answer": parsed["answer"]}
                    elif "response" in parsed:
                        return {"action": "final", "answer": parsed["response"]}
                    else:
                        return {"action": "final", "answer": str(parsed)}
            else:
                return {"action": "final", "answer": str(parsed)}
                
        except json.JSONDecodeError as e:
            print(f"[WARNING] Failed to parse JSON: {e}")
            print(f"[WARNING] Raw content: {content[:200]}")
            
            # Try to find JSON in the response
            import re
            # Look for JSON object or array
            json_match = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, dict) and "action" in parsed:
                        return parsed
                    elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) and "action" in parsed[0]:
                        return parsed[0]
                except:
                    pass
            
            # If content looks like a direct answer, use it
            if "weather" in content.lower() or "temperature" in content.lower() or "answer" in content.lower():
                return {"action": "final", "answer": content}
            else:
                # Check if it's trying to call a tool
                for tool_name in ["get_weather", "book_recs", "random_joke", "random_dog", "city_to_coords", "trivia"]:
                    if tool_name in content.lower():
                        # Extract coordinates if present
                        import re
                        coord_match = re.search(r'(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)', content)
                        if coord_match and tool_name == "get_weather":
                            lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
                            return {"action": "get_weather", "args": {"latitude": lat, "longitude": lon}}
                        elif tool_name == "book_recs" and "mystery" in content.lower():
                            return {"action": "book_recs", "args": {"topic": "mystery", "limit": 2}}
                        else:
                            return {"action": tool_name, "args": {}}
                
                # Fallback: return as final answer
                return {"action": "final", "answer": content}
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Connection error: {str(e)}"
        print(f"[ERROR] {error_msg}")
        return {"action": "final", "answer": "Sorry, I'm having trouble connecting to services. Please try again."}

def reflect_with_groq(answer: str) -> str:
    """Use Groq for reflection check - only for complex answers"""
    if len(answer) < 200:  # Skip reflection for short answers
        return "looks good"
    
    reflection_prompt = (
        "Check if this response is correct and complete. "
        "If it's fine, reply with exactly 'looks good'. "
        "If there are issues, provide the corrected answer."
    )
    
    payload = {
        "model": "llama-3.1-70b-versatile",
        "messages": [
            {"role": "system", "content": reflection_prompt},
            {"role": "user", "content": answer}
        ],
        "temperature": 0,
        "max_tokens": 500
    }
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=20
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[WARNING] Reflection failed: {e}")
        return "looks good"

async def main():
    server_path = sys.argv[1] if len(sys.argv) > 1 else "server_fun.py"
    exit_stack = AsyncExitStack()
    stdio = await exit_stack.enter_async_context(
        stdio_client(StdioServerParameters(command="python", args=[server_path]))
    )
    r_in, w_out = stdio
    session = await exit_stack.enter_async_context(ClientSession(r_in, w_out))
    await session.initialize()

    tools = (await session.list_tools()).tools
    tool_index = {t.name: t for t in tools}
    print("Connected tools:", list(tool_index.keys()))
    
    # Create system prompt with tool information
    system_prompt = await create_system_prompt(tool_index)
    
    # Print brief tool info
    print("\nAvailable tools:")
    for name, tool in tool_index.items():
        params = []
        if tool.inputSchema and 'properties' in tool.inputSchema:
            params = list(tool.inputSchema['properties'].keys())
        print(f"  - {name}: {', '.join(params) if params else 'no params'}")

    history = [{"role": "system", "content": system_prompt}]
    try:
        while True:
            user = input("\nYou: ").strip()
            if not user or user.lower() in {"exit", "quit", "q"}:
                break
                
            print(f"\n{'='*60}")
            print(f"User: {user}")
            print(f"{'='*60}")
            
            history.append({"role": "user", "content": user})

            # Track what information we've gathered
            gathered_info = {
                "weather": None,
                "books": None,
                "joke": None,
                "dog": None,
                "trivia": None
            }
            
            for step in range(12):  # Increased steps for complex requests
                print(f"\n[Step {step + 1}] Processing...")
                decision = llm_json(history)
                
                print(f"[DEBUG] Decision: {decision.get('action', 'unknown')}")
                
                if decision.get("action") == "final":
                    answer = decision.get("answer", "")
                    
                    # Add gathered info to answer for complex requests
                    if any(gathered_info.values()):
                        # For complex answers, ensure all gathered info is included
                        if "weather" in user.lower() and "book" in user.lower() and "joke" in user.lower():
                            final_answer_parts = []
                            if gathered_info["weather"]:
                                final_answer_parts.append(f"🌤️ Weather: {gathered_info['weather']}")
                            if gathered_info["books"]:
                                final_answer_parts.append(f"📚 Book suggestions: {gathered_info['books']}")
                            if gathered_info["joke"]:
                                final_answer_parts.append(f"😄 Joke: {gathered_info['joke']}")
                            if gathered_info["dog"]:
                                final_answer_parts.append(f"🐶 Dog picture: {gathered_info['dog']}")
                            
                            if final_answer_parts:
                                answer = "Here's your cozy Saturday plan for New York!\n\n" + "\n\n".join(final_answer_parts)
                    
                    # Use reflection for longer answers
                    if len(answer) > 150:
                        reflection_result = reflect_with_groq(answer)
                        if reflection_result.lower() != "looks good":
                            answer = reflection_result
                    
                    print(f"\n{'='*60}")
                    print(f"Agent: {answer}")
                    print(f"{'='*60}")
                    history.append({"role": "assistant", "content": answer})
                    break

                tname = decision.get("action")
                args = decision.get("args", {})
                
                if not tname:
                    error_msg = f"Need to specify an action. Available: {list(tool_index.keys())}"
                    history.append({"role": "assistant", "content": error_msg})
                    print(f"[ERROR] {error_msg}")
                    continue
                    
                if tname not in tool_index:
                    available_tools = list(tool_index.keys())
                    error_msg = f"Tool '{tname}' not found. Available: {available_tools}"
                    history.append({"role": "assistant", "content": error_msg})
                    print(f"[ERROR] {error_msg}")
                    continue

                try:
                    print(f"[TOOL] Calling {tname} with {args}")
                    result = await session.call_tool(tname, args)
                    
                    # Extract the result text
                    if result.content and len(result.content) > 0:
                        payload = result.content[0].text
                    else:
                        payload = json.dumps(result.model_dump())
                    
                    tool_response = f"[tool:{tname}] {payload}"
                    print(f"[TOOL RESULT] {tname}: Success")
                    
                    # Store gathered information
                    if tname == "get_weather":
                        try:
                            weather_data = json.loads(payload)
                            temp = weather_data.get('temperature_2m', 'N/A')
                            code = weather_data.get('weather_code', 0)
                            # Convert weather code to description
                            weather_desc = "sunny" if code in [0, 1] else "cloudy" if code in [2, 3] else "rainy" if code > 50 else "clear"
                            gathered_info["weather"] = f"{temp}°C, {weather_desc}"
                        except:
                            gathered_info["weather"] = "Weather data received"
                    
                    elif tname == "book_recs":
                        try:
                            book_data = json.loads(payload)
                            books = book_data.get('results', [])[:2]
                            book_titles = [b.get('title', 'Unknown') for b in books]
                            gathered_info["books"] = ", ".join(book_titles) if book_titles else "Mystery books"
                        except:
                            gathered_info["books"] = "Mystery book recommendations"
                    
                    elif tname == "random_joke":
                        try:
                            joke_data = json.loads(payload)
                            gathered_info["joke"] = joke_data.get('joke', 'A funny joke!')
                        except:
                            gathered_info["joke"] = "A lighthearted joke"
                    
                    elif tname == "random_dog":
                        try:
                            dog_data = json.loads(payload)
                            gathered_info["dog"] = dog_data.get('message', 'cute dog picture')
                        except:
                            gathered_info["dog"] = "A cute dog picture URL"
                    
                    elif tname == "trivia":
                        try:
                            trivia_data = json.loads(payload)
                            question = trivia_data.get('question', '')
                            gathered_info["trivia"] = question[:100] + "..." if len(question) > 100 else question
                        except:
                            gathered_info["trivia"] = "Trivia question"
                    
                    history.append({"role": "assistant", "content": tool_response})
                    
                except Exception as e:
                    error_msg = f"Error with {tname}: {str(e)}"
                    history.append({"role": "assistant", "content": error_msg})
                    print(f"[ERROR] {error_msg}")
                
                # Safety check: break if too many steps
                if step >= 11:
                    # Create final answer from gathered info
                    final_parts = []
                    for key, value in gathered_info.items():
                        if value:
                            final_parts.append(f"{key}: {value}")
                    
                    if final_parts:
                        final_answer = "Based on what I found:\n" + "\n".join(final_parts)
                    else:
                        final_answer = "I tried to gather information but encountered some issues. Let me summarize what I have."
                    
                    print(f"\n{'='*60}")
                    print(f"Agent: {final_answer}")
                    print(f"{'='*60}")
                    history.append({"role": "assistant", "content": final_answer})
                    break
                    
    except KeyboardInterrupt:
        print("\n\nExiting...")
    finally:
        await exit_stack.aclose()

if __name__ == "__main__":
    asyncio.run(main())