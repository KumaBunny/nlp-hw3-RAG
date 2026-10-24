import os
import sqlite3
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

'''
[faiss.IndexFlatL2]
使用歐氏距離

[faiss.IndexFlatIP]
IP = Inner Product，
測試使用 Inner Product 來比較 features 資料
同時進行 feature normalization
等同於 cosine similarity
'''

# 模型名稱
model_name = 'BAAI/bge-m3'

# 索引存放路徑
index_path = './vector.index'

# 讀取 model
encoder = SentenceTransformer(model_name)

# 讀取資料庫中的新聞標題與內容，並將其組合成文件
docs = []
doc_ids = []
conn = sqlite3.connect('./news.db')
cursor = conn.cursor()
try:
    # 查詢資料庫中的新聞標題與內容
    rows = cursor.execute(
        "SELECT id, summary FROM news "
        "WHERE summary IS NOT NULL AND TRIM(summary) != ''"
    )

    for news_id, summary in rows:
        docs.append(summary)
        doc_ids.append(news_id)
finally:
    conn.close()

# 將 doc_ids 轉成 numpy array，並指定資料型態為 int64
doc_ids = np.array(doc_ids, dtype='int64')

# 將所有句子轉換成向量，同時計算轉向量時間
embeddings = encoder.encode(
    docs, 
    batch_size=8,
    show_progress_bar=True,
    normalize_embeddings=True
)

# 索引預設變數
index = None

# 每次重新建立索引，避免重複加入新聞
dims = embeddings.shape[1]
index = faiss.IndexFlatIP(dims)
index = faiss.IndexIDMap(index)

# 加入 doc id 到 對應的 vector
print(embeddings.shape)
print(len(doc_ids))
index.add_with_ids(embeddings, doc_ids) # 加入 向量 與 文件ID
# index.add(embeddings) # 僅加入向量

# 儲存索引
faiss.write_index(index, index_path)
print("索引已儲存到", index_path)