from google import genai

# حط الـ API Key بتاعك هنا (بس أوعى تبعته في الشات هنا تاني عشان الأمان 😉)
client = genai.Client(api_key="AIzaSyD5E5tVDJZirGVFG-iAsECH35zlKXYrfio")

print("🔍 بنجيب قائمة الموديلات المتاحة...")

try:
    models = client.models.list()
    for m in models:
        # هنطبع اسم الموديل بس
        print(f"📍 متاح عندك موديل باسم: {m.name}")
        
except Exception as e:
    print(f"حصلت مشكلة: {e}")