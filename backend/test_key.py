import requests
from app.core.config import settings

def dump_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.GEMINI_API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if 'models' in data:
            model_names = [m['name'] for m in data['models']]
            with open("models_list.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(model_names))
    except Exception as e:
        print("Failed to parse JSON", e)

if __name__ == "__main__":
    dump_models()
