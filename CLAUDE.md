# AeroSense AI Agent Workflow Configuration (CLAUDE.md)

Welcome to the **AeroSense Drone GCS & Payload Project** workspace. This repository contains the ground control cockpit, environmental mapping tools, hardware scripts, and payload control firmware for a quadcopter pollution mapping system.

---

## 🛠️ Dev Commands

| Goal | Command | Execution Directory |
|---|---|---|
| **Launch GCS & Dashboard Stack** | `python project/launcher.py` | Project Root |
| **Run Simulated Flight Telemetry** | `python project/Ground/ground_station/simulate_flight.py` | Project Root |
| **Run Live LoRa Receiver** | `python project/Ground/ground_station/aerosense_ground.py` | Project Root |
| **Start REST API (Flask)** | `python project/Ground/ground_station/aerosense_api.py` | Project Root |
| **Start Plotly Dash Dashboard** | `python project/dashboard/aerosense_dashboard.py` | Project Root |
| **Build React UI (GCS)** | `npm.cmd run build` | `project/Ground/ground_control_app` |
| **Run React UI Dev Server** | `npm.cmd run dev` | `project/Ground/ground_control_app` |
| **Python Syntax Check** | `python -m py_compile <file_path>` | Anywhere |

---

## 🤖 Virtual Engineering Team Personas

To maintain code standards, the AI developer can act under one of the following virtual roles:

### 1. `[CEO]` — Product & UX Architect
*   **Focus**: User interface, visual excellence, layouts, and copy.
*   **Rules**:
    *   Keep interfaces responsive and premium.
    *   Prioritize rich aesthetics: dark charcoal background (`#080809`), matte card design with subtle borders, and vibrant neon orange accents (`#ff5500`, `#ff8833`).
    *   Ensure all screens use Vanilla CSS and are free of generic styles.
*   **Workflows**: Request CEO review using `/ask-ceo` or `/review-layout` to check alignments, padding, animations, and color harmony.

### 2. `[Architect]` — Data & Systems Planner
*   **Focus**: Inter-process communication, REST controllers, serial/SPI telemetry pipelines, and SQLite persistence.
*   **Rules**:
    *   Ensure Flask API routers, SQLite databases, and message queues cleanly separate responsibilities.
    *   Check for socket/port conflicts and ensure processes exit gracefully by releasing ports (e.g. `taskkill` logic).
*   **Workflows**: Ask the architect for a design layout (`/review-architecture`) before implementing major telemetry or data-layer changes.

### 3. `[Engineer]` — Frontend & Backend Builder
*   **Focus**: Writing clean, modular React (JSX/JS) components, Python firmware control loops, and CSS modules.
*   **Rules**:
    *   Use type hints in Python.
    *   In React, use modular, functional components. Keep inline styles minimal and delegate layout details to `index.css`.
    *   Preserve all existing docstrings, serial parameters, and comments.

### 4. `[QA & Security]` — Systems Auditor
*   **Focus**: Port conflict management, database injection safety, and robust error handling.
*   **Rules**:
    *   Always use parameterized database inputs to protect SQL endpoints.
    *   Ensure every network call (Fetch, axios, or urllib) handles timeouts and connection losses.
    *   Run linting/compilation checks (`py_compile` and `npm run build`) before delivering updates.

---

## 💡 Codebase Guidelines

### 🐍 Python Backend & Firmware
*   Open database handles using SQLite timeouts (`timeout=0.5` or `1.0`) to avoid write locks from concurrent threads.
*   Always close database connection handles in a `finally:` block.
*   Maintain physical pin mappings, I2C addresses, and baud rates in `project/firmware/config.json`. Do not hardcode them in logic files.

### ⚛️ React GCS UI
*   Primary theme colors:
    *   `--bg-primary`: `#080809` (slate black)
    *   `--bg-secondary`: `#0e0e10` (charcoal dark)
    *   `--color-purple` / `--color-orange`: `#ff5500` (neon orange brand accent)
    *   `--color-purple-light` / `--color-orange-light`: `#ff8833` (light orange alert text)
*   Add hover transitions on interactive components to give a tactile feel to the Ground Control Station app.

### 📁 Git Hygiene
*   Keep local simulation logs, databases, `.pkl` models, and `.env` credentials in `.gitignore`.
*   Commit changes in atomic blocks with descriptive, imperative commit messages.
