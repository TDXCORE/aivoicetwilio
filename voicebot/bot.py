# voicebot/bot.py
import os
import asyncio
import json
from typing import Union
from dotenv import load_dotenv
from fastapi import WebSocket, Request, Response
from loguru import logger

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from openai._types import NOT_GIVEN
from pipecat.frames.frames import TextFrame

# Cargar variables de entorno
load_dotenv(override=True)

def create_ultra_fast_tts_service():
    """Crea el servicio TTS ultra-optimizado para velocidad."""
    
    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if elevenlabs_api_key:
        try:
            logger.info("🚀 Configurando ElevenLabs ULTRA-RÁPIDO...")
            tts = ElevenLabsTTSService(
                api_key=elevenlabs_api_key,
                voice_id="qHkrJuifPpn95wK3rm2A",  # ANDREA MEDELLIN COLOMBIA
                model="eleven_flash_v2_5",  # MODELO MÁS RÁPIDO DISPONIBLE
                language="es",
                stability=0.2,  # Menor estabilidad = mayor velocidad
                similarity_boost=0.75,  # Reducido para velocidad
                style=0.2,  # Sin estilo para mayor velocidad
                use_speaker_boost=False,  # Desactivado para velocidad
                output_format="pcm_8000",
                optimize_streaming_latency=4,  # Máxima optimización
            )
            logger.info("✅ ElevenLabs FLASH configurado para máxima velocidad")
            return tts, "ElevenLabs-FLASH"
        except Exception as e:
            logger.warning(f"⚠️ ElevenLabs falló: {e}")
    
    # Fallback ultrarrápido
    if openai_api_key:
        try:
            logger.info("🚀 Configurando OpenAI TTS ultrarrápido...")
            tts = OpenAITTSService(
                api_key=openai_api_key,
                voice="nova",
                model="tts-1",  # Modelo más rápido
                language="es",
            )
            logger.info("✅ OpenAI TTS configurado")
            return tts, "OpenAI-Flash"
        except Exception as e:
            logger.error(f"❌ OpenAI TTS falló: {e}")
    
    raise ValueError("❌ No se pudo configurar TTS")

