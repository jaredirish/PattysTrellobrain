"""
Patty's Knowledge Brain - Main Application

A "Lazy RAG" solution using Gemini's massive context window to search
across Trello boards, uploaded documents, and Cast Magic transcripts.
Includes client profiles for applying frameworks to specific client needs.
"""

import streamlit as st
import google.generativeai as genai
import hashlib
from io import BytesIO
from datetime import datetime
import pypdf

from database import DatabaseManager
from trello_client import TrelloClient
from castmagic_client import CastMagicClient
from scheduler import SyncScheduler

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Patty's Knowledge Brain",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for copy-friendly output
st.markdown("""
<style>
    .copy-box {
        background-color: #f0f2f6;
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0;
        border-left: 4px solid #4CAF50;
    }
    .quick-action {
        margin: 4px 0;
    }
    .client-card {
        background-color: #e8f4ea;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
    }
    /* Premium Option C: The "Action Tease" */
    .premium-card-c {
        border: 1px solid #ddd;
        border-left: 5px solid #ff4b4b; /* Streamlit Red/Pink */
        border-radius: 8px;
        padding: 15px;
        background-color: white;
        display: flex;
        justify_content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    .premium-text-group {
        display: flex;
        flex-direction: column;
    }
    .premium-title {
        font-weight: bold;
        font-size: 16px;
        margin: 0;
        color: #333; /* Ensure contrast */
    }
    .premium-desc {
        font-size: 12px;
        color: #666; /* Ensure contrast */
        margin: 0;
    }
    .upgrade-btn-c {
        background-color: #ff4b4b;
        color: white;
        border: none;
        padding: 6px 12px;
        border-radius: 5px;
        font-weight: 600;
        cursor: pointer;
        text-transform: uppercase;
        font-size: 12px;
        text-decoration: none;
    }
    .upgrade-btn-c:hover {
        background-color: #e04444;
    }
</style>
""", unsafe_allow_html=True)


# --- INITIALIZE DATABASE ---
@st.cache_resource
def get_database():
    """Get or create the database manager (cached)."""
    return DatabaseManager()

db = get_database()


# --- SESSION STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = db.get_chat_history()

if "sync_status" not in st.session_state:
    st.session_state.sync_status = ""

if "selected_client" not in st.session_state:
    st.session_state.selected_client = None

if "castmagic_pending" not in st.session_state:
    st.session_state.castmagic_pending = []

# Load stored API keys from database
if "keys_loaded" not in st.session_state:
    st.session_state.keys_loaded = True
    stored_gemini = db.get_metadata("api_key_gemini")
    stored_trello_key = db.get_metadata("api_key_trello")
    stored_trello_token = db.get_metadata("api_key_trello_token")
    stored_castmagic = db.get_metadata("api_key_castmagic")

    if stored_gemini:
        st.session_state.gemini_api_key = stored_gemini
    if stored_trello_key:
        st.session_state.trello_api_key = stored_trello_key
    if stored_trello_token:
        st.session_state.trello_token = stored_trello_token
    if stored_castmagic:
        st.session_state.castmagic_api_key = stored_castmagic


# --- HELPER FUNCTIONS ---

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file."""
    try:
        pdf_reader = pypdf.PdfReader(BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        return f"[Error reading PDF: {e}]"


def process_uploaded_file(uploaded_file) -> tuple[str, str]:
    """Process an uploaded file and return (content, file_hash)."""
    file_bytes = uploaded_file.getvalue()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    file_extension = uploaded_file.name.split('.')[-1].lower()

    if file_extension == 'pdf':
        content = extract_text_from_pdf(file_bytes)
    else:
        try:
            content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = "[Error: Could not decode text file]"

    return content, file_hash


def get_trello_client():
    """Create a Trello client from session state credentials."""
    api_key = st.session_state.get("trello_api_key", "").strip()
    token = st.session_state.get("trello_token", "").strip()
    if api_key and token:
        return TrelloClient(api_key, token)
    return None


def get_castmagic_client():
    """Create a Cast Magic client from session state credentials."""
    api_secret = st.session_state.get("castmagic_api_key", "")
    if api_secret:
        return CastMagicClient(api_secret)
    return None


def format_time_ago(dt: datetime) -> str:
    """Format a datetime as a relative time string."""
    if dt is None:
        return "Never"
    now = datetime.now()
    diff = now - dt.replace(tzinfo=None)

    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"


def format_duration(seconds: float) -> str:
    """Format seconds as mm:ss or hh:mm:ss."""
    if seconds is None:
        return "Unknown"
    minutes = int(seconds / 60)
    secs = int(seconds % 60)
    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def run_query(prompt: str, include_client: bool = True):
    """Run a query against the knowledge base."""
    gemini_key = st.session_state.get("gemini_api_key")
    if not gemini_key:
        st.error("Please enter a Gemini API key first.")
        return None

    genai.configure(api_key=gemini_key.strip())

    # Build context
    context = db.get_all_content()
    client_context = ""

    if include_client and st.session_state.selected_client:
        client_context = db.get_client_context()

    system_prompt = f"""You are Patty's Marketing Knowledge Assistant - a smart librarian that doesn't just find things, but makes them ACTIONABLE.

