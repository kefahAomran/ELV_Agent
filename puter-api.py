from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8741/v1",
    api_key="unused"  # أي نص عشوائي، المفتاح غير مطلوب
)

response = client.chat.completions.create(
    model="llama-3.1-70b",  # يمكنك تغيير النموذج
    messages=[{"role": "user", "content": "مرحباً، كيف الحال؟"}]
)

print(response.choices[0].message.content)