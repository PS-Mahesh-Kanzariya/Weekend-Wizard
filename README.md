# 🧙‍♂️ Weekend Wizard

## Introduction

Weekend Wizard is a friendly CLI agent designed to add some fun and usefulness to your weekends. It can:

* 🗺️ Plan a chill mini-itinerary
* 🌤️ Tell you the current weather
* 📚 Suggest books on a topic you like
* 😂 Crack a light-hearted joke
* 🐶 Share a dog picture link for good vibes

This is a **real agent**, not a simple script. Weekend Wizard decides **when to call tools**, invokes them using **MCP (Model Context Protocol)**, observes the results, and intelligently decides **when to stop**.

---

## Tech Overview

* Python CLI application
* MCP (Model Context Protocol) for tool invocation
* LLM powered via **GROQ API**
* Environment-based configuration

---

## Steps to Run the Project

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd <repo-folder>
```

### 2. Create and Activate a Virtual Environment

```bash
python -m venv venv

# On Windows
venv\\Scripts\\activate

# On macOS/Linux
source venv/bin/activate
```

### 3. Download `requirements.txt`

Make sure the `requirements.txt` file is present in the project root.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Create a `.env` File

Create a `.env` file in the root directory and add your GROQ API key:

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 6. Run the Agent

```bash
python agent_fun.py
```

---

## Example Usage

Once started, interact with Weekend Wizard through the CLI. Ask it to plan a weekend, suggest books, check the weather, or just brighten your mood.

---

## Vibes

This project is meant to be **lightweight, fun, and educational**, showcasing how real agents work with MCP while keeping things playful ✨

Happy weekend hacking! 🐾
