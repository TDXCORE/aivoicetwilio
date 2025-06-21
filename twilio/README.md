# Twilio Voice Bot Starter

A telephone-based conversational agent built with Pipecat that connects to Twilio for voice calls.

## Features

- Telephone voice conversations powered by:
  - Deepgram (STT)
  - OpenAI (LLM)
  - Cartesia (TTS)
- Voice activity detection with Silero
- FastAPI WebSocket connection with Twilio
- 8kHz audio sampling optimized for telephone calls

## Required API Keys

- `OPENAI_API_KEY`
- `DEEPGRAM_API_KEY`
- `CARTESIA_API_KEY`
- Twilio account with Media Streams configured

## Quick Customization

### Change Bot Personality

Modify the system prompt in `bot.py`:

```python
messages = [
    {
        "role": "system",
        "content": "You are Chatbot, a friendly, helpful robot..."
    },
]
```

### Change Voice

Update the voice ID in the TTS service:

```python
tts = CartesiaTTSService(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22", # Change this
)
```

### Adjust Audio Parameters

The pipeline is configured for telephone-quality audio (8kHz). If your Twilio configuration uses different parameters, adjust these values:

```python
task = PipelineTask(
    pipeline,
    params=PipelineParams(
        audio_in_sample_rate=8000,  # Input sample rate
        audio_out_sample_rate=8000, # Output sample rate
        # Other parameters...
    ),
)
```

## Twilio Setup

To connect this agent to Twilio:

