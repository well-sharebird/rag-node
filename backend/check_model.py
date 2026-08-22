"""
查询数据库中的模型配置
"""
import psycopg2
import json

# 数据库配置
conn = psycopg2.connect(
    host="100.4.14.19",
    port=5432,
    user="postgres",
    password="postgres123",
    database="rag_db"
)

cur = conn.cursor()

# 查询模型配置
cur.execute("""
    SELECT id, name, model_id, model_type, provider, is_enabled, is_default
    FROM model_configs 
    WHERE model_id LIKE '%qwen%' OR model_type LIKE '%qwen%'
    LIMIT 5
""")

rows = cur.fetchall()

print("=" * 80)
print("Qwen 模型配置:")
print("=" * 80)

col_names = [desc[0] for desc in cur.description]

for row in rows:
    print()
    for i, val in enumerate(row):
        print(f"  {col_names[i]:20s}: {val}")

cur.close()
conn.close()
