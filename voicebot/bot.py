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
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from openai._types import NOT_GIVEN
from pipecat.frames.frames import TextFrame, AudioRawFrame, Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
import numpy as np

# Cargar variables de entorno
load_dotenv(override=True)

SAMPLE_RATE = 8000  # Twilio Media Streams

# ──────────────────────────────────────────
# FUNCIÓN DEBUG SIMPLE PARA LOGS
# ──────────────────────────────────────────
def log_audio_debug(frame: Frame, stage: str):
    """Log simple para debug de audio"""
    if isinstance(frame, AudioRawFrame):
        if frame.user_audio:
            logger.info(f"🎤 [{stage}] AUDIO INPUT: {len(frame.audio)} bytes, rate: {frame.sample_rate}Hz")
        else:
            try:
                audio_array = np.frombuffer(frame.audio, dtype=np.int16)
                max_amp = np.max(np.abs(audio_array)) if len(audio_array) > 0 else 0
                rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2)) if len(audio_array) > 0 else 0
                logger.info(f"🔊 [{stage}] AUDIO OUTPUT: {len(frame.audio)} bytes, rate: {frame.sample_rate}Hz, max_amp: {max_amp}, rms: {rms:.2f}")
                
                if max_amp < 100:
                    logger.warning(f"⚠️  [{stage}] Audio muy silencioso (max_amp: {max_amp})")
                    
            except Exception as e:
                logger.error(f"❌ [{stage}] Error analizando audio: {e}")
                
    elif isinstance(frame, TextFrame):
        logger.info(f"📝 [{stage}] TEXT: '{frame.text}'")


