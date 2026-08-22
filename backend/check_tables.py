"""
查询数据库中的所有表
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

# 查询所有表
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name
""")

rows = cur.fetchall()

print("=" * 80)
print("数据库表:")
print("=" * 80)

for row in rows:
    print(f"  {row[0]}")

cur.close()
conn.close()
