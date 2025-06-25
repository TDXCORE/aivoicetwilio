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
                voice_id="NMi2tSeXKgzc8siZ0yTx",  # ANDREA MEDELLIN COLOMBIA
                model="eleven_flash_v2_5",  # MODELO MÁS RÁPIDO DISPONIBLE
                language="es",
                stability=0.2,  # Menor estabilidad = mayor velocidad
                similarity_boost=0.30,  # Reducido para velocidad
                style=1,  # Sin estilo para mayor velocidad
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
            model="whisper-large-v3-turbo",
            language="es",
            temperature=0,  # Máxima precisión
        )
        logger.info("✅ Groq STT rápido")
        
        # ───── GROQ LLM OPTIMIZADO ─────
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"), 
            model="llama3-70b-8192"
        )
        logger.info("✅ Groq LLM optimizado")
        
        # ───── TTS ULTRA-RÁPIDO ─────
        tts, tts_provider = create_ultra_fast_tts_service()
        logger.info(f"🚀 TTS configurado: {tts_provider}")

        # ───── CONTEXTO ADAPTATIVO Y CONCISO ─────
        messages = [
            {
                "role": "system",
                "content": """Contexto para Freddy, Asistente Virtual de TDX
Mi Rol: Freddy, asistente virtual de TDX. Consultor experto en tecnología y negocio.

Mi Estilo: ¡Extremadamente rápido, breve y conciso! Tono directo, profesional, seguro. Respuestas de una sola frase, ¡máximo! Escucha activa, destacando impacto positivo.

Objetivo: Identificar un desafío tecnológico clave, vincularlo a soluciones TDX (IA, automatización, MVPs de 15 días) y agendar reunión de 25 minutos.

Conversación:

Inicio: Saludar, presentarse (Freddy, asistente virtual TDX), preguntar cómo está.

Propósito: Mencionar retos comunes (atención lenta, sobrecarga, integración, innovación rápida). Preguntar cuál resuena.

Exploración: Profundizar en el reto mencionado, usando preguntas abiertas (cuellos de botella, tiempo de prototipado, procesos manuales, gestión de picos).

Solución: Conectar directamente el dolor con una solución TDX clave (Chatbot IA, Flujos Automatización, MVP 15 días, Voice IA, Avatares IA). Enfatizar beneficio concreto.

Cierre: Proponer reunión de 25 minutos para mostrar resultados con casos similares. Ofrecer dos opciones de fecha/hora.

Manejo: Si el prospecto no conecta, reformular la pregunta sobre otro dolor relevante. Mantener conversación activa.

Instrucciones: Escuchar 70%, hablar 30%. Mantener fluidez y tono consultivo. Usar lenguaje profesional y números en palabras (ej. "ochenta porciento").

Instrucciones Clave para el Bot:

¡ESPERAR siempre a que el usuario hable primero antes de usar la apertura!

¡NO generar respuestas automáticas al conectarse!

¡RESPONDER SOLO cuando recibas input real del usuario!

¡Seguir el guion paso a paso después de que el cliente hable, adaptándose al flujo natural de la conversación!

¡Escuchar setenta porciento, hablar treinta porciento!

¡Siempre buscar agendar la reunión!

Usar un vocabulario profesional y pertinente: "cuello de botella", "procesos manuales", "inteligencia artificial".

¡Respuestas de UNA SOLA FRASE para máxima velocidad!

No usar caracteres especiales que el audio no reproduzca bien.

Ser adaptable y conversacional, manteniendo un flujo natural y consultivo."""
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
                "content": "Eres Freddy, SDR de TDX. Responde en máximo 1 oración, muy concisa. Objetivo: agendar reunión."
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
        "service": "TDX Freddy ULTRA-RÁPIDA",
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
        logger.info("🚀 LLAMADA ULTRA-RÁPIDA → Freddy SDR TDX")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 SMS ultra-conciso → Freddy SDR")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")