YOUR MISSION:
1. Find the relevant frameworks, prompts, and strategies from Patty's knowledge base
2. Present them in a COPY-READY format she can immediately use
3. When a client is specified, ADAPT the framework specifically for that client
4. Be specific - quote card names, board names, document names, and transcript titles
5. If you can't find something, say so clearly

CONTENT SOURCES:
- Trello cards (boards, lists, card content)
- Uploaded documents (PDFs, transcripts, text files)
- Cast Magic transcripts (podcast/video transcriptions with speaker labels)

OUTPUT STYLE:
- Lead with the actionable content (prompts, frameworks, sequences)
- Use clear headers and bullet points
- Make it COPY-PASTE ready
- End with source attribution (which board/document/transcript this came from)

{f'''ACTIVE CLIENT CONTEXT:
{client_context}

When the user mentions applying something "for [client name]", customize the output specifically for that client's business, audience, and offerings.''' if client_context else ''}

KNOWLEDGE BASE:
{context}

USER REQUEST:
{prompt}

Provide a helpful, organized, COPY-READY response:"""

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg:
             try:
                 models = list(genai.list_models())
                 valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
                 error_msg += f"\n\nAvailable models: {', '.join(valid_models)}"
             except:
                 pass
        st.error(f"Error: {error_msg}")
        return None


# --- SIDEBAR ---
with st.sidebar:
    st.title("🧠 Knowledge Brain")

    # Quick stats
    stats = db.get_stats()
    cols = st.columns(2)
    with cols[0]:
        st.metric("Boards", len(stats["boards"]))
    with cols[1]:
        st.metric("Cards", stats["trello_cards"])
    
    cols2 = st.columns(2)
    with cols2[0]:
        st.metric("Docs", stats["documents"])
    with cols2[1]:
        st.metric("Clients", stats["clients"])

    st.caption(f"Last sync: {format_time_ago(stats['last_sync'])}")
    st.divider()

    # --- Tabs for different settings ---
    tab1, tab2, tab3, tab4 = st.tabs(["Keys", "Trello", "Clients", "✨ Upgrades"])

    with tab1:
        st.subheader("API Configuration")
        st.caption("Keys are saved locally and persist across sessions.")

        # --- Gemini ---
        gemini_key_value = st.session_state.get("gemini_api_key", "")
        gemini_validated = db.get_metadata("api_validated_gemini") == "true"
        if not gemini_key_value:
            gemini_status = "⚪"
            gemini_status_text = "Not configured"
        elif gemini_validated:
            gemini_status = "✅"
            gemini_status_text = "Ready"
        else:
            gemini_status = "❓"
            gemini_status_text = "Not tested"

        st.markdown(f"**{gemini_status} Gemini API** [🔗 Get Key](https://aistudio.google.com/app/apikey)")
        gemini_key = st.text_input(
            "Gemini API Key",
            type="password",
            key="gemini_api_key",
            label_visibility="collapsed",
            placeholder="Paste your Gemini API key"
        )

        if gemini_key:
            clean_key = gemini_key.strip()
            if clean_key != gemini_key:
                st.session_state.gemini_api_key = clean_key
                st.rerun()

            # Save if changed
            if clean_key != db.get_metadata("api_key_gemini"):
                db.set_metadata("api_key_gemini", clean_key)
                db.set_metadata("api_validated_gemini", "false")  # Reset validation

            # Test button
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("Test", key="test_gemini", use_container_width=True):
                    with st.spinner("🔄"):
                        try:
                            genai.configure(api_key=clean_key)
                            model = genai.GenerativeModel('gemini-2.0-flash')
                            model.generate_content("Say 'ok'")
                            db.set_metadata("api_validated_gemini", "true")
                            st.toast("✅ Gemini API Valid!", icon="🎉")
                            st.rerun()
                        except Exception as e:
                            db.set_metadata("api_validated_gemini", "false")
                            error_msg = str(e)
                            if "404" in error_msg:
                                try:
                                    models = list(genai.list_models())
                                    valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
                                    error_msg += f"\n\nAvailable models: {', '.join(valid_models)}"
                                except:
                                    pass
                            st.toast(f"❌ Invalid: {error_msg}", icon="⚠️")

            with col1:
                if gemini_validated:
                    st.caption("✅ Tested & ready")
                else:
                    st.caption("❓ Click Test to validate")

        st.markdown("---")

        # --- Trello ---
        trello_key_value = st.session_state.get("trello_api_key", "")
        trello_token_value = st.session_state.get("trello_token", "")
        trello_validated = db.get_metadata("api_validated_trello") == "true"

        if not trello_key_value or not trello_token_value:
            trello_status = "⚪"
        elif trello_validated:
            trello_status = "✅"
        else:
            trello_status = "❓"

        st.markdown(f"**{trello_status} Trello API** [🔗 Get Keys](https://trello.com/power-ups/admin)")
        st.caption("Create a Power-Up → copy API Key → click 'Token' link")

        trello_api_key = st.text_input(
            "Trello API Key",
            type="password",
            key="trello_api_key",
            label_visibility="collapsed",
            placeholder="Trello API Key"
        )
        trello_token = st.text_input(
            "Trello Token",
            type="password",
            key="trello_token",
            label_visibility="collapsed",
            placeholder="Trello Token"
        )

        if trello_api_key and trello_token:
            clean_key = trello_api_key.strip()
            clean_token = trello_token.strip()
            
            if clean_key != trello_api_key:
                st.session_state.trello_api_key = clean_key
                st.rerun()
            if clean_token != trello_token:
                st.session_state.trello_token = clean_token
                st.rerun()

            # Save if changed
            if clean_key != db.get_metadata("api_key_trello") or clean_token != db.get_metadata("api_key_trello_token"):
                db.set_metadata("api_key_trello", clean_key)
                db.set_metadata("api_key_trello_token", clean_token)
                db.set_metadata("api_validated_trello", "false")

            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("Test", key="test_trello", use_container_width=True):
                    with st.spinner("🔄"):
                        client = TrelloClient(clean_key, clean_token)
                        success, msg = client.test_connection()
                        if success:
                            db.set_metadata("api_validated_trello", "true")
                            st.toast(f"✅ {msg}", icon="🎉")
                            st.rerun()
                        else:
                            db.set_metadata("api_validated_trello", "false")
                            st.toast(f"❌ {msg}", icon="⚠️")
            with col1:
                if trello_validated:
                    st.caption("✅ Tested & ready")
                else:
                    st.caption("❓ Click Test to validate")

        st.markdown("---")

        # --- Cast Magic ---
        castmagic_key_value = st.session_state.get("castmagic_api_key", "")
        castmagic_validated = db.get_metadata("api_validated_castmagic") == "true"

        if not castmagic_key_value:
            castmagic_status = "⚪"
        elif castmagic_validated:
            castmagic_status = "✅"
        else:
            castmagic_status = "❓"

        st.markdown(f"**{castmagic_status} Cast Magic API** [🔗 Request Access](https://castmagic.io)")
        st.caption("Email justin@castmagic.io for developer API access")

        castmagic_key = st.text_input(
            "Cast Magic API Secret",
            type="password",
            key="castmagic_api_key",
            label_visibility="collapsed",
            placeholder="Cast Magic API Secret"
        )

        if castmagic_key:
            clean_key = castmagic_key.strip()
            if clean_key != castmagic_key:
                st.session_state.castmagic_api_key = clean_key
                st.rerun()

            if clean_key != db.get_metadata("api_key_castmagic"):
                db.set_metadata("api_key_castmagic", clean_key)
                db.set_metadata("api_key_castmagic", castmagic_key)
                db.set_metadata("api_validated_castmagic", "false")

            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("Test", key="test_castmagic", use_container_width=True):
                    with st.spinner("🔄"):
                        cm_client = CastMagicClient(clean_key)
                        success, msg = cm_client.test_connection()
                        if success:
                            db.set_metadata("api_validated_castmagic", "true")
                            st.toast(f"✅ {msg}", icon="🎉")
                            st.rerun()
                        else:
                            db.set_metadata("api_validated_castmagic", "false")
                            st.toast(f"❌ {msg}", icon="⚠️")
            with col1:
                if castmagic_validated:
                    st.caption("✅ Tested & ready")
                else:
                    st.caption("❓ Click Test to validate")

    with tab2:
        st.subheader("Trello Sync")

        client = get_trello_client()
        if client:
            # Test connection first
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔌 Test Connection", use_container_width=True):
                    with st.spinner("Testing..."):
                        success, msg = client.test_connection()
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
            with col2:
                if st.button("🔄 Sync All Boards", use_container_width=True):
                    scheduler = SyncScheduler(client, db)
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def update_progress(current, total, message):
                        if total > 0:
                            progress_bar.progress(current / total)
                        status_text.text(message)

                    success, message = scheduler.sync_trello_data(progress_callback=update_progress)
                    progress_bar.empty()
                    status_text.empty()

                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

            # Board summary
            if stats["boards"]:
                st.caption("**Synced Boards:**")
                for board in stats["boards"][:8]:
                    st.text(f"• {board['board_name'][:25]}: {board['card_count']}")
        else:
            st.info("Add Trello credentials in API Keys tab")

        st.divider()

        # Document upload
        st.subheader("Upload Documents")
        uploaded_files = st.file_uploader(
            "Drop files here",
            type=["txt", "pdf", "md", "csv", "json"],
            accept_multiple_files=True,
            key="file_uploader",
            label_visibility="collapsed"
        )

        if uploaded_files and st.button("📥 Index Files", use_container_width=True):
            added = 0
            for f in uploaded_files:
                content, file_hash = process_uploaded_file(f)
                if db.add_document(f.name, f.name.split('.')[-1], content, file_hash):
                    added += 1
            if added:
                st.success(f"Added {added} document(s)")
                st.rerun()

    with tab3:
        st.subheader("Client Profiles")
        st.caption("Add clients for personalized outputs")

        # Add new client
        with st.expander("➕ Add New Client"):
            new_name = st.text_input("Client Name", key="new_client_name")
            new_business = st.text_input("Business Type", key="new_client_business")
            new_audience = st.text_input("Target Audience", key="new_client_audience")
            new_offerings = st.text_area("Key Offerings", key="new_client_offerings", height=80)
            new_notes = st.text_area("Notes", key="new_client_notes", height=80)

            if st.button("Save Client", use_container_width=True):
                if new_name:
                    if db.add_client(new_name, new_business, new_audience, new_offerings, new_notes):
                        st.success(f"Added {new_name}!")
                        st.rerun()
                    else:
                        st.error("Client already exists")
                else:
                    st.warning("Enter a name")

        # List existing clients
        clients = db.get_all_clients()
        if clients:
            st.caption("**Your Clients:**")
            for client in clients:
                col1, col2 = st.columns([4, 1])
                with col1:
                    if st.button(f"👤 {client['name']}", key=f"sel_{client['name']}", use_container_width=True):
                        st.session_state.selected_client = client['name']
                        st.rerun()
                with col2:
                    if st.button("🗑", key=f"del_{client['name']}"):
                        db.delete_client(client['name'])
                        if st.session_state.selected_client == client['name']:
                            st.session_state.selected_client = None
                        st.rerun()

    with tab4:
        st.subheader("🚀 Future Enhancements")
        st.caption("Unlock the full potential of your Marketing Brain.")

        st.markdown("### 🎙️ [CastMagic](https://castmagic.io) Integration")
        
        cm_features = [
             ("🪄 Auto-Transcribe", "Auto-ingest full transcripts from your podcasts and YouTube videos."),
             ("🏃‍♂️ Run on CastMagic", "Found a Trello prompt? Run it on your audio transcripts instantly."),
             ("🔄 Sync to CastMagic", "Push generated insights back to CastMagic as show notes."),
        ]

        for i, (title, desc) in enumerate(cm_features):
            st.markdown(f"""
            <div class="premium-card-c">
                <div class="premium-text-group">
                    <p class="premium-title">{title}</p>
                    <p class="premium-desc">{desc}</p>
                </div>
                <button class="upgrade-btn-c">Get PRO</button>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown("### 🧠 General Enhancements")
        
        premium_features = [
            ("🎙️ Voice Command", "Talk to your brain hands-free while driving or walking."),
            ("🕸️ Visual Graph", "3D interactive map showing hidden connections between cards."),
            ("✨ Magic Drafter", "One-click generation for Emails, Webinars, and LinkedIn posts."),
            ("📱 Mobile App", "Native mobile experience with push notifications."),
            ("🔗 Zapier Connect", "Auto-trigger new research when you add a Trello card.")
        ]

        for i, (title, desc) in enumerate(premium_features):
            st.markdown(f"""
            <div class="premium-card-c">
                <div class="premium-text-group">
                    <p class="premium-title">{title}</p>
                    <p class="premium-desc">{desc}</p>
                </div>
                <button class="upgrade-btn-c">Get PRO</button>
            </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        st.caption("✅ **Included in Current Plan:**")
        st.caption("• 🕵️ Lazy RAG Search (Unlimited)")
        st.caption("• 📎 PDF & Doc Ingestion")
        st.caption("• 🔄 Live Trello Sync")
        st.caption("• 🧠 Persistent Memory")


    st.divider()

    # Clear buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear Chat", use_container_width=True):
            db.clear_chat_history()
            st.session_state.messages = []
            st.rerun()
    with col2:
        if st.button("Clear All", use_container_width=True):
            db.clear_trello_cards()
            db.clear_documents()
            db.clear_castmagic_transcripts()
            db.clear_chat_history()
            st.session_state.messages = []
            st.session_state.selected_client = None
            st.rerun()


# --- MAIN CONTENT ---

# Header with client selector
col1, col2 = st.columns([3, 1])
with col1:
    st.header("🧠 Ask Your Knowledge Base")
    if stats["trello_cards"] > 0:
        st.caption(f"Search across {stats['trello_cards']} Trello cards from {len(stats['boards'])} boards. No Trello connection needed.")
    else:
        st.caption("Sync once, search forever. All your Trello boards in one place.")

with col2:
    clients = db.get_all_clients()
    if clients:
        client_options = ["No client selected"] + [c['name'] for c in clients]
        current_idx = 0
        if st.session_state.selected_client:
            try:
                current_idx = client_options.index(st.session_state.selected_client)
            except ValueError:
                current_idx = 0

        selected = st.selectbox(
            "Apply to client:",
            client_options,
            index=current_idx,
            key="client_selector"
        )
        st.session_state.selected_client = selected if selected != "No client selected" else None

# Show active client context
if st.session_state.selected_client:
    client = db.get_client(st.session_state.selected_client)
    if client:
        st.info(f"**Active Client: {client['name']}** - {client.get('business_type', 'No business type')} | Target: {client.get('target_audience', 'Not specified')}")

# Check prerequisites
gemini_ready = bool(st.session_state.get("gemini_api_key"))
has_content = stats["trello_cards"] > 0 or stats["documents"] > 0 or stats["castmagic"] > 0

if not gemini_ready:
    if has_content:
        st.warning(f"👈 Enter your Gemini API key to search your {stats['trello_cards']} stored cards. Your data is safe in the local database!")
    else:
        st.warning("👈 Enter your Gemini API key in the sidebar to get started.")

if not has_content:
    st.info("""
    **Get Started in 2 Minutes:**

    1. Enter your **Gemini API key** (free at aistudio.google.com)
    2. Enter your **Trello API key + token** (from trello.com/power-ups/admin)
    3. Click **Sync Trello** - pulls ALL your boards into a local database

    **That's it!** After syncing, your data is stored locally. You can search across ALL 300+ boards without needing Trello open.

    Try searches like:
    - "Find Veronica's webinar prompt"
    - "What email sequence frameworks do I have?"
    - "Show me everything about sales funnels"
    """)

# Quick Actions
if has_content and gemini_ready:
    st.subheader("Quick Actions")
    cols = st.columns(4)

    quick_prompts = [
        ("📋 List frameworks", "List all the marketing frameworks, templates, and prompt sequences in my knowledge base. Group them by category."),
        ("✉️ Email sequences", "Find all email sequence templates and frameworks. Show me the key steps for each."),
        ("🎙 From transcripts", "What insights, quotes, or actionable tips are in my Cast Magic transcripts? Summarize by topic."),
        ("📊 Sales funnels", "What sales funnel templates or strategies do I have? Summarize the key stages.")
    ]

    for i, (label, prompt) in enumerate(quick_prompts):
        with cols[i]:
            if st.button(label, use_container_width=True, key=f"quick_{i}"):
                st.session_state.quick_prompt = prompt

    # Handle quick prompt
    if "quick_prompt" in st.session_state and st.session_state.quick_prompt:
        prompt = st.session_state.quick_prompt
        st.session_state.quick_prompt = None

        st.session_state.messages.append({"role": "user", "content": prompt})
        db.add_chat_message("user", prompt)

        with st.spinner("Searching your knowledge base..."):
            response = run_query(prompt)
            if response:
                st.session_state.messages.append({"role": "assistant", "content": response})
                db.add_chat_message("assistant", response)

        st.rerun()

st.divider()

# Helper function to render response with copy buttons
def render_with_copy(content: str, message_idx: int):
    """Render assistant response with copy buttons for full response and sections."""
    # Full response copy button at top
    # Full response copy button at top (Small and subtle)
    col1, col2 = st.columns([12, 1])
    with col2:
        if st.button("📋", key=f"copy_all_{message_idx}", help="Copy full response"):
            st.code(content, language=None)
            st.toast("Response expanded for copying!", icon="📋")

    # Show copy confirmation
    if st.session_state.get(f"copied_{message_idx}"):
        st.code(content, language=None)
        st.caption("👆 Select all and copy (Ctrl+A, Ctrl+C)")
        if st.button("Hide", key=f"hide_{message_idx}"):
            st.session_state[f"copied_{message_idx}"] = False
            st.rerun()
    else:
        # Parse sections (split by ## headers) for individual copy
        sections = []
        current_section = {"title": "Response", "content": ""}

        for line in content.split('\n'):
            if line.startswith('## '):
                if current_section["content"].strip():
                    sections.append(current_section)
                current_section = {"title": line[3:].strip(), "content": ""}
            else:
                current_section["content"] += line + "\n"

        if current_section["content"].strip():
            sections.append(current_section)

        # Render sections with mini copy buttons if multiple sections
        if len(sections) > 1:
            for idx, section in enumerate(sections):
                with st.container():
                    sec_col1, sec_col2 = st.columns([10, 1])
                    with sec_col1:
                        if section["title"] != "Response":
                            st.markdown(f"## {section['title']}")
                        st.markdown(section["content"])
                    with sec_col2:
                        # Subtle copy button for section
                        if st.button("📑", key=f"copy_sec_{message_idx}_{idx}", help=f"Copy section: {section['title']}"):
                             full_section = f"## {section['title']}\n{section['content']}" if section["title"] != "Response" else section["content"]
                             st.code(full_section, language=None)
                             st.toast(f"Section '{section['title']}' ready to copy!", icon="📑")
        else:
            # Single section - just render normally
            st.markdown(content)

# Chat history
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_with_copy(message["content"], idx)
        else:
            st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ex: 'Apply the webinar framework to my latest podcast' or 'Find prompts for Karen'"):
    if not gemini_ready:
        st.error("Please enter a Gemini API key first.")
        st.stop()

    if not has_content:
        st.warning("Please sync Trello, upload documents, or add transcripts first!")
        st.stop()

    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    db.add_chat_message("user", prompt)

    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Searching your knowledge base..."):
            response = run_query(prompt)
            if response:
                st.session_state.messages.append({"role": "assistant", "content": response})
                db.add_chat_message("assistant", response)
                st.rerun()  # Rerun to render with copy buttons


# --- FOOTER ---
st.divider()
st.caption(f"📊 {stats['trello_cards']} cards | {stats['documents']} docs | {stats['castmagic']} transcripts | {stats['clients']} clients")
