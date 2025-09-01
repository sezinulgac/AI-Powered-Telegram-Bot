import requests

MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"
def translate_text(text, source_lang="en", target_lang="tr"):
    if not text:
        return ""  
    params = {
        "q": text,
        "langpair": f"{source_lang}|{target_lang}"
    }
    try:
        response = requests.get(MYMEMORY_API_URL, params=params)
        data = response.json()
        return data.get("responseData", {}).get("translatedText", "Çeviri alınamadı!")
    except Exception as e:
        return f"Çeviri hatası: {e}"

