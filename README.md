# ✈️ Cheap Flights App

A Python application for scraping **Google Flights** to find cheap flights.  
Supports **local development** and **Dockerized deployment**, and is easily extendable with new scraping logic.

---

## 📦 Features
- Scrapes **Google Flights** for cheap flight opportunities
- Modular structure for adding new scraping logic or flight search parameters
- Supports environment-based configuration via `CONFIG_MODULE`
- Works **locally** and in **Docker**

---

## 🚀 Quick Start (Local)

### 1. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the scraper
```bash
export CONFIG_MODULE=config_sets.config_wrzesien_550   # macOS/Linux
set CONFIG_MODULE=config_sets.config_wrzesien_550     # Windows

python main.py
```

---

## 🐳 Run with Docker

1. **Build and start containers**
```bash
docker-compose up --build
```

2. **Access container shell (optional)**
```bash
docker exec -it loty_wrzesien_550 bash
```

3. **Run the scraper inside the container**
```bash
python main.py
```

---

## 🧪 Testing

Create or run tests using `pytest`:
```bash
pytest
```

---

## 📂 Project Structure
```
tanielotyscrapper/
│
├── app/                   # Main Python application
│   ├── main.py            # Google Flights scraper
│   ├── wizzair.py
│   ├── ryanair.py
│   ├── mapyearforwizz.py
│   └── tests/             # Unit tests
│
├── docker-compose.yml     # Docker services
├── requirements.txt       # Python dependencies
├── README.md              # Project documentation
└── .gitignore
```

---

## ⚡ Notes
- `.gitignore` is already set to skip `venv/` and other large files.
- Docker maps the `app/` folder, so local code changes appear instantly in the container.
- Use `git filter-repo` if you accidentally commit large files.

---

## 📜 License
MIT License
