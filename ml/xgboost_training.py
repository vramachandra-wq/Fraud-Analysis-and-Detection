import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from ml.feature_engineering import FraudFeatureEngineer
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, classification_report, confusion_matrix, roc_curve, precision_recall_curve
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

# Create baseline directories for outputs if they don't exist
os.makedirs(r'ml\images', exist_ok=True)
os.makedirs(r'ml\models', exist_ok=True)

# ==========================================
# 1. LOAD DATA
# ==========================================
print('Reading the Data...')
df = pd.read_csv(r"banking_data\transactions.csv")
print("Read CSV Complete")

# Select Features
features = [
    'account_id',
    'device_id',
    'location_id',
    'transaction_type',
    'channel',
    'amount',
    'currency',
    'transaction_status',
    'merchant_category',
    'transaction_date',
    'transaction_time',
    'processing_time_ms'
]

TARGET = 'is_fraud'
df = df[features + [TARGET]]

# ==========================================
# 2. HANDLING MISSING VALUES
# ==========================================
print('\nHandling Missing Values...')
categorical_cols = [
    'account_id',
    'device_id',
    'location_id',
    'transaction_type',
    'channel',
    'currency',
    'transaction_status',
    'merchant_category'
]

numerical_cols = [
    'amount',
    'processing_time_ms'
]

for col in categorical_cols:
    df[col] = df[col].fillna('UNKNOWN')

for col in numerical_cols:
    df[col] = df[col].fillna(df[col].median())
print('Handled Missing Values')


# ==========================================
# 3. FEATURE ENGINEERING TRANSFORMER
# ==========================================
# class FraudFeatureEngineer(BaseEstimator, TransformerMixin):

#     def fit(self, X, y=None):
#         X = X.copy()

#         # Datetime conversion safely inside fit
#         X['transaction_date'] = pd.to_datetime(X['transaction_date'], errors='coerce')
#         X['transaction_time'] = pd.to_datetime(X['transaction_time'], format='%H:%M:%S', errors='coerce')

#         # High amount threshold
#         self.high_amount_threshold_ = X['amount'].quantile(0.95)

#         # Customer statistics mappings
#         self.customer_avg_ = X.groupby('account_id')['amount'].mean().to_dict()
#         self.customer_std_ = X.groupby('account_id')['amount'].std().fillna(1).replace(0, 1).to_dict()
        
#         # Device and Location counts profiles
#         self.device_count_ = X.groupby('device_id')['amount'].count().to_dict()
#         self.location_count_ = X.groupby('location_id')['amount'].count().to_dict()

#         # VELOCITY LOOKUPS: Calculate historic daily transaction behavior per account across full data
#         daily_counts = X.groupby(['account_id', 'transaction_date']).size().reset_index(name='count')
#         self.account_avg_daily_count_ = daily_counts.groupby('account_id')['count'].mean().to_dict()
        
#         daily_amounts = X.groupby(['account_id', 'transaction_date'])['amount'].sum().reset_index(name='daily_sum')
#         self.account_avg_daily_amount_ = daily_amounts.groupby('account_id')['daily_sum'].mean().to_dict()

#         # Global fallbacks for completely new production accounts/data
#         self.global_customer_avg_ = X['amount'].mean()
#         self.global_daily_count_ = daily_counts['count'].mean()
#         self.global_daily_amount_ = daily_amounts['daily_sum'].mean()

#         return self

#     def transform(self, X):
#         X = X.copy()

#         # Datetime conversion
#         X['transaction_date'] = pd.to_datetime(X['transaction_date'], errors='coerce')
#         X['transaction_time'] = pd.to_datetime(X['transaction_time'], format='%H:%M:%S', errors='coerce')

#         # Date Features
#         X['transaction_day'] = X['transaction_date'].dt.day
#         X['transaction_month'] = X['transaction_date'].dt.month
#         X['transaction_weekday'] = X['transaction_date'].dt.weekday
#         X['transaction_hour'] = X['transaction_time'].dt.hour

#         # Night Transaction Flag
#         X['is_night_transaction'] = ((X['transaction_hour'] >= 23) | (X['transaction_hour'] <= 5)).astype(np.uint8)

#         # Weekend Flag
#         X['is_weekend'] = (X['transaction_weekday'] >= 5).astype(np.uint8)

#         # Map Profiles securely using fit statistics (Production safe!)
#         customer_avg = X['account_id'].map(self.customer_avg_).fillna(self.global_customer_avg_)
#         customer_std = X['account_id'].map(self.customer_std_).fillna(1)
#         customer_std = np.maximum(customer_std, 1)

