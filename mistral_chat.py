from openai import OpenAI

# OpenRouter ayarları
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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"
)

def ask_mistral(prompt: str) -> str:
    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct:free",
            #model="google/gemma-3-27b-it:free:online",
            messages=[
                {"role": "system", "content": "Sen bilgili, yardımsever bir Türkçe sohbet botusun."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=256,
            temperature=0.7 

        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Hata: {e}")
        return f"⚠️ Cevap alınamadı. Hata: {e}"
if __name__ == "__main__":
    cevap = ask_mistral("Türkiye'nin başkenti neresidir?")
    print(cevap)
