# Agent Coding Standards

**Version:** 1.3
**Effectivity:** Immediate
**Audience:** All AI Agents (Manager, Backend_Dev, Frontend_Dev, QA_Engineer)

These are the **Mandatory Rules** for all code, configurations, and documentation generated within this project.

---

## 1. Python Standards

```yaml
# RAG METADATA
rag_id: "standard_python_v1"
domain: "backend"
context_scope: ["python_development", "scripting", "refactoring"]
keywords: 
  - "snake_case"
  - "docstrings"
  - "typing"
  - "type_hints"
  - "error_handling"
target_agent_personas: ["Backend_Dev", "QA_Engineer", "Manager"]
embedding_weight: "high"
last_updated: "2025-12-10"
related_documents: ["main.py", "requirements.txt"]
rules_summary: "Enforces snake_case, Google-style docstrings, type hinting, and try-except blocks."
```

### Naming Conventions
*   **Functions/Variables:** MUST use `snake_case` (e.g., `calculate_user_metrics`).
*   **Classes:** MUST use `PascalCase` (e.g., `TaskManager`).
*   **Constants:** MUST use `UPPER_CASE` (e.g., `MAX_RETRIES = 5`).

### Documentation
*   **Docstrings:** EVERY function and class MUST have a Google-style docstring explaining purpose, arguments, and return values.
*   **Inline Comments:** Explain complex logic ("Why"), not syntax ("What").

### Type Safety
*   Use the `typing` module for all function signatures where possible.
    *   *Example:* `def connect(retries: int) -> bool:`

### Imports
*   **Order:** Standard Library -> Third Party -> Local Application.
*   **Avoid:** `from module import *`. Explicitly import used functions to prevent namespace pollution.

### Error Handling
*   Use `try-except` blocks for all external operations (I/O, Network, DB).
*   **Never** use bare `except:` clauses. Catch specific exceptions (e.g., `except FileNotFoundError:`).

---

## 2. Flask & Backend Standards

```yaml
# RAG METADATA
rag_id: "standard_flask_v1"
domain: "backend"
context_scope: ["web_server", "api_design", "security"]
keywords: 
  - "flask"
  - "routing"
  - "post_redirect_get"
  - "environment_variables"
  - "secrets_management"
target_agent_personas: ["Backend_Dev", "QA_Engineer"]
embedding_weight: "critical"
last_updated: "2025-12-10"
related_documents: ["app.py", ".env"]
rules_summary: "Mandates @app.route decorators, PRG pattern for forms, and environment variables for secrets."
```

### Routing
*   Functions handling routes MUST be decorated with `@app.route`.
*   Define HTTP methods explicitly: `@app.route('/submit', methods=['POST'])`.

### Response Management
*   **POST/PUT/DELETE:** On success, ALWAYS return `redirect(url_for('target_route'))` (Post/Redirect/Get pattern).
*   **GET:** Return `render_template(...)` or JSON data.

### Form Errors
*   Flash messages to the session (`flash("Error message", "category")`) rather than rendering error pages directly.

### Configuration
*   **NO hardcoded secrets.** Use `os.environ.get('KEY_NAME')`.
*   Set `app.secret_key` from environment variables, never string literals in the code.

---

## 3. Frontend & UI Standards

```yaml
# RAG METADATA
rag_id: "standard_frontend_v1"
domain: "frontend"
context_scope: ["ui_design", "accessibility", "responsive_layout"]
keywords: 
  - "semantic_html"
  - "css_grid"
  - "mobile_first"
  - "accessibility"
  - "alt_tags"
target_agent_personas: ["Frontend_Dev", "QA_Engineer"]
embedding_weight: "medium"
last_updated: "2025-12-10"
related_documents: ["templates/index.html", "static/style.css"]
rules_summary: "Requires semantic HTML5, mobile-first CSS, and mandatory accessibility attributes."
```

### Structure
*   Use Semantic HTML5 tags (`<header>`, `<main>`, `<section>`, `<footer>`) instead of generic div soup.

### Styling
*   Ensure "Mobile-First" responsiveness using CSS Grid or Flexbox.
*   Use internal CSS (inside `<style>` block in head) for single-file template simplicity, or explicit linking if using static assets.

### Accessibility
*   All `<img>` tags MUST have an `alt` attribute.
*   Forms MUST have `<label>` tags associated with inputs via `for` attributes.

---

## 4. Git & Version Control Standards

```yaml
# RAG METADATA
rag_id: "standard_git_v1"
domain: "devops"
context_scope: ["version_control", "collaboration", "ci_cd"]
keywords: 
  - "git_config"
  - "atomic_commits"
  - "commit_messages"
  - "gitignore"
  - "imperative_mood"
target_agent_personas: ["Manager", "Backend_Dev", "Frontend_Dev"]
embedding_weight: "high"
last_updated: "2025-12-10"
related_documents: [".gitignore"]
rules_summary: "Enforces distinct user identity, atomic commits, imperative messages, and strict .gitignore usage."
```

### Identity
*   Configure user before committing: `git config user.email "agent@bot.com"` / `git config user.name "AgentBot"`.

### Commit Logic
*   **Atomic Commits:** One feature or fix per commit. Do not combine backend logic and frontend styling in one commit if possible.

### Messages
*   Use imperative mood (e.g., "Add user login route", not "Added user login route").

### Safety
*   **NEVER** commit `.env` files, `venv/`, or `__pycache__` directories. Ensure `.gitignore` is checked first.

---

## 5. QA & Testing Standards

```yaml
# RAG METADATA
rag_id: "standard_qa_v1"
domain: "qa"
context_scope: ["testing", "validation", "debugging"]
keywords: 
  - "test_isolation"
  - "assertions"
  - "teardown"
  - "error_messages"
target_agent_personas: ["QA_Engineer", "Backend_Dev"]
embedding_weight: "high"
last_updated: "2025-12-10"
related_documents: ["tests/", "main.py"]
rules_summary: "Requires independent tests, proper teardown cleanup, and explicit assertion error messages."
```

### Test Isolation
*   Tests MUST NOT rely on the state of a previous test run.
*   Clean up created data (teardown) after tests finish.

### Assertions
*   Use explicit error messages in assertions: `assert response.status_code == 200, f"Expected 200, got {response.status_code}"`.

---

## 6. Metadata Tags for RAG (Retrieval-Augmented Generation)

Use these tags in the file header or within a comment block to optimize this document for vector database indexing.

```yaml
# RAG METADATA
rag_id: "doc_coding_standards_v1.3"
domain: "devops"
context_scope: ["meta", "documentation_standards"]
keywords: 
  - "rag"
  - "metadata"
  - "indexing"
target_agent_personas: ["Manager"]
embedding_weight: "low"
last_updated: "2025-12-10"
related_documents: ["memory.py"]
rules_summary: "Meta-rules for defining RAG metadata tags."
```