#         X['amount_vs_customer_avg'] = X['amount'] / (customer_avg + 1)
#         X['customer_amount_zscore'] = (X['amount'] - customer_avg) / customer_std

#         # Map Historical Velocities (Safe for single-row pipeline transforms)
#         X['historical_avg_daily_count'] = X['account_id'].map(self.account_avg_daily_count_).fillna(self.global_daily_count_)
#         X['historical_avg_daily_amount'] = X['account_id'].map(self.account_avg_daily_amount_).fillna(self.global_daily_amount_)

#         # Device and Location historical counts profiles
#         X['device_transaction_count'] = X['device_id'].map(self.device_count_).fillna(0)
#         X['location_transaction_count'] = X['location_id'].map(self.location_count_).fillna(0)

#         # Drop Raw Columns
#         X = X.drop(columns=[
#             'account_id',
#             'device_id',
#             'location_id',
#             'transaction_date',
#             'transaction_time'
#         ])

#         return X


# Preprocessor Columns Setup
final_categorical_cols = [
    'transaction_type',
    'channel',
    'currency',
    'transaction_status',
    'merchant_category'
]

final_numerical_cols = [
    'amount',
    'processing_time_ms',
    'transaction_day',
    'transaction_month',
    'transaction_weekday',
    'transaction_hour',
    'is_night_transaction',
    'is_weekend',
    'amount_vs_customer_avg',
    'customer_amount_zscore',
    'historical_avg_daily_count',
    'historical_avg_daily_amount',
    'device_transaction_count',
    'location_transaction_count'
]

# Preprocessor Step
preprocessor = ColumnTransformer(
    transformers=[
        ('cat', OneHotEncoder(handle_unknown='ignore'), final_categorical_cols),
        ('num', 'passthrough', final_numerical_cols)
    ]
)

# Extract full datasets
X = df[features]
y = df[TARGET]


# ==========================================
# 4. TRAINING PRODUCTION PIPELINE (ON 100% DATA)
# ==========================================
print('\n=== TRAINING PRODUCTION PIPELINE ON 100% DATA ===')

# Calculate exact imbalance ratio across the entire dataset
fraud_count = y.sum()
non_fraud_count = len(y) - fraud_count
scale_pos_weight = non_fraud_count / fraud_count

print(f"Total dataset volume: {len(X)} rows | Total Fraud instances: {fraud_count}")
print(f"Scale Pos Weight adjusted to: {scale_pos_weight:.4f}")

# Define the production pipeline instance
production_pipeline = Pipeline(
    steps=[
        ('feature_engineering', FraudFeatureEngineer()),  # Maps lookups over 100% of records
        ('preprocessing', preprocessor),
        ('model',
            XGBClassifier(
                n_estimators=400,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                objective='binary:logistic',
                eval_metric='auc',
                scale_pos_weight=scale_pos_weight,
                random_state=42,
                n_jobs=-1
            )
        )
    ]
)

print('Fitting Production Model on whole dataset...')
production_pipeline.fit(X, y)
print('Production Model Fit Complete!')


# ==========================================
# 5. PREDICT PROBABILITIES & RUN BASELINE METRICS
# ==========================================
print('\nPredicting Probabilities on Full Dataset...')
train_prob = production_pipeline.predict_proba(X)[:, 1]

# Threshold Tuning Loop
thresholds = np.arange(0.1, 1.0, 0.05)
best_threshold = 0.5
best_f1 = 0
print("\n========== Threshold Tuning (On Full Dataset) ==========\n")
for threshold in thresholds:
    preds = (train_prob >= threshold).astype(int)
    f1 = f1_score(y, preds, zero_division=0)
    print(f"Threshold: {threshold:.2f} | F1 Score: {f1:.4f}")
    if f1 > best_f1:
        best_f1 = f1
        best_threshold = threshold
print(f"\nBest Automated Threshold : {best_threshold:.2f}")
print(f"Best Dataset F1 Score    : {best_f1:.4f}")

# Threshold vs Precision / Recall Plot
precision_scores = []
recall_scores = []
for threshold in thresholds:
    preds = (train_prob >= threshold).astype(int)
    precision_scores.append(precision_score(y, preds, zero_division=0))
    recall_scores.append(recall_score(y, preds, zero_division=0))

plt.figure(figsize=(10, 6))
plt.plot(thresholds, precision_scores, marker='o', label='Precision')
plt.plot(thresholds, recall_scores, marker='o', label='Recall')
plt.xlabel('Threshold')
plt.ylabel('Score')
plt.title('Full Dataset: Threshold vs Precision and Recall')
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(r'ml\images\xgboost_threshold_precision_recall.jpeg', dpi=300, bbox_inches='tight')
plt.close()
print('\nSaved Baseline Threshold Precision Recall Plot')


