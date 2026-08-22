from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8741/v1",
    api_key="unused"
)

response = client.chat.completions.create(
    model="qwen2.5-7b-instruct",
    messages=[{"role": "user", "content": "ما هو الطقس في دبي؟"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "الحصول على حالة الطقس",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "اسم المدينة"}
                },
                "required": ["city"]
            }
        }
    }],
    tool_choice="auto"
)

print(response.choices[0].message)