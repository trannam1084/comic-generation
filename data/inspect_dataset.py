import pandas as pd

DATA_PATH = "data/raw/full_story.csv"

df = pd.read_csv(DATA_PATH)

print("===== DATASET INFORMATION =====")
print("Number of rows:", len(df))
print("Columns:", df.columns.tolist())

print("\n===== MISSING VALUES =====")
print(df.isnull().sum())

print("\n===== DUPLICATE URL =====")
print(df["url"].duplicated().sum())

print("\n===== DUPLICATE TITLE =====")
print(df["title"].duplicated().sum())

print("\n===== CONTENT LENGTH =====")
df["content_length"] = df["content"].fillna("").str.len()

print(df["content_length"].describe())

print("\n===== SAMPLE TITLES =====")
for title in df["title"].head(20):
    print("-", title)