1. [Purchase a number from Twilio](https://help.twilio.com/articles/223135247-How-to-Search-for-and-Buy-a-Twilio-Phone-Number-from-Console), if you haven't already

2. Collect your Pipecat Cloud organization name:

```bash
pcc organizations list
```

You'll use this information in the next step.

3. Create a [TwiML Bin](https://help.twilio.com/articles/360043489573-Getting-started-with-TwiML-Bins):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://api.pipecat.daily.co/ws/twilio">
      <Parameter name="_pipecatCloudServiceHost" value="AGENT_NAME.ORGANIZATION_NAME"/>
    </Stream>
  </Connect>
</Response>
```

where:

- AGENT_NAME is your agent's name (the name you used when deploying)
- ORGANIZATION_NAME is the value returned in the previous step

4. Assign the TwiML Bin to your phone number:

- Select your number from the Twilio dashboard
- In the `Configure` tab, set `A call comes in` to `TwiML Bin`
- Set `TwiML Bin` to the Bin you created in the previous step
- Save your configuration

## Deployment

### Deploying on Render

1. **Create a Render Account**: If you don't have one, [sign up for Render](https://dashboard.render.com/).

2. **Create a New Web Service**:
   - Go to the [Render dashboard](https://dashboard.render.com/).
   - Click on `New` and select `Web Service`.
   - Connect your GitHub repository (`https://github.com/TDXCORE/aivoicetwilio.git`).

3. **Configure the Web Service**:
   - **Name**: Enter a name for your service.
   - **Branch**: Select the branch you want to deploy (e.g., `main`).
   - **Region**: Choose the region closest to your users.
   - **Instance Type**: Select the instance type (e.g., Free).
   - **Environment Variables**: Add the following environment variables:
     - `TWILIO_ACCOUNT_SID`: Your Twilio Account SID.
     - `TWILIO_AUTH_TOKEN`: Your Twilio Auth Token.
     - `TWILIO_PHONE_NUMBER`: Your Twilio phone number.
     - `DESTINATION_PHONE_NUMBER`: The destination phone number for calls.
     - `OPENAI_API_KEY`: Your OpenAI API key.
     - `DEEPGRAM_API_KEY`: Your Deepgram API key.
     - `CARTESIA_API_KEY`: Your Cartesia API key.

4. **Start the Service**:
   - Click `Create Web Service` to deploy your application.

5. **Verify Deployment**:
   - Once the deployment is complete, verify that your application is running by accessing the provided URL.

### Additional Configuration

- **Twilio Setup**: Ensure your Twilio account is configured as described in the [Twilio Setup](#twilio-setup) section.

- **Customization**: Customize your bot as described in the [Quick Customization](#quick-customization) section.

<final_file_content path="twilio/README.md">
# Twilio Voice Bot Starter

A telephone-based conversational agent built with Pipecat that connects to Twilio for voice calls.

## Features

- Telephone voice conversations powered by:
  - Deepgram (STT)
  - OpenAI (LLM)
  - Cartesia (TTS)
- Voice activity detection with Silero
- FastAPI WebSocket connection with Twilio
- 8kHz audio sampling optimized for telephone calls

## Required API Keys

- `OPENAI_API_KEY`
- `DEEPGRAM_API_KEY`
- `CARTESIA_API_KEY`
- Twilio account with Media Streams configured

## Quick Customization

### Change Bot Personality

Modify the system prompt in `bot.py`:

```python
messages = [
    {
        "role": "system",
        "content": "You are Chatbot, a friendly, helpful robot..."
    },
]
```

### Change Voice

Update the voice ID in the TTS service:

```python
tts = CartesiaTTSService(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22", # Change this
)
```

### Adjust Audio Parameters

The pipeline is configured for telephone-quality audio (8kHz). If your Twilio configuration uses different parameters, adjust these values:

```python
task = PipelineTask(
    pipeline,
    params=PipelineParams(
        audio_in_sample_rate=8000,  # Input sample rate
        audio_out_sample_rate=8000, # Output sample rate
        # Other parameters...
    ),
)
```

## Twilio Setup

To connect this agent to Twilio:

1. [Purchase a number from Twilio](https://help.twilio.com/articles/223135247-How-to-Search-for-and-Buy-a-Twilio-Phone-Number-from-Console), if you haven't already

2. Collect your Pipecat Cloud organization name:

```bash
pcc organizations list
```

You'll use this information in the next step.

3. Create a [TwiML Bin](https://help.twilio.com/articles/360043489573-Getting-started-with-TwiML-Bins):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://api.pipecat.daily.co/ws/twilio">
      <Parameter name="_pipecatCloudServiceHost" value="AGENT_NAME.ORGANIZATION_NAME"/>
    </Stream>
  </Connect>
</Response>
```

where:

- AGENT_NAME is your agent's name (the name you used when deploying)
- ORGANIZATION_NAME is the value returned in the previous step

4. Assign the TwiML Bin to your phone number:

- Select your number from the Twilio dashboard
- In the `Configure` tab, set `A call comes in` to `TwiML Bin`
- Set `TwiML Bin` to the Bin you created in the previous step
- Save your configuration

## Deployment

### Deploying on Render

1. **Create a Render Account**: If you don't have one, [sign up for Render](https://dashboard.render.com/).

2. **Create a New Web Service**:
   - Go to the [Render dashboard](https://dashboard.render.com/).
   - Click on `New` and select `Web Service`.
   - Connect your GitHub repository (`https://github.com/TDXCORE/aivoicetwilio.git`).

3. **Configure the Web Service**:
   - **Name**: Enter a name for your service.
   - **Branch**: Select the branch you want to deploy (e.g., `main`).
   - **Region**: Choose the region closest to your users.
   - **Instance Type**: Select the instance type (e.g., Free).
   - **Environment Variables**: Add the following environment variables:
     - `OPENAI_API_KEY`
     - `DEEPGRAM_API_KEY`
     - `CARTESIA_API_KEY`
     - `TWILIO_ACCOUNT_SID`
     - `TWILIO_AUTH_TOKEN`
     - `TWILIO_PHONE_NUMBER`

4. **Start the Service**:
   - Click `Create Web Service` to deploy your application.

5. **Verify Deployment**:
   - Once the deployment is complete, verify that your application is running by accessing the provided URL.

### Additional Configuration

- **Twilio Setup**: Ensure your Twilio account is configured as described in the [Twilio Setup](#twilio-setup) section.

- **Customization**: Customize your bot as described in the [Quick Customization](#quick-customization) section.
</final_file_content>

IMPORTANT: For any future changes to this file, use the final_file_content shown above as your reference. This content reflects the current state of the file, including any auto-formatting (e.g., if you used single quotes but the formatter converted them to double quotes). Always base your SEARCH/REPLACE operations on this final version to ensure accuracy.


<environment_details>
# VSCode Visible Files
twilio/Dockerfile

# VSCode Open Tabs
.gitignore
twilio/Dockerfile

# Recently Modified Files
These files have been modified since you last accessed them (file was just edited so you may need to re-read it before editing):
twilio/Dockerfile
twilio/README.md

# Current Time
6/21/2025, 2:36:25 PM (America/Bogota, UTC-5:00)

# Context Window Usage
13,500 / 32.768K tokens used (41%)

# Current Mode
ACT MODE
