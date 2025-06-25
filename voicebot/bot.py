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
from pipecat.services.openai.tts import OpenAITTSService  # Fallback
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from openai._types import NOT_GIVEN
from pipecat.frames.frames import TextFrame

# Cargar variables de entorno
load_dotenv(override=True)

def create_optimized_tts_service():
    """Crea el servicio TTS optimizado con las voces reales de tu cuenta."""
    
    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    # Configuración optimizada basada en tu test
    if elevenlabs_api_key:
        try:
            logger.info("🎙️ Configurando ElevenLabs TTS con ANDREA MEDELLIN COLOMBIA...")
            tts = ElevenLabsTTSService(
                api_key=elevenlabs_api_key,
                voice_id="qHkrJuifPpn95wK3rm2A",  # ANDREA MEDELLIN COLOMBIA - Tu voz real
                model="eleven_turbo_v2_5",  # Modelo óptimo para tiempo real
                language="es",  # Español
                stability=0.6,  # Estabilidad optimizada para conversación
                similarity_boost=0.85,  # Alta similaridad para naturalidad
                style=0.2,  # Ligero estilo para conversación
                use_speaker_boost=True,  # Activado para mayor claridad
                output_format="pcm_8000",  # Formato optimizado para Twilio
                optimize_streaming_latency=4,  # Máxima optimización para llamadas
            )
            logger.info("✅ ElevenLabs TTS configurado con voz colombiana ANDREA")
            return tts, "ElevenLabs-ANDREA"
        except Exception as e:
            logger.warning(f"⚠️ ElevenLabs falló, probando voz alternativa: {e}")
            
            # Fallback a la segunda voz en español (YoungEngineerCo - masculina)
            try:
                logger.info("🎙️ Probando con YoungEngineerCo (voz masculina)...")
                tts = ElevenLabsTTSService(
                    api_key=elevenlabs_api_key,
                    voice_id="ucWwAruuGtBeHfnAaKcJ",  # YoungEngineerCo
                    model="eleven_turbo_v2_5",
                    language="es",
                    stability=0.6,
                    similarity_boost=0.85,
                    style=0.2,
                    use_speaker_boost=True,
                    output_format="pcm_8000",
                    optimize_streaming_latency=4,
                )
                logger.info("✅ ElevenLabs TTS configurado con YoungEngineerCo")
                return tts, "ElevenLabs-YoungEngineerCo"
            except Exception as e2:
                logger.warning(f"⚠️ Segunda voz también falló: {e2}")
    
    # Fallback final a OpenAI TTS
    if openai_api_key:
        try:
            logger.info("🎙️ Configurando OpenAI TTS como fallback...")
            tts = OpenAITTSService(
                api_key=openai_api_key,
                voice="nova",  # Voz femenina clara
                model="tts-1",  # Modelo más rápido
                language="es",
            )
            logger.info("✅ OpenAI TTS configurado como fallback")
            return tts, "OpenAI-Nova"
        except Exception as e:
            logger.error(f"❌ OpenAI TTS también falló: {e}")
    
    raise ValueError("❌ No se pudo configurar ningún servicio TTS")