# ──────────────────────────────────────────
# 1) PIPELINE ULTRA-OPTIMIZADO
# ──────────────────────────────────────────
async def _voice_call(ws: WebSocket):
    """Pipeline optimizado para máxima velocidad y adaptabilidad."""
    logger.info("🚀 PIPELINE ULTRA-RÁPIDO iniciando...")
    
    try:
        # ───── TWILIO HANDSHAKE ─────
        start_iter = ws.iter_text()
        await start_iter.__anext__()
        start_msg = await start_iter.__anext__()
        start_data = json.loads(start_msg)
        
        stream_sid = start_data["start"]["streamSid"]
        call_sid = start_data["start"]["callSid"]
        
        logger.info(f"📞 CallSid: {call_sid}")
        logger.info(f"📞 StreamSid: {stream_sid}")

        # ───── SERIALIZER ─────
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        )
        logger.info("✅ Twilio serializer creado")

        # ───── VAD ULTRA-RÁPIDO ─────
        vad_analyzer = SileroVADAnalyzer(
            sample_rate=8000,
            params=VADParams(
                confidence=0.6,      # Más agresivo
                start_secs=0.1,      # Respuesta inmediata
                stop_secs=0.3,       # Mucho más rápido
                min_volume=0.2       # Más sensible
            )
        )
        logger.info("⚡ VAD ultra-rápido configurado")

        # ───── TRANSPORT OPTIMIZADO ─────
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=vad_analyzer,
                serializer=serializer,
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                audio_in_channels=1,
                audio_out_channels=1,
                audio_out_enabled_timeout=20.0,  # Timeout reducido
            ),
        )
        logger.info("✅ Transport optimizado")

        # ───── GROQ STT RÁPIDO ─────
        stt = GroqSTTService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="whisper-large-v3",
            language="es",
            temperature=0,  # Máxima precisión
        )
        logger.info("✅ Groq STT rápido")
        
        # ───── GROQ LLM OPTIMIZADO ─────
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"), 
            model="llama-3.3-70b-versatile"
        )
        logger.info("✅ Groq LLM optimizado")
        
        # ───── TTS ULTRA-RÁPIDO ─────
        tts, tts_provider = create_ultra_fast_tts_service()
        logger.info(f"🚀 TTS configurado: {tts_provider}")

        # ───── CONTEXTO ADAPTATIVO Y CONCISO ─────
        messages = [
            {
                "role": "system",
                "content": """Guion de Llamada con Soluciones TDX

## *PERSONAJE: Freddy, SDR de TDX*

*PERSONALIDAD Y TONO:*
- *Consultor experto:* Formal-amigable, con la confianza de un par que entiende de tecnología y negocio.
- *Ritmo pausado y natural:* Sin muletillas coloquiales excesivas ni groserías.
- *Escucha activa:* Refleja las ideas del prospecto y conecta con lo que dice.
- *Conciso:* Máximo 2 oraciones por respuesta para mantener la fluidez.
- *Lenguaje orientado al beneficio:* Cada intervención se enfoca en el resultado que el líder obtiene.

*OBJETIVO DE LA LLAMADA:*
1. Descubrir dolores críticos del líder de tecnología.
2. Mapearlos a las soluciones de TDX.
3. Concretar una reunión de exploración de 25 minutos.

---

### *GUION DE LA LLAMADA*

*APERTURA* (usar SOLO después de que el prospecto hable primero - "Hola", "Buenos días", etc.):
"Buen día, le habla Freddy, de TDX. ¿Cómo está?"

(ESPERAR RESPUESTA Y RESPONDER CORTÉSMENTE)

*INTRO:*
"Qué bueno. El motivo de mi llamada es muy puntual: muchos líderes de tecnología nos comentan que sus equipos dedican casi un tercio de su tiempo a tareas repetitivas, en lugar de a innovar. De hecho, encontramos un método para devolverles ese tiempo para lo estratégico."

---

### *DESCUBRIMIENTO*

(usar estas preguntas según el flujo, asintiendo y conectando con la respuesta del prospecto):

- *Si el prospecto menciona desafíos con tareas repetitivas o carga de equipo:* "Eso que menciona es un reto muy frecuente, lo escucho constantemente en líderes de TI. Para entender mejor su caso, ¿dónde se están generando los *cuellos de botella* que más le quitan foco a su equipo hoy?"

- *Si el prospecto habla de lentitud en proyectos o innovación:* "Totalmente de acuerdo, la velocidad para innovar es crucial hoy en día. Pensando en esa agilidad, ¿cuánto tiempo le está tomando a su equipo llevar un nuevo prototipo desde la idea hasta que el usuario final puede interactuar con él?"

- *Si el prospecto menciona problemas de integración o manualidades:* "Claro, tener los sistemas hablando entre sí es la base para escalar sin fricción. A propósito de eso, ¿qué tantos *amarres manuales* tiene que hacer su equipo para que los canales como WhatsApp se entiendan con sus sistemas centrales como el ERP o CRM?"

- *Si el prospecto menciona problemas de atención al cliente o disponibilidad 24/7:* "Entiendo, la atención continua es clave hoy. ¿Cómo manejan actualmente los picos de consultas o la necesidad de soporte fuera del horario de oficina?"

---

### *SOLUCIONES TDX*

(mapear directamente al dolor identificado, conectando con la necesidad):

- *Para cuellos de botella en soporte (general o digital):* "Justo para ese dolor, con nuestro *AI Chatbot Multiagente por web o WhatsApp, logramos que su equipo se libere de hasta el **ochenta por ciento* de esas consultas repetitivas. Así pueden dedicarse a lo que de verdad agrega valor."

- *Para cuellos de botella en soporte telefónico:* "Para esos momentos donde la línea telefónica se congestiona, nuestro *AI Voice para llamadas telefónicas* puede gestionar de forma autónoma gran parte de esas interacciones. Esto significa una resolución más rápida para el cliente y menos carga para su equipo."

- *Para tareas repetitivas (internas o cara a cliente):* "Entiendo, para *quitarse de encima* esas labores, nuestros *Flujos de Automatización* ejecutan esos procesos de forma autónoma. En la práctica, es devolverle horas muy valiosas a su gente para que innoven."

- *Para la velocidad de lanzamiento de MVPs:* "Para acelerar esa salida a producción, empaquetamos la solución en nuestro formato de *MVP en quince días*. Es la forma más rápida de validar sus ideas directamente en el mercado."

- *Para amarres manuales y sistemas desintegrados:* "Precisamente, para eliminar esa fricción, nuestras integraciones nativas con CRM y canales como WhatsApp logran que la información fluya sin reprocesos. Todo conversa de forma automática y natural."

- *Para ofrecer atención visual y personalizada 24/7:* "Si su objetivo es dar una experiencia más inmersiva, nuestros *AI Avatar para llamadas en vivo* pueden interactuar con sus clientes en tiempo real, resolviendo dudas y guiando procesos. Esto libera a su equipo y ofrece atención de alto nivel en todo momento."

- *Para atención al cliente en línea (web):* "Para una interacción más dinámica en su sitio web, nuestro *AI Voice asistente web* puede guiar a los usuarios a través de información compleja o procesos de compra. Esto mejora la experiencia del usuario y reduce la carga de consultas directas a su equipo."

---

### *CIERRE*

"Perfecto, [Nombre del prospecto]. Con base en lo que me comenta sobre [mencionar el dolor principal del prospecto], le propongo algo muy concreto y práctico: tengamos una conversación de *veinticinco minutos* para mostrarle con datos cómo un cliente con un reto similar al suyo logró resultados tangibles. ¿Le queda bien este *jueves a las diez a.m.* o prefiere el *viernes a primera hora*?"

---

### *MANEJO DE SITUACIONES*

- *Si el usuario dice "No" a las preguntas iniciales:* "Entiendo. ¿Y hay algún otro tema de eficiencia operativa o agilidad en proyectos que sea importante para usted en este momento?" o "Comprendo. ¿Quizás el tiempo que invierten en tareas de soporte repetitivas podría ser un área a mejorar?"
- *Si no entiende una transcripción:* "Disculpe, no logré escucharlo bien, ¿podría repetir por favor?"
- *Si hay silencio prolongado:* "Le pregunto esto porque he visto a muchos líderes con desafíos similares. ¿Hay algo que le genere inquietud en este tipo de soluciones?"
- *Nunca quedarse completamente callado,* siempre mantener la conversación activa y consultiva.

---

*INSTRUCCIONES CRÍTICAS:*
- ESPERAR siempre a que el usuario hable primero antes de usar la apertura.
- NO generar respuestas automáticas al conectarse.
- Responder SOLO cuando recibas input real del usuario.
- Seguir el guion paso a paso después de que el cliente hable.
- Escuchar 70%, hablar 30%.
- Siempre buscar agendar la reunión.
- Usar vocabulario formal-colombiano: "cuello de botella", "amarres", "quitarse de encima".
- Respuestas máximo 2 oraciones para mantener fluidez.
- No incluir caracteres especiales en las respuestas ya que se convertirán a audio.
- Ser adaptable y conversacional, mantener el flujo natural"""
            }
        ]
        
        # ───── CONTEXTO ADAPTATIVO ─────
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        logger.info("✅ Contexto adaptativo creado")

        # ───── PIPELINE ULTRA-RÁPIDO ─────
        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])
        logger.info("⚡ Pipeline ultra-rápido creado")

        # ───── TASK OPTIMIZADO ─────
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )
        
        # ───── EVENTOS ─────        
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info(f"🔗 Cliente conectado: {client}")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info(f"👋 Cliente desconectado: {client}")
            await task.cancel()

        # ───── EJECUTAR ULTRA-RÁPIDO ─────
        logger.info(f"🚀🚀 INICIANDO PIPELINE ULTRA-RÁPIDO con {tts_provider}...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        logger.info("📞 Llamada finalizada")
        
    except Exception as e:
        logger.exception(f"💥 Error: {e}")
        raise


# ──────────────────────────────────────────
# 2) SMS OPTIMIZADO
# ──────────────────────────────────────────
async def _sms(request: Request) -> Response:
    """SMS ultra-conciso."""
    try:
        form = await request.form()
        user_msg = form.get("Body", "") or "..."
        from_number = form.get("From", "")
        
        logger.info(f"💬 SMS de {from_number}: '{user_msg}'")

        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile"
        )
        
        context = OpenAILLMContext([
            {
                "role": "system", 
                "content": "Eres Laura, SDR de TDX. Responde en máximo 1 oración, muy concisa. Objetivo: agendar reunión."
            },
            {
                "role": "user",
                "content": user_msg
            }
        ])
        
        response = await llm._process_context(context)
        reply = response.choices[0].message.content
        
        logger.info(f"🤖 SMS conciso: '{reply}'")

        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.exception(f"💥 Error SMS: {e}")
        error_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error</Message></Response>'
        return Response(content=error_twiml, media_type="text/xml")


