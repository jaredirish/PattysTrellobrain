"""
Patty's Knowledge Brain - Main Application

A "Lazy RAG" solution using Gemini's massive context window to search
across Trello boards and uploaded documents. Includes client profiles
for applying frameworks to specific client needs.
"""

import streamlit as st
import google.generativeai as genai
import hashlib
from io import BytesIO
from datetime import datetime
import pypdf

from database import DatabaseManager
from trello_client import TrelloClient
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
    api_key = st.session_state.get("trello_api_key", "")
    token = st.session_state.get("trello_token", "")
    if api_key and token:
        return TrelloClient(api_key, token)
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


def run_query(prompt: str, include_client: bool = True):
    """Run a query against the knowledge base."""
    gemini_key = st.session_state.get("gemini_api_key")
    if not gemini_key:
        st.error("Please enter a Gemini API key first.")
        return None

    genai.configure(api_key=gemini_key)

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
4. Be specific - quote card names, board names, and document names
5. If you can't find something, say so clearly

OUTPUT STYLE:
- Lead with the actionable content (prompts, frameworks, sequences)
- Use clear headers and bullet points
- Make it COPY-PASTE ready
- End with source attribution (which board/document this came from)

{f'''ACTIVE CLIENT CONTEXT:
{client_context}

When the user mentions applying something "for [client name]", customize the output specifically for that client's business, audience, and offerings.''' if client_context else ''}

KNOWLEDGE BASE:
{context}

USER REQUEST:
{prompt}

Provide a helpful, organized, COPY-READY response:"""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


# --- SIDEBAR ---
with st.sidebar:
    st.title("🧠 Knowledge Brain")

    # Quick stats
    stats = db.get_stats()
    cols = st.columns(3)
    with cols[0]:
        st.metric("Cards", stats["trello_cards"])
    with cols[1]:
        st.metric("Docs", stats["documents"])
    with cols[2]:
        st.metric("Clients", stats["clients"])

    st.caption(f"Last sync: {format_time_ago(stats['last_sync'])}")
    st.divider()

    # --- Tabs for different settings ---
    tab1, tab2, tab3 = st.tabs(["API Keys", "Trello", "Clients"])

    with tab1:
        st.subheader("API Configuration")

        gemini_key = st.text_input(
            "Gemini API Key",
            type="password",
            key="gemini_api_key",
            help="Free at aistudio.google.com"
        )
        if gemini_key:
            st.success("Gemini ready!")

        st.markdown("---")
        st.caption("**Trello Credentials**")
        st.markdown("[Get keys here](https://trello.com/power-ups/admin)")

        trello_api_key = st.text_input("Trello API Key", type="password", key="trello_api_key")
        trello_token = st.text_input("Trello Token", type="password", key="trello_token")

    with tab2:
        st.subheader("Trello Sync")

        client = get_trello_client()
        if client:
            if st.button("🔄 Sync Now", use_container_width=True):
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
            db.clear_chat_history()
            st.session_state.messages = []
            st.session_state.selected_client = None
            st.rerun()


# --- MAIN CONTENT ---

# Header with client selector
col1, col2 = st.columns([3, 1])
with col1:
    st.header("🧠 Ask Your Knowledge Base")
    st.caption("Find frameworks, prompts, and strategies. Get copy-ready output.")

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
has_content = stats["trello_cards"] > 0 or stats["documents"] > 0

if not gemini_ready:
    st.warning("👈 Enter your Gemini API key in the sidebar to get started.")

if not has_content:
    st.info("""
    **No content yet!**
    1. **Sync Trello** - Add API keys in sidebar, then click Sync
    2. **Upload Docs** - Drop PDFs, transcripts, or text files

    Once indexed, ask questions like:
    - "Find Veronica's webinar prompt sequence"
    - "What frameworks do I have for email sequences?"
    - "Apply the sales funnel template for Karen"
    """)

# Quick Actions
if has_content and gemini_ready:
    st.subheader("Quick Actions")
    cols = st.columns(4)

    quick_prompts = [
        ("📋 List all frameworks", "List all the marketing frameworks, templates, and prompt sequences in my knowledge base. Group them by category."),
        ("✉️ Email sequences", "Find all email sequence templates and frameworks. Show me the key steps for each."),
        ("🎙 Webinar prompts", "Find any webinar-related prompts, scripts, or frameworks. Make them copy-ready."),
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

# Chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ex: 'Find the prompt sequence for client onboarding' or 'Apply webinar framework for Karen'"):
    if not gemini_ready:
        st.error("Please enter a Gemini API key first.")
        st.stop()

    if not has_content:
        st.warning("Please sync Trello or upload documents first!")
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
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                db.add_chat_message("assistant", response)


# --- FOOTER ---
st.divider()
st.caption(f"📊 {stats['trello_cards']} cards | {stats['documents']} docs | {stats['clients']} clients | Synced: {format_time_ago(stats['last_sync'])}")
