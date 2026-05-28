# 🔧 Home Fix Agent

An agentic system that takes a photo of a broken home item, identifies the problem, finds replacement products, and helps you order them — through an interactive conversation.

## Quick Start

```bash
pip install -e ".[dev]"
export OPENAI_API_KEY=your-key-here

# Web UI (recommended)
python -m src.main web
# Open http://localhost:8000

# CLI
python -m src.main analyze path/to/photo.jpg -d "kitchen light burned out"
python -m src.main history
python -m src.main replay <session_id>
```

## How It Works

1. **Upload a photo** of a broken/missing item
2. **Vision Analyst** identifies the item and problem
3. **Spec Extractor** determines replacement specs (bulb type, wattage, etc.)
4. **Clarification** — if specs are uncertain, the system asks you questions and **blocks until you answer**
5. **Product Searcher** finds matching products online
6. **Product Ranker** scores and ranks results
7. **You refine** — send follow-up messages like "I need dimmable" to re-search
8. **You choose** a product and confirm the order

## Interactive Features

- **Blocking clarification**: when the system isn't sure about a spec (e.g., "Is this bulb on a dimmer?"), it pauses and waits for your answer before searching
- **Refinement loop**: after seeing products, type feedback to adjust results without re-uploading
- **Chat UI**: the web interface presents the entire flow as a conversation with a session sidebar
- **Session history**: past sessions are saved with full conversation transcripts and can be replayed

## Testing

No API keys needed for unit tests — they use mocks.

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v
```

The system uses mock product data when no `SERPAPI_KEY` is set. You still need an `OPENAI_API_KEY` for photo analysis.

## Local Deployment

```bash
# Run directly
python -m src.main web

# Or with Docker
docker build -t home-fix-agent .
docker run -p 8000:8000 -e OPENAI_API_KEY=your-key home-fix-agent
```

## Deploy to Fly.io

```bash
# Install flyctl: https://fly.io/docs/flyctl/install/
fly auth login

# First deploy
fly launch  # uses existing fly.toml

# Set secrets
fly secrets set OPENAI_API_KEY=your-key
fly secrets set SERPAPI_KEY=your-key  # optional

# Deploy updates
fly deploy

# Check logs
fly logs
```

The app listens on the `PORT` environment variable (Fly.io sets this automatically).

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key (needs vision model access) |
| `LLM_BASE_URL` | No | Custom LLM endpoint (default: OpenAI) |
| `LLM_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `SERPAPI_KEY` | No | SerpAPI key for real product search (uses mock/LLM fallback if unset) |
| `PORT` | No | Server port (default: `8000`) |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `POST` | `/analyze` | Upload photo + description, start session |
| `POST` | `/chat` | Send message to session (clarification or refinement) |
| `POST` | `/order` | Place order for selected product |
| `GET` | `/session/{id}` | Get full session state |
| `GET` | `/history` | List past sessions |

## Project Structure

```
src/
  main.py           # CLI entry point
  pipeline.py       # Incremental pipeline engine (start_session, advance)
  web.py            # FastAPI server
  agents/           # Vision analyst, spec extractor, product searcher, ranker, order manager
  models/schemas.py # Pydantic models (Session, PipelineStage, ChatMessage, PipelineResult, etc.)
  storage/store.py  # JSON file persistence
  utils/            # LLM client, config loader
static/index.html   # Chat-driven web UI
configs/            # Category definitions, ranking weights
data/sessions/      # Per-session storage (photos + JSON)
```