# ──────────────────────────────────────────
# 3) HEALTH CHECK ULTRA-OPTIMIZADO
# ──────────────────────────────────────────
async def health_check():
    """Health check optimizado."""
    logger.info("🏥 Health check ULTRA-RÁPIDO")
    
    tts_status = "unknown"
    try:
        _, tts_provider = create_ultra_fast_tts_service()
        tts_status = tts_provider
    except Exception as e:
        tts_status = f"error: {str(e)}"
    
    return {
        "status": "healthy", 
        "service": "TDX Laura ULTRA-RÁPIDA",
        "version": "2025-06-25-ULTRA-FAST",
        "location": "Medellín, Colombia",
        "apis": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        },
        "services": {
            "stt": "Groq Whisper Ultra-Fast",
            "llm": "Groq Llama 3.3 (Adaptativo)", 
            "tts": tts_status,
            "voice": "ANDREA MEDELLIN (Flash Mode)",
            "purpose": "Ultra-Fast Adaptive SDR"
        },
        "optimization": {
            "vad_speed": "Ultra-Fast (0.3s stop)",
            "tts_model": "eleven_flash_v2_5",
            "adaptability": "High (responde a feedback)",
            "conciseness": "Máximo 1 oración por defecto"
        }
    }


# ──────────────────────────────────────────
# 4) ENTRADA PRINCIPAL
# ──────────────────────────────────────────
async def bot(ctx):
    """Bot ultra-optimizado y adaptativo."""
    if isinstance(ctx, WebSocket):
        logger.info("🚀 LLAMADA ULTRA-RÁPIDA → Laura SDR TDX")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 SMS ultra-conciso → Laura SDR")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")