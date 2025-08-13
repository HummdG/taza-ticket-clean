# TazaTicket Flight Agent

A production-ready FastAPI + LangGraph flight search agent with multilingual, multimodal WhatsApp support powered by Travelport API.

## Features

🌍 **Multilingual Support**: Automatically detects and responds in user's language (English, Urdu, Spanish, French, German, Arabic, etc.)

🎤 **Multimodal Interface**: Supports both text and voice messages via WhatsApp

✈️ **Comprehensive Flight Search**:

- One-way and round-trip flights
- Date range searches ("cheapest in September")
- Multi-airport city support (London: LHR, LGW, STN, etc.)
- Carrier-specific filtering
- Baggage information extraction

🧠 **Intelligent Conversation**:

- Persistent conversation memory via DynamoDB
- Context-aware slot filling
- Natural language date parsing
- Query reformulation for cleaner processing

🚀 **Production Ready**:

- Dockerized deployment
- Health checks and monitoring
- Structured logging
- Rate limiting and retries
- Async processing with immediate acknowledgments

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   WhatsApp      │    │   FastAPI        │    │   LangGraph     │
│   (Twilio)      │◄──►│   Webhook        │◄──►│   Agent         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AWS S3        │    │   DynamoDB       │    │   Travelport    │
│   (Audio)       │    │   (Memory)       │    │   API           │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                        ┌──────────────────┐    ┌─────────────────┐
                        │   OpenAI         │    │   IATA          │
                        │   (LLM/STT/TTS)  │    │   Resolver      │
                        └──────────────────┘    └─────────────────┘
```

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd taza-ticket-clean
cp env.example .env
```

### 2. Configure Environment

Edit `.env` with your credentials:

```bash
# Required APIs
OPENAI_API_KEY=sk-your-openai-key
TRAVELPORT_CLIENT_ID=your-travelport-client-id
TRAVELPORT_CLIENT_SECRET=your-travelport-client-secret
TRAVELPORT_USERNAME=your-username
TRAVELPORT_PASSWORD=your-password
TRAVELPORT_ACCESS_GROUP=your-access-group

# Twilio WhatsApp
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# AWS Services
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
S3_BUCKET=tazaticket
DYNAMODB_TABLE_NAME=tazaticket-conversations
```

### 3. Deploy with Docker

```bash
# Build and run
docker-compose up --build

# Or run directly
docker build -t taza-ticket .
docker run -p 8000:8000 --env-file .env taza-ticket
```

### 4. Setup WhatsApp Webhook

Configure your Twilio WhatsApp webhook URL:

```
https://your-domain.com/webhook/whatsapp
```

## Development Setup

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### AWS Infrastructure

#### DynamoDB Table Setup

```bash
aws dynamodb create-table \
    --table-name tazaticket-conversations \
    --attribute-definitions \
        AttributeName=PK,AttributeType=S \
        AttributeName=SK,AttributeType=S \
    --key-schema \
        AttributeName=PK,KeyType=HASH \
        AttributeName=SK,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST
```

#### S3 Bucket Setup

```bash
aws s3 mb s3://tazaticket
aws s3api put-bucket-cors --bucket tazaticket --cors-configuration file://cors-config.json
```

## API Endpoints

| Endpoint            | Method | Description                       |
| ------------------- | ------ | --------------------------------- |
| `/`                 | GET    | Service information               |
| `/healthz`          | GET    | Health check (liveness probe)     |
| `/readiness`        | GET    | Readiness check with dependencies |
| `/webhook/whatsapp` | POST   | WhatsApp message webhook          |

## Usage Examples

### Text Messages (English)

```
User: "Find me a flight from London to Dubai tomorrow"
Bot: "✈️ Flight Details
🛫 Outbound: EK 1 (Emirates)
Route: LHR (London) → DXB (Dubai)
Time: 14:30 - 23:55
💰 Total: $450"
```

### Voice Messages (Urdu)

```
User: [Voice in Urdu] "لاہور سے کراچی کے لیے اگلے ہفتے کی سب سے سستی فلائٹ"
Bot: [Voice response in Urdu with flight options]
```

### Date Range Searches

```
User: "What's the cheapest flight from NYC to London in September?"
Bot: [Returns cheapest option across all September dates]
```

### Multi-Airport Support

```
User: "London to New York"
Bot: [Searches LHR,LGW,STN,LTN,LCY → JFK,LGA,EWR combinations]
```

