import json
import logging
import PIL.Image
import io

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

class GeminiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        if GEMINI_AVAILABLE:
            genai.configure(api_key=api_key)
        else:
            logging.error("google-generativeai is not installed.")

    def chat(self, model: str, messages: list[dict], temperature: float = 0.2, response_mime_type: str = "application/json") -> str:
        if not GEMINI_AVAILABLE:
            raise RuntimeError("google-generativeai not installed")
        
        system_instruction = ""
        gemini_history = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_instruction += content + "\n"
            elif role == "user":
                gemini_history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_history.append({"role": "model", "parts": [content]})
                
        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system_instruction if system_instruction else None,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                response_mime_type=response_mime_type
            )
        )
        
        chat = gemini_model.start_chat(history=gemini_history[:-1])
        last_msg = gemini_history[-1]["parts"][0]
        
        response = chat.send_message(last_msg)
        return response.text

    def analyze_image(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        if not GEMINI_AVAILABLE:
            raise RuntimeError("google-generativeai not installed")
        
        gemini_model = genai.GenerativeModel(model_name=model)
        
        # Convert bytes to PIL Image
        image = PIL.Image.open(io.BytesIO(image_bytes))
        
        response = gemini_model.generate_content([prompt, image])
        return response.text

    async def analyze_image_async(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        if not GEMINI_AVAILABLE:
            raise RuntimeError("google-generativeai not installed")
        
        gemini_model = genai.GenerativeModel(model_name=model)
        image = PIL.Image.open(io.BytesIO(image_bytes))
        
        response = await gemini_model.generate_content_async([prompt, image])
        return response.text