# ==========================================
# 6. EXPORT PRODUCTION PIPELINE
# ==========================================
production_model_path = r"ml\models\xgboost_fraud_detection_production.pkl"
joblib.dump(production_pipeline, production_model_path)
print(f"\nComplete pipeline successfully trained and saved to: {production_model_path}")


# ==========================================
# 7. CUSTOM OPERATIONAL THRESHOLD EVALUATION (0.3 THRESHOLD)
# ==========================================
CUSTOM_THRESHOLD = 0.3
custom_folder_path = r'ml\images\0.3_threshold'
os.makedirs(custom_folder_path, exist_ok=True)

print(f'\n=== PHASE 3: APPLYING CUSTOM OPERATIONAL THRESHOLD ({CUSTOM_THRESHOLD}) ===')

# Generate predictions strictly mapped to the 0.3 threshold rule
y_pred_custom = (train_prob >= CUSTOM_THRESHOLD).astype(int)

# Evaluation Metrics Output
print(f"\n========== Evaluation Metrics (Custom Threshold = {CUSTOM_THRESHOLD}) ==========\n")
print(f"Accuracy  : {accuracy_score(y, y_pred_custom):.4f}")
print(f"Precision : {precision_score(y, y_pred_custom):.4f}")
print(f"Recall    : {recall_score(y, y_pred_custom):.4f}")
print(f"F1 Score  : {f1_score(y, y_pred_custom):.4f}")
print(f"ROC AUC   : {roc_auc_score(y, train_prob):.4f}")

# Classification Report
print("\n========== Classification Report ==========\n")
print(classification_report(y, y_pred_custom))

# Plot 1: Custom Confusion Matrix
cm_custom = confusion_matrix(y, y_pred_custom)
plt.figure(figsize=(7, 6))
sns.heatmap(
    cm_custom, annot=True, fmt='d', cmap='Oranges',
    xticklabels=['Not Fraud', 'Fraud'], yticklabels=['Not Fraud', 'Fraud']
)
plt.title(f'Confusion Matrix (Threshold = {CUSTOM_THRESHOLD})')
plt.xlabel('Predicted')
plt.ylabel('Actual')
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_confusion_matrix.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom Confusion Matrix')

# Plot 2: ROC Curve (Highlighting the 0.3 operation marker point)
fpr, tpr, thresholds_roc = roc_curve(y, train_prob)
# Find closest true/false positive rate coordinates on the curve for 0.3
idx = np.argmin(np.abs(thresholds_roc - CUSTOM_THRESHOLD))

plt.figure(figsize=(8, 6))
plt.plot(fpr, tpr, color='darkorange', label=f"AUC = {roc_auc_score(y, train_prob):.4f}")
plt.plot([0, 1], [0, 1], color='navy', linestyle='--')
plt.scatter(fpr[idx], tpr[idx], color='red', s=100, zorder=5, label=f'Operating Point ({CUSTOM_THRESHOLD})')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC AUC Curve (Full Dataset)')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_roc_auc_curve.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom ROC Curve')

# Plot 3: Precision-Recall Curve (Highlighting the 0.3 operation marker point)
precision, recall, thresholds_pr = precision_recall_curve(y, train_prob)
idx_pr = np.argmin(np.abs(thresholds_pr - CUSTOM_THRESHOLD))

plt.figure(figsize=(8, 6))
plt.plot(recall, precision, color='purple', label='PR Curve')
plt.scatter(recall[idx_pr], precision[idx_pr], color='red', s=100, zorder=5, label=f'Operating Point ({CUSTOM_THRESHOLD})')
plt.xlabel('Recall')
plt.ylabel('Precision')
plt.title('Precision Recall Curve (Full Dataset)')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_precision_recall_curve.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom Precision Recall Curve')

# Plot 4: Feature Importance Graph
model = production_pipeline.named_steps['model']
feature_names = production_pipeline.named_steps['preprocessing'].get_feature_names_out()
importance_df = pd.DataFrame({'Feature': feature_names, 'Importance': model.feature_importances_})
importance_df = importance_df.sort_values(by='Importance', ascending=False)

top_features = importance_df.head(15)
plt.figure(figsize=(10, 7))
plt.barh(top_features['Feature'], top_features['Importance'], color='teal')
plt.xlabel('Importance')
plt.ylabel('Feature')
plt.title('Top Feature Importance')
plt.gca().invert_yaxis()
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_feature_importance.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom Feature Importance Image')