## Project Structure

```
app/
├── main.py                 # FastAPI application
├── config.py              # Settings and configuration
├── routers/
│   └── webhook.py         # WhatsApp webhook handlers
├── services/
│   ├── openai_io.py       # OpenAI integration (chat, STT, TTS)
│   ├── travelport.py      # Travelport API client
│   ├── twilio_client.py   # Twilio WhatsApp client
│   ├── s3_media.py        # S3 media management
│   ├── date_parse.py      # Natural language date parsing
│   ├── iata_resolver.py   # City to IATA code resolution
│   ├── search_strategy.py # Bulk search strategies
│   └── formatter.py       # Response formatting
├── agents/
│   └── graph.py          # LangGraph agent orchestration
├── integrations/
│   └── dynamodb.py       # DynamoDB conversation storage
├── models/
│   └── schemas.py        # Pydantic models
├── utils/
│   ├── logging.py        # Structured logging
│   └── errors.py         # Custom exceptions
└── payloads/             # Travelport API payloads
    ├── flight_search.py  # Payload builders
    └── airline_codes.py  # Airline mappings
```

## Configuration

### Environment Variables

| Variable         | Description                       | Required |
| ---------------- | --------------------------------- | -------- |
| `OPENAI_API_KEY` | OpenAI API key for LLM/STT/TTS    | ✅       |
| `TRAVELPORT_*`   | Travelport API credentials        | ✅       |
| `TWILIO_*`       | Twilio WhatsApp credentials       | ✅       |
| `AWS_*`          | AWS credentials and configuration | ✅       |
| `APP_TIMEZONE`   | Base timezone for date parsing    | ⚠️       |
| `LOG_LEVEL`      | Logging level (INFO, DEBUG, etc.) | ⚠️       |

### Language Support

The agent automatically detects and responds in these languages:

- English (en)
- Urdu (ur)
- Spanish (es)
- French (fr)
- German (de)
- Arabic (ar)
- Hindi (hi)

### Supported Date Formats

- Relative: "today", "tomorrow", "next Friday"
- Absolute: "24th August", "2025-08-24", "24/08/2025"
- Ranges: "12th-16th August", "March 15-20"
- Monthly: "September 2025", "cheapest in September"

## Monitoring and Logging

### Health Checks

```bash
# Liveness probe
curl http://localhost:8000/healthz

# Readiness probe (checks all dependencies)
curl http://localhost:8000/readiness
```

### Structured Logging

All logs are JSON formatted with contextual information:

```json
{
  "timestamp": "2025-01-13T10:30:00Z",
  "level": "INFO",
  "logger": "app.agents.graph",
  "message": "Agent processing completed",
  "user_id": "whatsapp:+1234567890",
  "message_sid": "SM123456789"
}
```

## Testing

### Unit Tests

```bash
pytest tests/unit/
```

### Integration Tests

```bash
pytest tests/integration/
```

### Manual Testing

Use the WhatsApp Sandbox or send test messages:

```bash
# Test webhook directly
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+1234567890&Body=test message"
```

## Deployment

### Production Deployment

1. **Container Registry**: Push to your registry

```bash
docker build -t your-registry/taza-ticket:latest .
docker push your-registry/taza-ticket:latest
```

2. **Kubernetes**: Use provided manifests

```bash
kubectl apply -f k8s/
```

3. **Cloud Run / ECS**: Deploy container with environment variables

### Scaling Considerations

- **Horizontal**: Multiple instances behind load balancer
- **Rate Limiting**: Built-in retry logic with exponential backoff
- **Memory**: Conversation data stored in DynamoDB, not in-memory
- **Background Tasks**: Uses FastAPI BackgroundTasks for async processing

## Security

- ✅ Webhook signature validation
- ✅ No secrets in logs
- ✅ Non-root container user
- ✅ Input validation with Pydantic
- ✅ AWS IAM role-based access

## Troubleshooting

### Common Issues

1. **Webhook timeouts**: Immediate ack is sent, processing happens async
2. **Travelport errors**: Check credentials and rate limits
3. **Audio processing fails**: Fallback to text responses
4. **Memory issues**: Conversation cleanup after 30 days

### Debug Mode

```bash
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions:

- Create an issue in the repository
- Review the troubleshooting section
- Check the logs for detailed error information
