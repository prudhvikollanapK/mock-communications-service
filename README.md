# Mock Communications Service

An asynchronous REST and WebSocket API that simulates a calling platform. Clients can initiate calls, receive real-time state updates, retrieve call details and inspect metrics.

Redis manages live call state, rate limiting and event broadcasting. PostgreSQL stores call records. A Celery worker simulates call progression and creates mock recording files in the background. Docker Compose runs the API, worker, Redis and PostgreSQL.

## Features

| Requirement | Implementation |
|---|---|
| REST API | FastAPI |
| Create calls | `POST /calls` |
| Retrieve call status | `GET /calls/{id}` |
| Real-time updates | WebSocket |
| Live state and event broadcasting | Redis |
| Persistent storage | PostgreSQL |
| Background processing | Celery |
| Concurrent-call limit | Redis atomic Lua script |
| Calls-per-second (CPS) limit | Redis atomic Lua script |
| Recording uploads | Asynchronous mock storage |
| Basic metrics | `GET /metrics` |
| Prometheus-style metrics | `GET /metrics/prometheus` |
| Containerization | Docker Compose |
| Database schema | `migrations/001_initial.sql` |
| Basic tests | Pytest |

## Requirements

- Docker Desktop or Docker Engine with Docker Compose
- `curl` or Postman for API testing (optional)

## Run the project

1. Download and extract the ZIP.
2. Open the `mock-communications-service` folder in VS Code or a terminal.
3. Make sure Docker is running.
4. Start all services:

   ```bash
   docker compose up --build
   ```

The API will be available at `http://localhost:8000`.

- Interactive API documentation: <http://localhost:8000/docs>
- OpenAPI schema: <http://localhost:8000/openapi.json>
- Health check: <http://localhost:8000/health>

To stop the services, press `Ctrl+C` and run :

```bash
docker compose down
```

To stop services and delete the database volume too, run `docker compose down -v`. This permanently deletes local database data.

## Authentication

REST endpoints other than `/health` require a Bearer API key :

```http
Authorization: Bearer dev-key
```

`dev-key` is for local development only. Configure your own key using `API_KEYS` before using the service outside a local assessment environment. Do not commit production secrets to source control.

Example environment settings :

```env
API_KEYS=long-key
CONCURRENT_CALL_LIMIT=3
CPS_LIMIT=2
```

The WebSocket endpoint accepts the key in the `api_key` query parameter for browser compatibility. Query-string credentials can appear in logs. For production, use short-lived WebSocket tickets or another secure authentication mechanism.

## Create a call

Endpoint :

```http
POST /calls
```

Headers :

```http
Authorization: Bearer dev-key
Content-Type: application/json
```

Request body :

```json
{
  "from": "+15550000001",
  "to": "+15550000002",
  "metadata": {
    "source": "assessment"
  }
}
```

Example with `curl` :

```bash
curl -X POST http://localhost:8000/calls \
  -H 'Authorization: Bearer dev-key' \
  -H 'Content-Type: application/json' \
  -d '{"from":"+15550000001","to":"+15550000002","metadata":{"team":"support"}}'
```

The API returns HTTP `202 Accepted` with a response similar to :

```json
{
  "call_id": "generated-call-uuid",
  "state": "QUEUED",
  "websocket_url": "/ws/calls/generated-call-uuid"
}
```

Use the actual `call_id` returned by your request. The worker progresses the call through:

```text
QUEUED -> RINGING -> ANSWERED -> COMPLETED
                    or
QUEUED -> RINGING -> UNANSWERED -> COMPLETED
```

The answer outcome is randomized. Once the call reaches `COMPLETED`, a background task creates a mock recording file and saves its URL on the call record. This is a placeholder file for the assessment, not a real audio recording.

## Retrieve a call

Endpoint :

```http
GET /calls/{id}
```

Example :

```bash
curl http://localhost:8000/calls/CALL_ID \
  -H 'Authorization: Bearer dev-key'
```

Replace `CALL_ID` with the actual call ID. The response includes the current state, caller and callee details, optional metadata and the recording URL when available. A call belonging to another API key is not returned.

## WebSocket updates

Connect using the call ID and API key :

```javascript
const socket = new WebSocket(
  "ws://localhost:8000/ws/calls/CALL_ID?api_key=dev-key"
);

socket.onmessage = (event) => {
  console.log(JSON.parse(event.data));
};

socket.onopen = () => console.log("Connected to call updates");
socket.onerror = (event) => console.error("WebSocket error", event);
```

Replace `CALL_ID` with the ID returned by `POST /calls`. The server sends the current state and then broadcasts state-transition events published through Redis.

## Metrics

### JSON metrics

Endpoint: `GET /metrics`

```bash
curl http://localhost:8000/metrics \
  -H 'Authorization: Bearer dev-key'
```

The response includes :

- `total` : total calls stored for the authenticated API key
- `active` : calls currently registered as active in Redis
- `cps` : recent call-start entries in the one-second rate-limit window
- `uploads` : calls with a recording URL

### Prometheus-style metrics

Endpoint: `GET /metrics/prometheus`

```bash
curl http://localhost:8000/metrics/prometheus \
  -H 'Authorization: Bearer dev-key'
```

Returns plain-text metrics for total calls, active calls and recording uploads.

## Rate limits

Defaults :

- Maximum concurrent calls per API key: `3`
- Maximum new calls per second per API key: `2`

Configure these defaults with `CONCURRENT_CALL_LIMIT` and `CPS_LIMIT`. Redis Lua scripts perform admission checks atomically across API workers.

If a limit is exceeded, the API returns HTTP `429 Too Many Requests` with a message indicating whether the concurrent-call or calls-per-second limit was reached.

Per-key overrides can be stored in the `api_key_configs` table. Its `api_key_hash` field contains the SHA-256 hash of the API key. This project does not provide a public endpoint to manage these overrides; configure them directly in the database.

## Project structure

```text
mock-communications-service/
├── app/
│   ├── main.py             # FastAPI endpoints and WebSocket handler
│   ├── config.py           # Environment-based configuration
│   ├── database.py         # SQLAlchemy engine and sessions
│   ├── models.py           # Database models
│   ├── schemas.py          # Request and response schemas
│   ├── redis_client.py     # Redis client and rate-limit script
│   ├── security.py         # Bearer API-key validation
│   └── tasks.py            # Celery call and recording tasks
├── migrations/
│   └── 001_initial.sql     # Initial database schema
├── tests/
│   └── test_schemas.py     # Basic schema test
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Run tests

Create and activate a virtual environment :

```bash
python -m venv .venv
```

Windows PowerShell :

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux :

```bash
source .venv/bin/activate
```

Install dependencies and run the tests:

```bash
pip install -r requirements.txt
pytest
```

The included tests cover basic request-schema validation. Use Docker Compose to test the API, Redis, PostgreSQL, Celery worker and WebSocket flow together.

## Design notes and limitations

- Redis stores live call state and publishes state-transition events.
- PostgreSQL is the durable store for call records.
- Celery processes call progression and recording work outside the HTTP request.
- A shared Docker volume acts as a local mock recording bucket. Replace it with S3 or compatible object storage for a real deployment.
- Database tables are created by the application at startup. The SQL file documents the schema but is not an automated migration runner.
