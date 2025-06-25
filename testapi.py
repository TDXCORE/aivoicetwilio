# test_elevenlabs_api.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_elevenlabs_api():
    """Verifica si la API key de ElevenLabs es válida."""
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    
    if not api_key:
        print("❌ ELEVENLABS_API_KEY no encontrada en variables de entorno")
        return False
    
    print(f"🔑 API Key encontrada: {api_key[:10]}...")
    
    # Test 1: Verificar la validez de la API key
    headers = {
        "Accept": "application/json",
        "xi-api-key": api_key
    }
    
    try:
        print("🧪 Probando conexión con ElevenLabs API...")
        response = requests.get("https://api.elevenlabs.io/v1/user", headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            print("✅ API Key válida!")
            print(f"   Usuario: {user_data.get('email', 'N/A')}")
            print(f"   Caracteres disponibles: {user_data.get('character_count', 'N/A')}")
            print(f"   Límite de caracteres: {user_data.get('character_limit', 'N/A')}")
            return True
        elif response.status_code == 401:
            print("❌ API Key inválida o expirada")
            return False
        else:
            print(f"⚠️ Error inesperado: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"💥 Error conectando con ElevenLabs: {e}")
        return False

def list_available_voices():
    """Lista las voces disponibles en tu cuenta."""
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    headers = {
        "Accept": "application/json",
        "xi-api-key": api_key
    }
    
    try:
        print("\n🎙️ Obteniendo voces disponibles...")
        response = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
        
        if response.status_code == 200:
            voices = response.json()
            all_voices = voices.get('voices', [])
            
            print("✅ Todas las voces disponibles:")
            spanish_voices = []
            
            for voice in all_voices:
                voice_id = voice.get('voice_id')
                name = voice.get('name')
                category = voice.get('category', 'N/A')
                labels = voice.get('labels', {})
                language = labels.get('language', 'N/A')
                accent = labels.get('accent', 'N/A')
                age = labels.get('age', 'N/A')
                gender = labels.get('gender', 'N/A')
                use_case = labels.get('use case', 'N/A')
                
                print(f"   • {name} ({voice_id})")
                print(f"     - Categoría: {category}")
                print(f"     - Idioma: {language}")
                print(f"     - Acento: {accent}")
                print(f"     - Edad: {age}, Género: {gender}")
                print(f"     - Uso: {use_case}")
                print()
                
                # Recopilar voces en español
                if 'spanish' in language.lower() or 'español' in language.lower() or language.lower() == 'es':
                    spanish_voices.append({
                        'name': name,
                        'voice_id': voice_id,
                        'category': category,
                        'language': language,
                        'accent': accent,
                        'gender': gender,
                        'age': age,
                        'use_case': use_case
                    })
            
            # Mostrar voces en español separadamente
            if spanish_voices:
                print("\n🇪🇸 VOCES EN ESPAÑOL DISPONIBLES:")
                print("=" * 50)
                for voice in spanish_voices:
                    print(f"✨ {voice['name']} ({voice['voice_id']})")
                    print(f"   📍 Acento: {voice['accent']}")
                    print(f"   👤 {voice['gender']}, {voice['age']}")
                    print(f"   🎯 Uso recomendado: {voice['use_case']}")
                    print(f"   📂 Categoría: {voice['category']}")
                    print()
                    
                print("💡 RECOMENDACIONES PARA TU BOT:")
                for voice in spanish_voices:
                    if voice['gender'].lower() == 'female' and 'young' in voice['age'].lower():
                        print(f"🌟 IDEAL: {voice['name']} ({voice['voice_id']}) - Perfecta para Laura SDR")
                        
            else:
                print("\n⚠️ No se encontraron voces específicamente en español")
                print("💡 Tip: Algunas voces multilingües pueden funcionar en español")
            
            return all_voices
        else:
            print(f"❌ Error obteniendo voces: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"💥 Error: {e}")
        return []

def list_available_models():
    """Lista los modelos de TTS disponibles."""
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    headers = {
        "Accept": "application/json",
        "xi-api-key": api_key
    }
    
    try:
        print("\n🤖 Obteniendo modelos de TTS disponibles...")
        response = requests.get("https://api.elevenlabs.io/v1/models", headers=headers)
        
        if response.status_code == 200:
            models = response.json()
            print("✅ Modelos disponibles:")
            print("=" * 60)
            
            for model in models:
                model_id = model.get('model_id')
                name = model.get('name', 'N/A')
                description = model.get('description', 'N/A')
                languages = model.get('languages', [])
                max_chars = model.get('max_characters_request_free_user', 'N/A')
                max_chars_sub = model.get('max_characters_request_subscribed_user', 'N/A')
                
                print(f"🎯 {name} ({model_id})")
                print(f"   📝 Descripción: {description}")
                print(f"   🌍 Idiomas soportados: {', '.join([lang.get('language_id', '') for lang in languages])}")
                print(f"   📊 Límite caracteres (free): {max_chars}")
                print(f"   📊 Límite caracteres (suscripción): {max_chars_sub}")
                
                # Marcar modelos recomendados
                if 'turbo' in model_id.lower():
                    print("   ⚡ RECOMENDADO: Modelo rápido para tiempo real")
                elif 'multilingual' in model_id.lower():
                    print("   🌐 MULTILINGÜE: Ideal para español")
                elif model_id == 'eleven_v3':
                    print("   🏆 PREMIUM: Máxima calidad de voz")
                    
                print()
                
            # Mostrar recomendaciones específicas
            print("\n💡 RECOMENDACIONES PARA TU BOT DE VENTAS:")
            print("🥇 eleven_turbo_v2_5: Mejor para llamadas en tiempo real (baja latencia)")
            print("🥈 eleven_multilingual_v2: Excelente para español con buena velocidad")
            print("🥉 eleven_v3: Máxima calidad pero mayor latencia")
            
            return models
        else:
            print(f"❌ Error obteniendo modelos: {response.status_code}")
            print(f"   Respuesta: {response.text}")
            return []
            
    except Exception as e:
        print(f"💥 Error obteniendo modelos: {e}")
        return []

def test_voice_synthesis(voice_id=None, model_id="eleven_turbo_v2_5"):
    """Prueba la síntesis de voz con una voz específica."""
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    
    if not voice_id:
        print("⚠️ No se especificó voice_id para la prueba")
        return False
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    
    data = {
        "text": "Hola, soy Laura de TDX. ¿Cómo está usted hoy?",
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
            "use_speaker_boost": False
        }
    }
    
    try:
        print(f"\n🧪 Probando síntesis de voz...")
        print(f"   🎙️ Voz: {voice_id}")
        print(f"   🤖 Modelo: {model_id}")
        
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            json=data,
            headers=headers
        )
        
        if response.status_code == 200:
            print("✅ Síntesis de voz exitosa!")
            print(f"   📊 Tamaño del audio: {len(response.content)} bytes")
            
            # Guardar archivo de prueba
            with open("test_voice.mp3", "wb") as f:
                f.write(response.content)
            print("   💾 Audio guardado como 'test_voice.mp3'")
            return True
        else:
            print(f"❌ Error en síntesis: {response.status_code}")
            print(f"   Respuesta: {response.text}")
            return False
            
    except Exception as e:
        print(f"💥 Error en prueba de síntesis: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Verificando configuración completa de ElevenLabs...\n")
    
    if test_elevenlabs_api():
        voices = list_available_voices()
        models = list_available_models()
        
        # Encontrar la mejor voz en español para la prueba
        spanish_voices = []
        for voice in voices:
            labels = voice.get('labels', {})
            language = labels.get('language', '').lower()
            if 'spanish' in language or 'español' in language or language == 'es':
                spanish_voices.append(voice)
        
        if spanish_voices:
            print(f"\n🧪 Realizando prueba de síntesis con la primera voz en español...")
            best_voice = spanish_voices[0]
            test_voice_synthesis(
                voice_id=best_voice.get('voice_id'),
                model_id="eleven_turbo_v2_5"
            )
        
        print("\n" + "="*60)
        print("📋 RESUMEN PARA TU BOT:")
        print("="*60)
        
        if spanish_voices:
            print(f"✅ Voces en español encontradas: {len(spanish_voices)}")
            print("🎯 Recomendación principal:")
            for voice in spanish_voices[:3]:  # Mostrar top 3
                labels = voice.get('labels', {})
                print(f"   • {voice.get('name')} ({voice.get('voice_id')})")
                print(f"     Género: {labels.get('gender', 'N/A')}, Edad: {labels.get('age', 'N/A')}")
        else:
            print("⚠️ No se encontraron voces específicamente en español")
            print("💡 Puedes usar voces multilingües como 'Rachel' o 'Bella'")
        
        print("\n🤖 Modelo recomendado para tiempo real: eleven_turbo_v2_5")
        print("🌐 Modelo recomendado para español: eleven_multilingual_v2")
        
        print("\n💻 CONFIGURACIÓN SUGERIDA PARA TU BOT:")
        if spanish_voices:
            best_voice = spanish_voices[0]
            print(f'voice_id="{best_voice.get("voice_id")}"  # {best_voice.get("name")}')
        else:
            print('voice_id="21m00Tcm4TlvDq8ikWAM"  # Rachel (funciona bien en español)')
        print('model="eleven_turbo_v2_5"  # Para baja latencia')
        print('language="es"')
        
    else:
        print("\n📋 Pasos para solucionar:")
        print("1. Verifica que tu API key esté correcta en el archivo .env")
        print("2. Asegúrate de que tu cuenta ElevenLabs esté activa")
        print("3. Verifica que tengas créditos disponibles")
        print("4. Considera generar una nueva API key desde tu dashboard")
        print("5. Si sigues teniendo problemas, usa OpenAI TTS como fallback")