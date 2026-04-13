# Curiosity Meter

The AI-driven educational assessment platform that grades the quality of questions students ask, rather than their answers.

## Local Development Setup

Follow these steps to run the application locally. You will need 3 separate terminal windows to run the different parts of the stack.

### 1. Start the Databases (Docker)
You need Docker installed and running on your machine.
Open Terminal 1 at the root folder (`CuriosityMeter`) and run:
```bash
docker-compose up -d
```
*This spins up PostgreSQL (Port 5432), Redis (Port 6379), and Qdrant (Ports 6333/6334) in the background.*

---

### 2. Run the FastAPI Backend
Open Terminal 2 and navigate to the `backend` folder:
```bash
cd backend
```

Activate the virtual environment (Windows PowerShell):
```powershell
.\.venv\Scripts\activate
```

Install the required Python packages:
```bash
pip install -r requirements.txt
```

Start the FastAPI server:
```bash
uvicorn main:app --reload
```
*The backend API will now be running at **http://localhost:8000**.*
*(You can view the Swagger API Documentation at **http://localhost:8000/docs**)*

---

### 3. Run the Next.js Frontend
Open Terminal 3 and navigate to the `frontend` folder:
```bash
cd frontend
```

Install the node dependencies:
```bash
npm install
```

Start the Next.js frontend server:
```bash
npm run dev
```
*The frontend UI will now be available at **http://localhost:3000**.*