print(f"\nAll operational evaluation charts updated and saved cleanly inside: '{custom_folder_path}'")

# ==========================================
# 7. CUSTOM OPERATIONAL THRESHOLD EVALUATION (0.25 THRESHOLD)
# ==========================================
CUSTOM_THRESHOLD = 0.25
custom_folder_path = r'ml\images\0.25_threshold'
os.makedirs(custom_folder_path, exist_ok=True)

print(f'\n=== PHASE 3: APPLYING CUSTOM OPERATIONAL THRESHOLD ({CUSTOM_THRESHOLD}) ===')

# Generate predictions strictly mapped to the 0.25 threshold rule
y_pred_custom = (train_prob >= CUSTOM_THRESHOLD).astype(int)

# Evaluation Metrics Output
print(f"\n========== Evaluation Metrics (Custom Threshold = {CUSTOM_THRESHOLD}) ==========\n")
print(f"Accuracy  : {accuracy_score(y, y_pred_custom):.4f}")
print(f"Precision : {precision_score(y, y_pred_custom):.4f}")
print(f"Recall    : {recall_score(y, y_pred_custom):.4f}")
print(f"F1 Score  : {f1_score(y, y_pred_custom):.4f}")
print(f"ROC AUC   : {roc_auc_score(y, train_prob):.4f}")

# Classification Report
print("\n========== Classification Report ==========\n")
print(classification_report(y, y_pred_custom))

# Plot 1: Custom Confusion Matrix
cm_custom = confusion_matrix(y, y_pred_custom)
plt.figure(figsize=(7, 6))
sns.heatmap(
    cm_custom, annot=True, fmt='d', cmap='Oranges',
    xticklabels=['Not Fraud', 'Fraud'], yticklabels=['Not Fraud', 'Fraud']
)
plt.title(f'Confusion Matrix (Threshold = {CUSTOM_THRESHOLD})')
plt.xlabel('Predicted')
plt.ylabel('Actual')
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_confusion_matrix.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom Confusion Matrix')

# Plot 2: ROC Curve (Highlighting the 0.25 operation marker point)
fpr, tpr, thresholds_roc = roc_curve(y, train_prob)
# Find closest true/false positive rate coordinates on the curve for 0.25
idx = np.argmin(np.abs(thresholds_roc - CUSTOM_THRESHOLD))

plt.figure(figsize=(8, 6))
plt.plot(fpr, tpr, color='darkorange', label=f"AUC = {roc_auc_score(y, train_prob):.4f}")
plt.plot([0, 1], [0, 1], color='navy', linestyle='--')
plt.scatter(fpr[idx], tpr[idx], color='red', s=100, zorder=5, label=f'Operating Point ({CUSTOM_THRESHOLD})')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC AUC Curve (Full Dataset)')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_roc_auc_curve.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom ROC Curve')

# Plot 3: Precision-Recall Curve (Highlighting the 0.25 operation marker point)
precision, recall, thresholds_pr = precision_recall_curve(y, train_prob)
idx_pr = np.argmin(np.abs(thresholds_pr - CUSTOM_THRESHOLD))

plt.figure(figsize=(8, 6))
plt.plot(recall, precision, color='purple', label='PR Curve')
plt.scatter(recall[idx_pr], precision[idx_pr], color='red', s=100, zorder=5, label=f'Operating Point ({CUSTOM_THRESHOLD})')
plt.xlabel('Recall')
plt.ylabel('Precision')
plt.title('Precision Recall Curve (Full Dataset)')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_precision_recall_curve.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom Precision Recall Curve')

# Plot 4: Feature Importance Graph
model = production_pipeline.named_steps['model']
feature_names = production_pipeline.named_steps['preprocessing'].get_feature_names_out()
importance_df = pd.DataFrame({'Feature': feature_names, 'Importance': model.feature_importances_})
importance_df = importance_df.sort_values(by='Importance', ascending=False)

top_features = importance_df.head(15)
plt.figure(figsize=(10, 7))
plt.barh(top_features['Feature'], top_features['Importance'], color='teal')
plt.xlabel('Importance')
plt.ylabel('Feature')
plt.title('Top Feature Importance')
plt.gca().invert_yaxis()
plt.tight_layout()
plt.savefig(os.path.join(custom_folder_path, 'xgboost_feature_importance.jpeg'), dpi=300, bbox_inches='tight')
plt.close()
print('Saved Custom Feature Importance Image')

print(f"\nAll operational evaluation charts updated and saved cleanly inside: '{custom_folder_path}'")