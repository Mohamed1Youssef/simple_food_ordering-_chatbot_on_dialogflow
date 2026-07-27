Directory structure
===================
backend: Contains Python FastAPI backend code
db: contains rest_db.sql, the PostgreSQL schema + seed data script
dialogflow_assets: this has training phrases etc. for our intents
frontend: website code

Install dependencies
======================

cd backend
pip install -r requirements.txt

This installs fastapi[all], uvicorn, psycopg[binary], and python-dotenv.

Set up the database
================================
1. Create the database (once): using psql or pgAdmin, run
   CREATE DATABASE food_ordering_chatbot;
2. Connect to that database specifically and run db/rest_db.sql against it
   to create the tables, functions, procedures, and seed data.

Configure credentials
================================
1. In backend/, copy .env.example to a new file named .env
2. Fill in your real PostgreSQL password in .env (DB_PASSWORD=...)
   .env is gitignored and never committed - only .env.example is.

To start the FastAPI backend server
================================
1. Go to the backend directory in your terminal
2. Run this command: uvicorn main:app --reload

ngrok for https tunneling
================================
1. Install ngrok: https://ngrok.com/download
2. Add your authtoken (one-time): ngrok config add-authtoken YOUR_TOKEN
3. With uvicorn running on port 8000, in a separate terminal run:
   ngrok http 8000
4. Use the printed https://...ngrok-free.app URL as the Dialogflow
   fulfillment webhook URL.

NOTE: ngrok free-tier URLs can expire/change between sessions - update
the Dialogflow webhook URL again if a new tunnel is started.