# ──────────────────────────────────────────
# 1) PIPELINE PARA LLAMADAS DE VOZ (WebSocket)
# ──────────────────────────────────────────
async def _voice_call(ws: WebSocket):
    """Maneja la conexión Media Streams de Twilio - Groq + ElevenLabs."""
    logger.info("🎯 Iniciando pipeline de voz Groq + ElevenLabs...")
    
    try:
        # ───── TWILIO HANDSHAKE (necesario para Media Streams) ─────
        start_iter = ws.iter_text()
        await start_iter.__anext__()  # handshake message
        start_msg = await start_iter.__anext__()  # start message
        start_data = json.loads(start_msg)
        
        stream_sid = start_data["start"]["streamSid"]
        call_sid = start_data["start"]["callSid"]
        
        logger.info(f"📞 CallSid: {call_sid}")
        logger.info(f"📞 StreamSid: {stream_sid}")

        # ───── SERIALIZER CON DATOS DE TWILIO ─────
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        )
        logger.info("✅ Twilio serializer creado")

        # ───── SERVICIOS GROQ + ELEVENLABS ─────
        # Groq Whisper STT (temperatura 0)
        stt = GroqSTTService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="whisper-large-v3",
            language="es",
            temperature=0
        )
        logger.info("✅ Groq Whisper STT creado")
        
        # Groq Llama 70B LLM
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"), 
            model="llama-3.3-70b-versatile"
        )
        logger.info("✅ Groq Llama 70B LLM creado")
        
        # ───── ElevenLabs TTS con configuración básica ─────
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
        voice_id = "ucWwAruuGtBeHfnAaKcJ"
        
        if not elevenlabs_api_key:
            logger.error("❌ ELEVENLABS_API_KEY no configurada")
            raise ValueError("ELEVENLABS_API_KEY requerida")
            
        logger.info(f"🎵 Configurando ElevenLabs con voice_id: {voice_id}")
        
        # Configuración más básica y compatible
        tts = ElevenLabsTTSService(
            api_key=elevenlabs_api_key,
            voice_id=voice_id,
            # Usar configuraciones por defecto más compatibles
            model="eleven_monolingual_v1",  # Modelo más estable
            # No especificar output_format ni sample_rate para usar defaults
        )
        logger.info("✅ ElevenLabs TTS creado con configuración básica")

        # ───── CONTEXTO LLM ─────
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres Lorenzo, un asistente de voz amigable de TDX. "
                    "Responde en español de forma natural y breve. "
                    "Máximo 2 oraciones por respuesta. "
                    "Siempre confirma que escuchaste al usuario."
                )
            }
        ]
        context = OpenAILLMContext(messages, NOT_GIVEN)
        ctx_aggr = llm.create_context_aggregator(context)
        logger.info("✅ Groq context creado")

        # ───── VAD SIMPLE (sin parámetros problemáticos) ─────
        vad = SileroVADAnalyzer(sample_rate=SAMPLE_RATE)
        logger.info("✅ Silero VAD creado")

        # ───── TRANSPORT BÁSICO SIN DEBUG COMPLEJO ─────
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=vad,
                serializer=serializer,
                # Configuraciones de audio para Twilio
                audio_in_sample_rate=SAMPLE_RATE,
                audio_out_sample_rate=SAMPLE_RATE,
                audio_in_channels=1,
                audio_out_channels=1,
            ),
        )
        logger.info("✅ Transport creado")

        # ───── PIPELINE BÁSICO Y FUNCIONAL ─────
        pipeline = Pipeline([
            transport.input(),      # WebSocket Twilio
            stt,                   # Groq Whisper
            ctx_aggr.user(),       # Contexto usuario
            llm,                   # Groq Llama 70B
            tts,                   # ElevenLabs TTS 
            transport.output(),    # De vuelta a Twilio
            ctx_aggr.assistant(),  # Contexto asistente
        ])
        logger.info("✅ Pipeline Groq + ElevenLabs creado")

        # ───── TASK Y RUNNER ─────
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                audio_in_sample_rate=SAMPLE_RATE,
                audio_out_sample_rate=SAMPLE_RATE,
                enable_metrics=True,
                # Configuraciones adicionales para audio
                audio_out_enabled=True,
                audio_in_enabled=True,
            ),
        )
        
        # ───── SALUDO AUTOMÁTICO SIMPLE ─────
        async def send_greeting():
            await asyncio.sleep(3)  # Esperar conexión estable
            logger.info("👋 Enviando saludo...")
            greeting = TextFrame("¡Hola! Soy Lorenzo de TDX. ¿Me escuchas bien?")
            await task.queue_frame(greeting)
            logger.info("✅ Saludo enviado")
            
            # Log para verificar si ElevenLabs funciona
            logger.info("🔍 Verificando que ElevenLabs esté procesando audio...")

        asyncio.create_task(send_greeting())

        # ───── EJECUTAR PIPELINE ─────
        logger.info("🚀 Iniciando pipeline Groq + ElevenLabs...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        logger.info("📞 Llamada Groq + ElevenLabs finalizada")
        
    except Exception as e:
        logger.exception(f"💥 Error en pipeline Groq + ElevenLabs: {e}")
        raise


# ──────────────────────────────────────────
# 2) PIPELINE SMS / WHATSAPP (webhook HTTP) - SIN CAMBIOS
# ──────────────────────────────────────────
async def _sms(request: Request) -> Response:
    """Maneja mensajes SMS/WhatsApp de Twilio - Groq LLM."""
    try:
        form = await request.form()
        user_msg = form.get("Body", "") or "..."
        from_number = form.get("From", "")
        
        logger.info(f"💬 SMS de {from_number}: '{user_msg}'")

        # Usar Groq Llama para respuesta de texto
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile"
        )
        
        # Contexto simple para SMS
        context = OpenAILLMContext([
            {
                "role": "system", 
                "content": "Eres Lorenzo, un asistente amigable de TDX. Responde de forma concisa en español."
            },
            {
                "role": "user",
                "content": user_msg
            }
        ], NOT_GIVEN)
        
        # Generar respuesta
        response = await llm._process_context(context)
        reply = response.choices[0].message.content
        
        logger.info(f"🤖 Respuesta SMS Groq: '{reply}'")

        # TwiML para responder
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.exception(f"💥 Error en SMS Groq: {e}")
        # Respuesta de error en TwiML
        error_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error procesando mensaje</Message></Response>'
        return Response(content=error_twiml, media_type="text/xml")


# ──────────────────────────────────────────
# 3) HEALTH CHECK - SIN CAMBIOS
# ──────────────────────────────────────────
async def health_check():
    """Health check endpoint."""
    logger.info("🏥 Health check Groq + ElevenLabs")
    return {
        "status": "healthy", 
        "service": "TDX Voice Bot - Groq + ElevenLabs",
        "version": "2025-06-22-GROQ-ELEVENLABS-DEBUG",
        "apis": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        },
        "services": {
            "stt": "Groq Whisper (temp=0)",
            "llm": "Groq Llama 3.3 70B", 
            "tts": "ElevenLabs (ucWwAruuGtBeHfnAaKcJ)"
        }
    }


# ──────────────────────────────────────────
# 4) PUNTO ÚNICO DE ENTRADA - SIN CAMBIOS
# ──────────────────────────────────────────
async def bot(ctx):
    """
    Función principal Groq + ElevenLabs.
    Compatible con tu main.py existente.
    """
    if isinstance(ctx, WebSocket):
        logger.info("🗣️ Llamada de voz Twilio → Groq + ElevenLabs Stack")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 Mensaje SMS/WhatsApp → Groq")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")