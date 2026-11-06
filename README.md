# ✦ Jean AI — Local Desktop Assistant

> **A powerful, private, and customizable desktop AI assistant built in Python.**  
> Powered by **Ollama (`llama3.2`)**, **CustomTkinter**, and **SQLite**.

---

## ✨ Features

- 🧠 **Local LLM Intelligence**: Runs fully offline and privately on your machine using Ollama.
- 💬 **Persistent Chat Sessions**: Full session-based history management saved locally via SQLite database.
- 🗣️ **Active Listening & Interruptible TTS**: Responds with hands-free voice input and natural text-to-speech with instant interruption support.
- ⚡ **Global Hotkey & App Launcher**: Instantly toggle window visibility anywhere with `Ctrl + Space` or launch local Windows apps seamlessly.
- 🔍 **Live Web Search Fallback**: Real-time DuckDuckGo integration for up-to-date query responses.
- 💾 **Long-Term Agent Memory**: Store custom user facts and context across application restarts.
- 🎨 **Sleek Custom Canvas UI**: Dark-mode interface powered by CustomTkinter featuring a dynamic white ring brand icon.

---

## 🛠️ Tech Stack

- **GUI Framework**: CustomTkinter, Pillow
- **Local Inference Engine**: Ollama (`llama3.2`)
- **Database & Storage**: SQLite3
- **Audio & Voice**: `speech_recognition`, `pyttsx3`, `keyboard`
- **Search Engine**: DuckDuckGo API (`duckduckgo_search`)
- **Compilation**: PyInstaller

---

## 🚀 Getting Started

### Prerequisites

1. **Python 3.12+**
2. **Ollama Installed & Active**  
   Download Ollama and pull the target model:
   ```bash
   ollama pull llama3.2