# ──────────────────────────────────────────
# 1) PIPELINE PARA LLAMADAS DE VOZ (WebSocket)
# ──────────────────────────────────────────
async def _voice_call(ws: WebSocket):
    """Maneja la conexión Media Streams de Twilio - Groq Whisper + Groq LLM + ElevenLabs."""
    logger.info("🎯 Iniciando pipeline de voz optimizado para Colombia...")
    
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

        # ───── VAD OPTIMIZADO PARA ESPAÑOL COLOMBIANO ─────
        vad_analyzer = SileroVADAnalyzer(
            sample_rate=8000,
            params=VADParams(
                confidence=0.4,      # Más sensible para captar acento colombiano
                start_secs=0.2,      # Tiempo suficiente para procesar español
                stop_secs=0.6,       # Pausa natural en conversación colombiana
                min_volume=0.25      # Volumen mínimo optimizado
            )
        )
        logger.info("✅ Silero VAD optimizado para español colombiano")

        # ───── TRANSPORT CON CONFIGURACIÓN OPTIMIZADA ─────
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
                audio_out_enabled_timeout=35.0,  # Timeout extendido
            ),
        )
        logger.info("✅ Transport creado")

        # ───── GROQ WHISPER STT OPTIMIZADO ─────
        stt = GroqSTTService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="whisper-large-v3",
            language="es",  # Español específico
            temperature=0.1,  # Ligera temperatura para naturalidad
        )
        logger.info("✅ Groq Whisper STT optimizado para español")
        
        # ───── GROQ LLM ─────
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"), 
            model="llama-3.3-70b-versatile"
        )
        logger.info("✅ Groq LLM creado")
        
        # ───── TTS OPTIMIZADO CON TUS VOCES REALES ─────
        tts, tts_provider = create_optimized_tts_service()
        logger.info(f"✅ TTS configurado: {tts_provider}")

        # ───── CONTEXTO LLM OPTIMIZADO PARA COLOMBIA ─────
        messages = [
            {
                "role": "system",
                "content": """Eres Laura, SDR (Sales Development Representative) de TDX, empresa colombiana de soluciones de IA conversacional y automatización. Tienes acento de Medellín, Colombia.

PERSONALIDAD Y TONO COLOMBIANO:
- Formal pero cálido, típico paisa profesional
- Usa expresiones colombianas sutiles: "bacano", "chévere" ocasionalmente
- Ritmo natural pausado, característico de Medellín
- Escucha activa: refleja las ideas del prospecto
- Máximo 2 oraciones por respuesta para mantener fluidez
- Tono relajado y con mucha confianza paisa

OBJETIVO DE LA LLAMADA:
1) Descubrir dolores críticos del líder de tecnología
2) Mapearlos a las soluciones de TDX  
3) Concretar reunión de exploración (20-30 min)

GUION A SEGUIR:

APERTURA (usar SOLO después de que el prospecto hable primero):
"¡Muy buen día! Le habla Laura, de TDX acá en Medellín. ¿Cómo está?"

(esperar respuesta)

INTRODUCCION:
"Lo estoy contactando porque estamos ayudando a empresarios y líderes de tecnología a reducir en un treinta por ciento el tiempo que sus equipos dedican a tareas repetitivas y a acelerar la salida de prototipos. ¿Es un tema que está en su radar en este momento?"

DESCUBRIMIENTO (usar estas preguntas según el flujo):
- "Entendiendo ese desafío de las tareas repetitivas, ¿en qué procesos específicos su equipo de TI experimenta hoy más cuellos de botella por tickets o llamadas que les quitan foco?"
- "Pensando en la agilidad, cuando necesitan lanzar un prototipo o MVP, ¿cuánto tiempo les toma hoy realmente sacarlo a producción y llevarlo al usuario final?"
- "Hablando de eficiencia, ¿sus sistemas como CRM, ERP y canales como WhatsApp o voz conversan de forma fluida, o su equipo debe hacer muchos amarres manuales para que funcionen juntos?"

SOLUCIONES TDX (mapear directamente al dolor identificado):
- Para cuellos de botella: "Justamente para liberar esa carga, TDX implementa AI Chatbot Multiagente o AI Voice Assistant; estas soluciones toman el ochenta por ciento de las interacciones repetitivas."
- Para tareas repetitivas: "Para quitarse de encima esas labores que consumen tiempo valioso, utilizamos Flujos de Automatización y nuestro AgentOps Framework, optimizando procesos end-to-end."
- Para agilidad: "Si el desafío es la agilidad, con MVP en quince días y nuestra oferta de SaaS Agentic, podemos acelerar significativamente la puesta en marcha de sus innovaciones."
- Para integración: "Si la fricción está en la integración, nuestra Integración con CRM/ERP y el AI Assistant para WhatsApp permiten una conectividad perfecta."

CIERRE:
"Dado que identificamos [mencionar el dolor principal], propongo una sesión de descubrimiento de veinticinco minutos. Allí podemos revisar a detalle sus flujos y le muestro un caso real de TDX, similar al suyo, donde logramos resultados bien chéveres. ¿Le cuadra este jueves a las diez de la mañana o prefiere el viernes?"

MANEJO DE SITUACIONES:
- Si dice "No": hacer preguntas exploratorias alternativas
- Si no entiendes: "No logré escucharlo bien, ¿me puede repetir por favor?"
- Si hay silencio: hacer pregunta abierta para reactivar
- Siempre mantener la conversación activa

INSTRUCCIONES CRÍTICAS:
- ESPERAR siempre a que el usuario hable primero antes de usar la apertura
- NO generar respuestas automáticas al conectarse
- Responder SOLO cuando recibas input real del usuario
- Seguir el guion paso a paso después de que el cliente hable
- Escuchar 70%, hablar 30%
- Siempre buscar agendar la reunión
- Usar vocabulario colombiano profesional: "cuello de botella", "amarres", "quitarse de encima", "chévere", "bacano"
- Respuestas máximo 2 oraciones para mantener fluidez
- No incluir caracteres especiales en las respuestas
- Ser adaptable y conversacional, mantener el flujo natural paisa"""
            }
        ]
        
        # ───── CONTEXTO SIN MENSAJE INICIAL ─────
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        logger.info("✅ Contexto colombiano B2B creado")

        # ───── PIPELINE ─────
        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])
        logger.info("✅ Pipeline creado")

        # ───── TASK ─────
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
        
        # ───── EVENTOS DE TRANSPORTE ─────        
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info(f"🔗 Cliente conectado: {client}")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info(f"👋 Cliente desconectado: {client}")
            await task.cancel()

        # ───── EVENTOS DE DEBUGGING ─────
        @transport.event_handler("on_audio_stream_started")
        async def on_audio_stream_started(transport):
            logger.info("🎵 Audio stream iniciado")

        @transport.event_handler("on_audio_stream_stopped") 
        async def on_audio_stream_stopped(transport):
            logger.info("🔇 Audio stream detenido")

        @tts.event_handler("on_tts_started")
        async def on_tts_started(tts, text):
            logger.info(f"🔊 TTS ANDREA iniciado: '{text[:50]}...'")

        @tts.event_handler("on_tts_stopped")
        async def on_tts_stopped(tts):
            logger.info("🔇 TTS ANDREA finalizado")

        # ───── EJECUTAR RUNNER ─────
        logger.info(f"🚀 Iniciando pipeline con {tts_provider}...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        logger.info("📞 Llamada finalizada")
        
    except Exception as e:
        logger.exception(f"💥 Error en pipeline: {e}")
        raise


# ──────────────────────────────────────────
# 2) PIPELINE SMS / WHATSAPP (webhook HTTP)
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
        
        # Contexto colombiano para SMS
        context = OpenAILLMContext([
            {
                "role": "system", 
                "content": "Eres Laura, SDR de TDX en Medellín, Colombia. Responde de forma concisa y profesional pero cálida, con toque paisa. Enfócate en agendar una reunión para mostrar nuestras soluciones de IA conversacional."
            },
            {
                "role": "user",
                "content": user_msg
            }
        ])
        
        # Generar respuesta
        response = await llm._process_context(context)
        reply = response.choices[0].message.content
        
        logger.info(f"🤖 Respuesta SMS: '{reply}'")

        # TwiML para responder
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.exception(f"💥 Error en SMS: {e}")
        error_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error procesando mensaje</Message></Response>'
        return Response(content=error_twiml, media_type="text/xml")


# ──────────────────────────────────────────
# 3) HEALTH CHECK MEJORADO
# ──────────────────────────────────────────
async def health_check():
    """Health check endpoint con información detallada."""
    logger.info("🏥 Health check Pipeline TDX Medellín")
    
    # Verificar TTS disponible
    tts_status = "unknown"
    try:
        _, tts_provider = create_optimized_tts_service()
        tts_status = tts_provider
    except Exception as e:
        tts_status = f"error: {str(e)}"
    
    return {
        "status": "healthy", 
        "service": "TDX Sales Bot Laura - Medellín, Colombia",
        "version": "2025-06-25-ANDREA-MEDELLIN",
        "location": "Medellín, Antioquia, Colombia",
        "apis": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        },
        "services": {
            "stt": "Groq Whisper Large V3 (Español)",
            "llm": "Groq Llama 3.3 70B (Contexto Colombiano)", 
            "tts": tts_status,
            "voice": "ANDREA MEDELLIN COLOMBIA",
            "purpose": "Sales Development Representative (SDR) - TDX"
        },
        "optimization": {
            "target_market": "Colombia",
            "language": "Español Colombiano",
            "accent": "Paisa (Medellín)",
            "latency": "Optimizado para tiempo real"
        }
    }


# ──────────────────────────────────────────
# 4) PUNTO ÚNICO DE ENTRADA
# ──────────────────────────────────────────
async def bot(ctx):
    """
    Función principal para Sales Bot TDX Laura.
    Optimizado para mercado colombiano.
    """
    if isinstance(ctx, WebSocket):
        logger.info("📞 Llamada de ventas → Laura SDR TDX Medellín")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 Mensaje SMS/WhatsApp → Laura SDR")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")