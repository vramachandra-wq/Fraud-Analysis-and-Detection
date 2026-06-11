# Banking Fraud Detection Platform

## Overview

This project is a Banking Fraud Detection Platform built using PostgreSQL, Airflow, XGBoost, Groq, Streamlit, Superset, and a 3 Level Data Architecture.

The platform provides:

* Transaction fraud detection
* VIP customer management
* Customer blacklist management
* AI generated transaction summaries
* Data pipeline orchestration using Airflow
* Interactive dashboards using Superset
* Machine Learning based fraud prediction using XGBoost

---

# Project Structure

```text
project/
├── app.py                          ← Entry point (3 tabs)
├── config/
│   └── settings.py                 ← DB credentials, model path, Groq config
├── database/
│   ├── connection.py               ← Database connection pool
│   ├── account_repository.py       ← Account validation
│   ├── blacklist_repository.py     ← Blacklist operations
│   ├── vip_repository.py           ← VIP operations
│   └── transaction_repository.py   ← Transaction logging
├── ml/
│   └── models/
│   ├── feature_engineering.py  ← FraudFeatureEngineer
│   ├── model_loader.py         ← Cached model loader
│   └── prediction_service.py   ← ML prediction service
├── ai/
│   ├── groq_client.py              ← Groq client initialization
│   └── summarizer.py               ← AI transaction summaries
├── services/
│   ├── fraud_service.py            ← Fraud detection pipeline
│   ├── vip_service.py              ← VIP provisioning
│   └── blacklist_service.py        ← Blacklist operations
├── ui/
│   ├── session_state.py            ← Streamlit session state
│   ├── dialogs.py                  ← Dialog popups
│   ├── transaction_tab.py          ← Fraud Detection tab
│   ├── vip_management_tab.py       ← VIP Management tab
│   └── chatbot_tab.py              ← AI Chatbot tab
└── utils/
    └── constants.py                ← Application constants
```

---

# Technology Stack

## Backend

* Python
* PostgreSQL
* Psycopg2

## Data Engineering

* Apache Airflow
* 3 Level Architecture
  * Staging Layer
  * Curated Layer
  * Aggregated Layer

## Machine Learning

* XGBoost

## Frontend

* Streamlit

## Business Intelligence and Visualization

* Apache Superset

## Generative AI

* Groq API
* Llama 3.1 8B

## Containerization

* Podman

---

# Setup Instructions

## 1. Install Dependencies

Create a Python Virtual Enviromnet first.

```bash
pip install -r requirements.txt
```

## 2. Configure Database Credentials

Update the PostgreSQL connection details in:

```text
config/settings.py
```

Ensure the credentials match your PostgreSQL instance.

## 3. Build the Podman Container

```bash
py -m podman_compose up -d    
```

## 4. Create Database Objects

Run:

```bash
python setup.py
```

This script creates:

* Required schemas
* Tables
* Constraints

## 5. Load Initial Data

Import all source CSV files located in `banking_data` folder into the:

```text
staging schema in oltp_db
```

schema of the PostgreSQL database.

## 6. Load Lookup Data

Import lookup datasets located in:

```text
banking_data/lookup_data
```

into their corresponding lookup tables.
## 7. Configure Airflow PostgreSQL Connection

Before triggering the DAG, create a PostgreSQL connection in Airflow.

### Steps

1. Open Airflow UI
2. Navigate to:

```text
Admin → Connections
```

3. Click **+ Add Connection**

4. Enter the following details:

| Field | Value |
|---------|---------|
| Connection Id | olap_postgres |
| Connection Type | Postgres |
| Host | olap_db |
| Database | fraud_olap |
| Login | postgres |
| Password | your_password |
| Port | 5432 |

5. Click **Save**

The fraud detection DAG uses this connection to read and write data across the staging, curated, and aggregated layers.

### Verify Connection

Navigate to:

```text
Admin → Connections
```

Locate:

```text
olap_postgres
```

## 8. Run the Airflow Pipeline

Start Airflow and trigger the fraud detection DAG.

### Airflow Credentials

| Username | Password |
|----------|----------|
| admin | admin |

The DAG will:

* Load staging data
* Populate curated tables
* Generate feature ready datasets

## 9. Train the Fraud Detection Model

Execute:

```bash
python xgboost_training.py
```

The trained model will be generated in:

```text
ml/models/
```

## 10. Configure Groq API Key

Create the following directory:

```text
.streamlit/
```

Inside it create:

```text
.streamlit/secrets.toml
```

Add your API key:

```toml
GROQ_API_KEY = "your-groq-api-key"
```

## 11. Run Rules Based Fraud Detection Function
Run `rules_engine_fraud_dashboard.sql`

## 12. Launch Apache Superset

### Superset Credentials

| Username | Password |
|----------|----------|
| admin | admin |

## 13. Import Dashboards

Navigate to Superset and import the dashboards located in:

```text
superset_dashboard/
```

While importing:

* Select the target database
* Enter your PostgreSQL credentials

## 14. Run the Streamlit Application

```bash
python -m streamlit run app.py
```

The application will launch locally in your browser.

---

# Application Features

## Fraud Detection

Provides real time fraud analysis using:

* Blacklist checks
* VIP handling
* Feature engineering
* XGBoost prediction model
* Risk scoring

## VIP Management

Supports:

* VIP customer onboarding
* VIP status updates
* VIP customer monitoring

## Blacklist Management

Supports:

* Add customer to blacklist
* Remove customer from blacklist
* Blacklist validation

## AI Transaction Summary

Generates natural language explanations for:

* Fraud decisions
* Risk factors
* Transaction characteristics

using Groq LLMs.

## AI Chatbot

Allows users to:

* Query fraud data
* Understand model outputs
* Explore transaction insights

using natural language.

---

# Data Flow

```text
CSV Files
    ↓
Staging Schema
    ↓
Airflow ELT Pipeline
    ↓
XGBoost Model
    ↓
Fraud Prediction
    ↓
Streamlit Dashboard
    ↓
AI Summary Generation
```

---

# Login Credentials

## Airflow

```text
Username: admin
Password: admin
```

## Superset

```text
Username: admin
Password: admin
```

---

# Running the Complete System

```bash
# Install dependencies
pip install -r requirements.txt

# Build container
py -m podman_compose up -d     .

# Create schemas and tables
python setup.py

# Train model
python xgboost_training.py

# Run Streamlit
python -m streamlit run app.py
```

---

# Author

Real Time Banking Fraud Detection Platform

Built using PostgreSQL, Airflow, XGBoost, Groq, Streamlit, and Superset.