import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("DeepSeek_API_KEY"))

messages = [{
    "role": "system",
    "content": "انت مساعد هندسي ذكي متخصص في انظمة ELV و Low Current لمشروع بناء سكني في Dubai Hills"
}]

print("ELV Engineer Assistant - اكتب 'exit' لإنهاء المحادثة")
print("-" * 50)

while True:
    user_input = input("أنت: ")
    
    if user_input.lower() == "exit":
        print("وداعًا!")
        break

    messages.append({"role": "user", "content": user_input})
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages
    )

    assistant_reply = response.choices[0].message.content

    messages.append({"role": "assistant", "content": assistant_reply})
    
    print(f"Assistant: {assistant_reply}")
    print("-" * 40)