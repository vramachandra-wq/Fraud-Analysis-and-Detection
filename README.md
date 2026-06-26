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
FRAUD-ANALYSIS-AND-DETECTION/
│
├── .streamlit/
│   └── secrets.toml                        ← Streamlit secrets and credentials
│
├── .venv/                                  ← Python virtual environment
│
├── ai/
│   ├── chatbot/
│   │   ├── components.py                   ← Chatbot UI components
│   │   ├── config.py                       ← Chatbot configuration
│   │   └── pipeline.py                     ← Chatbot processing pipeline
│   │
│   ├── __init__.py                         ← AI package initialization
│   ├── groq_client.py                      ← Groq LLM client setup
│   └── summarizer.py                       ← Transaction summarization logic
│
├── airflow/
│   ├── config/                             ← Airflow configuration files
│   ├── dags/                               ← Airflow workflows and jobs
│   └── plugins/                            ← Custom Airflow plugins
│
├── auth/
│   ├── db.py                               ← Authentication database operations
│   └── users.py                            ← User authentication logic
│
├── banking_data/
│   └── lookup_data/                        ← Source lookup datasets
│
├── config/
│   ├── __init__.py                         ← Configuration package
│   └── settings.py                         ← Application settings
│
├── database/
│   ├── __init__.py                         ← Database package
│   ├── account_repository.py               ← Account database operations
│   ├── blacklist_repository.py             ← Blacklist database operations
│   ├── connection.py                       ← Database connection manager
│   ├── transaction_repository.py           ← Transaction database operations
│   └── vip_repository.py                   ← VIP database operations
│
├── fastapi_service/
│   ├── fastapi_cdc.log                     ← CDC service logs
│   ├── initial_load.log                    ← Initial load logs
│   ├── initial_load.py                     ← Initial data loading script
│   ├── main.py                             ← FastAPI application entry point
│   └── reload_transactions.py              ← Transaction reload utility
│
├── lookup_tables_scripts/
│   ├── blacklisted_accounts.py             ← Generate blacklist accounts
│   ├── valid_accounts.py                   ← Generate valid accounts
│   └── vip_accounts.py                     ← Generate VIP accounts
│
├── ml/
│   ├── images/                             ← Model images and plots
│   ├── models/                             ← Saved ML models
│   ├── __init__.py                         ← ML package
│   ├── feature_engineering.py              ← Feature creation logic
│   ├── model_loader.py                     ← Load trained models
│   ├── prediction_service.py               ← Fraud prediction service
│   └── xgboost_training.py                 ← XGBoost model training
│
├── services/
│   ├── __init__.py                         ← Services package
│   ├── blacklist_service.py                ← Blacklist business logic
│   ├── fraud_service.py                    ← Fraud detection logic
│   └── vip_service.py                      ← VIP account business logic
│
├── sql/
│   ├── schema_setup/
│   │   ├── olap/
│   │   │   ├── aggregated.sql              ← Aggregated layer schema
│   │   │   ├── curated.sql                 ← Curated layer schema
│   │   │   ├── landing.sql                 ← Landing layer schema
│   │   │   └── logging.sql                 ← Logging schema
│   │   │
│   │   └── oltp/
│   │       └── ddl.sql                     ← Transactional schema DDL
│   │
│   ├── ai_chatbot_logs.sql                 ← Chatbot logging tables
│   ├── create_olap_airflow_db.sql          ← OLAP and Airflow DB setup
│   ├── lookup_table_schema_creation.sql    ← Lookup table creation
│   ├── ml_transaction_logs.sql             ← ML prediction logs
│   ├── rules_based_fraud_dashboard.sql     ← Dashboard queries
│   ├── rules_engine_function.sql           ← Fraud rule engine functions
│   ├── user_credentials_creation.sql       ← User credentials tables
│   └── user_sessions_table_creation.sql    ← Session tracking tables
│
├── superset_dashboards/
│   ├── dashboard_export_20260525T051749.zip ← Dashboard export
│   ├── dashboard_export_20260525T051825.zip ← Dashboard export
│   ├── dashboard_export_20260525T051832.zip ← Dashboard export
│   └── dashboard_export_20260611T131022.zip ← Dashboard export
│
├── ui/
│   ├── __init__.py                         ← UI package
│   ├── admin_control_panel.py              ← Admin dashboard
│   ├── session_state.py                    ← Streamlit session state
│   ├── dialogs.py                          ← Dialog popups
│   ├── transaction_tab.py                  ← Fraud Detection tab
│   ├── vip_management_tab.py               ← VIP Management tab
│   └── chatbot_tab.py                      ← AI Chatbot tab
│
├── utils/
│   ├── __init__.py                         ← Utility package
│   └── constants.py                        ← Application constants
│
├── .gitattributes                          ← Git file handling rules
├── .gitignore                              ← Ignored files and folders
├── app.py                                  ← Main Streamlit application
├── connector.json                          ← Debezium Connector configuration
├── initial_load.log                        ← Initial Data Load logs
├── podman-compose.yml                      ← Container orchestration
├── README.md                               ← Project documentation
├── requirements.txt                        ← Python dependencies
└── setup.py                                ← Initial Setup script
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
[Files Link](https://azirotechnologies-my.sharepoint.com/:f:/g/personal/nmuralidhara_aziro_com/IgChLYluu48LQ5bNt3lecozvAXGYvkt-yFhaRT6NKncU6ss?e=BGTrVD)

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

Start Airflow and trigger the fraud detection DAG. If the first run fails, re run the pipeline.

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

The trained model will be stored in:

```text
ml/models/
```
The trained model plots and graphs will be stored in:

```text
ml/images/
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
This step takes appromimately 8-10 mins.  

Run `rules_engine_fraud_dashboard.sql` inside `pgadmin`

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

The application will launch locally in your browser on `localhost:8051`.

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
* Explore transaction insights using natural language.

## Administrative Control Panel

Provides administrative capabilities including:

* User management
* Session management
* Administrative controls
* User access management

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