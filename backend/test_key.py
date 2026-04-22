import os
import json
import urllib.request

def dump_models():
    url = "https://api.openai.com/v1/models"
    
    # Read .env file directly if os.environ doesn't have it
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.strip().split("=", 1)[1]
                    break

    if not api_key:
        print("OPENAI_API_KEY not found.")
        return

    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if 'data' in data:
                model_names = [m['id'] for m in data['data']]
                with open("test_key_output.txt", "w", encoding="utf-8") as f:
                    f.write("\n".join(sorted(model_names)))
                print(f"Successfully wrote {len(model_names)} models to test_key_output.txt")
            else:
                print("Failed to find models in response:", data)
    except Exception as e:
        print("Failed to fetch models:", e)

if __name__ == "__main__":
    dump_models()

