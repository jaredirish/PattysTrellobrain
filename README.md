# Patty's Knowledge Brain

**Stop drowning in 300+ Trello boards. Search everything. Instantly.**

A "Lazy RAG" tool that syncs your entire Trello workspace to a local database and lets you search across *all* of it using natural language. No vector embeddings. No complex infrastructure. Just Gemini's massive context window doing the heavy lifting.

---

## The Problem

You've got years of marketing frameworks, client prompts, email sequences, and strategies scattered across hundreds of Trello boards. Finding that one webinar prompt you wrote 6 months ago? Good luck.

## The Solution

Sync once. Search forever.

```
"Find Veronica's webinar prompt"
"What email sequences do I have for product launches?"
"Apply my sales funnel framework to [Client Name]"
```

All answered in seconds. No Trello connection needed after the initial sync.

---

## Features

### Core (MVP)
- **One-Click Trello Sync** - Pulls ALL boards, lists, and cards into a local SQLite database
- **Offline Search** - Once synced, search works without internet
- **Natural Language Queries** - Ask questions like you're talking to an assistant
- **Persistent Storage** - Your data survives restarts, no re-syncing needed

### Power Features
- **Client Profiles** - Add clients and get customized outputs ("Apply this framework to Karen's business")
- **Cast Magic Integration** - Import podcast/video transcripts into your knowledge base
- **Copy-Ready Output** - Section-by-section copy buttons for immediate use
- **Smart Rate Limiting** - Never hits Trello's API limits (80 req/10s buffer)
- **API Validation** - Three-state indicators show exactly what's configured

---

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the App
```bash
streamlit run app.py
```

### 3. Add Your API Keys

| Service | Where to Get It | Required? |
|---------|-----------------|-----------|
| **Gemini** | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) | Yes |
| **Trello** | [trello.com/power-ups/admin](https://trello.com/power-ups/admin) | Yes |
| **Cast Magic** | Email justin@castmagic.io | Optional |

### 4. Sync Your Trello
Click "Sync All Boards" and watch 300+ boards get indexed in minutes.

### 5. Ask Anything
```
"List all my marketing frameworks"
"Find email templates for webinar follow-ups"
"What did I say about pricing strategies?"
```

---

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Trello    │────▶│   SQLite    │────▶│   Gemini    │
│   300+ Boards     │   Local DB  │     │   1.5 Flash │
└─────────────┘     └─────────────┘     └─────────────┘
      ▲                   │                    │
      │                   │                    ▼
   Sync Once         Persist Forever    Answer Anything
```

**Why "Lazy RAG"?**

Traditional RAG systems chunk documents, create embeddings, and store them in vector databases. That's a lot of complexity.

Gemini 1.5 Flash has a 1 million token context window. We just... dump everything in there. It works. It's fast. It's simple.

---

## Architecture

```
PattysTrellobrain/
├── app.py              # Main Streamlit application
├── database.py         # SQLite persistence layer
├── trello_client.py    # Trello API with rate limiting
├── castmagic_client.py # Cast Magic transcription API
├── scheduler.py        # Background sync scheduler
├── requirements.txt    # Dependencies
└── .env.example        # Environment template
```

### Database Schema

| Table | Purpose |
|-------|---------|
| `trello_cards` | All synced Trello content |
| `documents` | Uploaded PDFs, text files |
| `castmagic_transcripts` | Audio/video transcriptions |
| `clients` | Client profiles for customization |
| `chat_history` | Conversation persistence |
| `sync_metadata` | API keys, validation states, sync timestamps |

---

## API Status Indicators

The sidebar shows real-time API status:

| Icon | Meaning |
|------|---------|
| ⚪ | Not configured |
| ❓ | Entered, not tested |
| ✅ | Tested & ready |

Click **[Test]** to validate any API key.

---

## Tech Stack

- **Frontend**: Streamlit
- **Database**: SQLite (zero config, portable)
- **AI**: Google Gemini 1.5 Flash (1M token context)
- **APIs**: Trello REST API, Cast Magic API

---

## FAQ

**Q: How much does this cost?**
- Gemini API: Free tier available
- Trello API: Free
- Cast Magic: Requires developer access (email them)

**Q: How long does the initial sync take?**
- ~2-5 minutes for 300 boards, depending on card count

**Q: Does this work offline?**
- After syncing, yes. The AI queries require internet (Gemini API).

**Q: Is my data secure?**
- Everything stays local in SQLite. API keys are stored in the local database, never transmitted except to authenticate with the respective services.

---

## License

MIT

---

Built for Patty. Built for anyone drowning in their own content.
