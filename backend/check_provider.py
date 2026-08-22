"""
查询数据库中的 model_providers 配置
"""
import psycopg2

# 数据库配置
conn = psycopg2.connect(
    host="100.4.14.19",
    port=5432,
    user="postgres",
    password="postgres123",
    database="rag_db"
)

cur = conn.cursor()

# 查询 provider 配置
cur.execute("""
    SELECT * FROM model_providers
    LIMIT 10
""")

rows = cur.fetchall()

print("=" * 80)
print("Provider 配置:")
print("=" * 80)

col_names = [desc[0] for desc in cur.description]
print("列名:", col_names)
print()

for row in rows:
    print("-" * 80)
    for i, val in enumerate(row):
        if val and 'key' in col_names[i].lower() and len(str(val)) > 10:
            print(f"  {col_names[i]:25s}: {str(val)[:10]}...")
        else:
            print(f"  {col_names[i]:25s}: {val}")

cur.close()
conn.close()
