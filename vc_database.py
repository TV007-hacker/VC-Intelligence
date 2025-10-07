import requests
from datetime import datetime
import os
from flask import Flask, render_template_string, request, jsonify
from typing import List, Dict, Any

class VCDatabase:
    def __init__(self, airtable_base_id: str, airtable_api_key: str, claude_api_key: str = None):
        """Simple VC database interface with Claude"""
        
        self.airtable_base_id = airtable_base_id.strip()
        self.airtable_api_key = airtable_api_key.strip()
        self.airtable_base_url = f"https://api.airtable.com/v0/{self.airtable_base_id}"
        self.airtable_headers = {
            "Authorization": f"Bearer {self.airtable_api_key}",
            "Content-Type": "application/json"
        }
        
        self.claude_api_key = claude_api_key.strip() if claude_api_key else None
        self.database_context = ""
        self.last_sync = None
        
        print("VC Database initialized")

    def fetch_table(self, table_name: str) -> List[Dict[str, Any]]:
        """Fetch data from Airtable"""
        url = f"{self.airtable_base_url}/{table_name}"
        
        try:
            response = requests.get(url, headers=self.airtable_headers, timeout=30)
            
            if response.status_code == 200:
                records = response.json().get("records", [])
                print(f"Fetched {len(records)} records from '{table_name}'")
                return records
            else:
                print(f"Error fetching '{table_name}': {response.status_code}")
                
        except Exception as e:
            print(f"Error: {e}")
            
        return []
    
    def find_table(self) -> List[Dict]:
        """Find the right table"""
        possible_names = [
            "List of Cos",
            "companies_full_history_safe",
            "Companies",
            "Imported table",
            "Portfolio Companies",
        ]
        
        for name in possible_names:
            data = self.fetch_table(name)
            if data:
                print(f"Using table: '{name}'")
                return data
        
        return []

    def create_context(self, records: List[Dict]) -> str:
        """Create context from database"""
        context = ["=== VC DATABASE ===\n"]
        
        # Get all unique field names first
        all_fields = set()
        for record in records:
            fields = record.get("fields", {})
            all_fields.update(fields.keys())
        
        print(f"Available fields in Airtable: {sorted(all_fields)}")
        
        for record in records:
            fields = record.get("fields", {})
            
            # Try multiple field name variations
            company = (fields.get("company_name") or 
                      fields.get("Company Name") or 
                      fields.get("Company") or 
                      fields.get("name") or 
                      "Unknown")
            
            status = (fields.get("status") or 
                     fields.get("Status") or 
                     fields.get("Current status") or 
                     fields.get("Current Status") or "")
            
            notes = (fields.get("notes") or 
                    fields.get("Notes") or 
                    fields.get("call notes") or 
                    fields.get("Call Notes") or 
                    fields.get("Call notes") or "")
            
            date = (fields.get("date") or 
                   fields.get("Date") or 
                   fields.get("Last Contact") or 
                   fields.get("last_contact") or "")
            
            summary = (fields.get("pitch_deck_summary") or 
                      fields.get("Pitch Deck Summary") or 
                      fields.get("summary") or 
                      fields.get("Summary") or 
                      fields.get("deck_summary") or 
                      fields.get("Deck Summary") or "")
            
            context.append(f"\nCompany: {company}")
            if status:
                context.append(f"Status: {status}")
            if date:
                context.append(f"Date: {date}")
            if notes:
                context.append(f"Notes: {notes[:500]}")
            if summary:
                context.append(f"Deck Summary: {summary[:500]}")
        
        return "\n".join(context)

    def sync_database(self) -> bool:
        """Load database into context"""
        try:
            records = self.find_table()
            if not records:
                print("No data found")
                return False
                
            self.database_context = self.create_context(records)
            self.last_sync = datetime.now()
            
            print(f"Loaded {len(records)} companies")
            return True
            
        except Exception as e:
            print(f"Sync failed: {e}")
            return False

    def web_search_duckduckgo(self, query: str) -> str:
        """Search using DuckDuckGo (Free, no API key needed)"""
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=3):
                    title = r.get('title', 'No title')
                    snippet = r.get('body', 'No description')
                    link = r.get('link', '')
                    results.append(f"• {title}\n  {snippet}\n  Source: {link}")
            
            if results:
                return "\n\n".join(results)
            else:
                return "No search results found."
                
        except ImportError:
            print("DuckDuckGo library not installed. Run: pip install duckduckgo-search")
            return None
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return None

    def web_search_brave(self, query: str) -> str:
        """Search using Brave Search API (2000 free queries/month)"""
        api_key = os.getenv("BRAVE_API_KEY", "").strip()
        if not api_key:
            return None
        
        try:
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": 3},
                headers={"X-Subscription-Token": api_key},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for r in data.get("web", {}).get("results", [])[:3]:
                    title = r.get('title', 'No title')
                    snippet = r.get('description', 'No description')
                    link = r.get('url', '')
                    results.append(f"• {title}\n  {snippet}\n  Source: {link}")
                
                if results:
                    return "\n\n".join(results)
                else:
                    return "No search results found."
                    
        except Exception as e:
            print(f"Brave search error: {e}")
            return None

    def web_search_serpapi(self, query: str) -> str:
        """Search using SerpAPI (100 free searches/month)"""
        api_key = os.getenv("SERPAPI_KEY", "").strip()
        if not api_key:
            return None
        
        try:
            response = requests.get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": api_key, "num": 3},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                for r in data.get("organic_results", [])[:3]:
                    title = r.get('title', 'No title')
                    snippet = r.get('snippet', 'No description')
                    link = r.get('link', '')
                    results.append(f"• {title}\n  {snippet}\n  Source: {link}")
                
                if results:
                    return "\n\n".join(results)
                else:
                    return "No search results found."
                
        except Exception as e:
            print(f"SerpAPI search error: {e}")
            return None

    def web_search(self, query: str) -> str:
        """Search the web using multiple providers with fallback"""
        print(f"Searching web for: {query}")
        
        # Try providers in order of preference
        # 1. DuckDuckGo (Free, no key needed, unlimited)
        result = self.web_search_duckduckgo(query)
        if result:
            print("✓ Used DuckDuckGo")
            return result
        
        # 2. Brave Search (2000 free/month)
        result = self.web_search_brave(query)
        if result:
            print("✓ Used Brave Search")
            return result
        
        # 3. SerpAPI (100 free/month)
        result = self.web_search_serpapi(query)
        if result:
            print("✓ Used SerpAPI")
            return result
        
        # All providers failed
        print("✗ All search providers unavailable")
        return None

    def ask_claude(self, message: str) -> str:
        """Ask Claude with database context and web search"""
        if not self.claude_api_key:
            return "Claude API not configured"
        
        if not self.database_context:
            self.sync_database()
        
        # Check if we should search the web
        search_terms = ['news', 'latest', 'recent', 'current', 'market', 'competitor', 'research']
        should_search = any(term in message.lower() for term in search_terms)
        
        web_results = None
        if should_search:
            print("Searching web...")
            web_results = self.web_search(message)
        
        try:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.claude_api_key,
                "anthropic-version": "2023-06-01"
            }
            
            system_prompt = f"""You are helping analyze a VC fund's deal pipeline database.

DATABASE CONTEXT:
{self.database_context}

{f"WEB SEARCH RESULTS:\n{web_results}\n" if web_results else ""}

Answer questions naturally using the database and web search results when available. Be conversational and insightful."""
            
            payload = {
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 4000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": message}]
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            
            if response.status_code == 200:
                data = response.json()
                
                # Safely extract response
                if "content" in data and len(data["content"]) > 0:
                    return data["content"][0]["text"]
                else:
                    return "Claude returned empty response"
            else:
                error_msg = response.text[:200] if response.text else "Unknown error"
                return f"Claude API error ({response.status_code}): {error_msg}"
                
        except requests.Timeout:
            return "Request timed out. Please try again."
        except requests.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

# Flask app
app = Flask(__name__)
db = None

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>VC Database</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, system-ui, sans-serif;
            background: #0f172a;
            color: #fff;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            padding: 1.5rem 2rem;
            background: rgba(255,255,255,0.05);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .header h1 {
            font-size: 1.5rem;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .container {
            flex: 1;
            max-width: 900px;
            margin: 0 auto;
            width: 100%;
            padding: 1rem;
            display: flex;
            flex-direction: column;
        }
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
            background: rgba(255,255,255,0.02);
            border-radius: 12px 12px 0 0;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .message {
            margin-bottom: 1.5rem;
            display: flex;
            gap: 0.75rem;
        }
        .message.user { flex-direction: row-reverse; }
        .message-content {
            max-width: 75%;
            padding: 1rem;
            border-radius: 12px;
            line-height: 1.6;
            white-space: pre-wrap;
        }
        .message.user .message-content {
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
        }
        .message.assistant .message-content {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .input-area {
            display: flex;
            gap: 0.5rem;
            padding: 1rem;
            background: rgba(255,255,255,0.02);
            border-radius: 0 0 12px 12px;
            border: 1px solid rgba(255,255,255,0.1);
            border-top: none;
        }
        input {
            flex: 1;
            padding: 0.75rem 1rem;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 20px;
            background: rgba(255,255,255,0.05);
            color: #fff;
            outline: none;
        }
        input::placeholder { color: rgba(255,255,255,0.5); }
        button {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 20px;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            color: #fff;
            font-weight: 600;
            cursor: pointer;
        }
        button:hover { opacity: 0.9; }
        .sync-btn {
            background: linear-gradient(135deg, #10b981, #3b82f6);
            padding: 0.75rem 1rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>VC Database with Claude</h1>
    </div>
    <div class="container">
        <div class="messages" id="messages">
            <div class="message assistant">
                <div class="message-content">Hi! I have access to your deal pipeline database. Ask me anything about your companies, status updates, or request market research.</div>
            </div>
        </div>
        <div class="input-area">
            <button class="sync-btn" onclick="syncDB()">↻ Sync</button>
            <input type="text" id="input" placeholder="Ask about your pipeline..." maxlength="500">
            <button onclick="send()">Send</button>
        </div>
    </div>
    <script>
        const input = document.getElementById('input');
        const messages = document.getElementById('messages');
        
        function addMessage(content, isUser) {
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'assistant');
            div.innerHTML = '<div class="message-content">' + content + '</div>';
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }
        
        async function send() {
            const text = input.value.trim();
            if (!text) return;
            
            addMessage(text, true);
            input.value = '';
            
            try {
                const response = await fetch('/api/ask', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text})
                });
                
                const data = await response.json();
                addMessage(data.response || data.error || 'Error occurred');
            } catch (error) {
                addMessage('Connection error');
            }
        }
        
        async function syncDB() {
            addMessage('Syncing database...', false);
            try {
                const response = await fetch('/api/sync', {method: 'POST'});
                const data = await response.json();
                addMessage(data.message || 'Sync complete');
            } catch (error) {
                addMessage('Sync failed');
            }
        }
        
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') send();
        });
    </script>
</body>
</html>
''')

@app.route('/api/sync', methods=['POST'])
def sync():
    try:
        success = db.sync_database()
        return jsonify({
            "success": success,
            "message": "Database synced" if success else "Sync failed"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ask', methods=['POST'])
def ask():
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({"error": "No message"}), 400
        
        response = db.ask_claude(message)
        return jsonify({"response": response})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def main():
    global db
    
    airtable_base_id = os.getenv("AIRTABLE_BASE_ID", "").strip()
    airtable_api_key = os.getenv("AIRTABLE_API_KEY", "").strip()
    claude_api_key = os.getenv("CLAUDE_API_KEY", "").strip()
    
    if not airtable_base_id or not airtable_api_key:
        print("Missing Airtable credentials")
        return
    
    db = VCDatabase(airtable_base_id, airtable_api_key, claude_api_key)
    db.sync_database()
    
    port = int(os.getenv('PORT', 8080))
    print(f"Starting on port {port}")
    
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    main()
