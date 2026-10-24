
import json
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen

import faiss
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent
MODEL_NAME = "BAAI/bge-m3"
OLLAMA_MODEL = "qwen2.5:0.5b"

print("正在載入 Embedding 模型...")
encoder = SentenceTransformer(MODEL_NAME)
index = faiss.read_index(str(BASE_DIR / "vector.index"))


def retrieve_news(question, k=3):
    """將問題向量化，檢索最相關的新聞。"""
    vector = encoder.encode(
        [question],
        normalize_embeddings=True
    )

    scores, ids = index.search(vector, k)

    results = []
    with sqlite3.connect(
        f"file:{BASE_DIR / 'news.db'}?mode=ro",
        uri=True
    ) as conn:
        for news_id, score in zip(ids[0], scores[0]):
            if news_id == -1:
                continue

            row = conn.execute(
                """
                SELECT title, link, summary, date, created_at
                FROM news
                WHERE id = ?
                """,
                (int(news_id),)
            ).fetchone()

            if row:
                results.append({
                    "title": row[0],
                    "link": row[1],
                    "summary": row[2],
                    "date": row[3],
                    "created_at": row[4],
                    "score": float(score),
                })

    return results


def ask_ollama(question, news):
    """將檢索結果交給 Ollama 產生回答。"""
    context = "\n\n".join(
        f"新聞{i}：{item['title']}\n"
        f"摘要：{item['summary']}"
        for i, item in enumerate(news, start=1)
    )

    prompt = f"""
你是台灣繁體中文健康新聞諮詢小幫手。
請只根據以下新聞摘要回答問題。
如果資料不足，請明確表示無法從新聞確認。
不要自行編造醫療資訊、診斷或治療建議。
請使用繁體中文，回答簡潔清楚。

參考新聞：
{context}

使用者問題：{question}

回答：
"""

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 300,
            "repeat_penalty": 1.2
        }
    }).encode("utf-8")

    request = Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urlopen(request, timeout=180) as response:
        result = json.load(response)

    return result["response"]


def ask_ollama_chat(question, news, history=None):
    """使用 Ollama Chat API 進行多輪 RAG 問答。"""

    history = history or []

    # 將本輪檢索到的新聞整理成參考資料
    context = "\n\n".join(
        f"新聞{i}\n"
        f"標題：{item['title']}\n"
        f"摘要：{item['summary']}"
        for i, item in enumerate(news, start=1)
    )

    system_prompt = (
        "你是台灣繁體中文健康新聞諮詢小幫手。\n"
        "請根據提供的新聞摘要回答目前的問題。\n"
        "可以參考歷史對話理解代名詞與追問。\n"
        "不要將歷史回答當成已驗證的醫療事實。\n"
        "如果新聞資料不足，請明確說明資料不足。\n"
        "不要編造醫療資訊，也不要聲稱 AI 可以取代醫師。\n"
        "請使用繁體中文，回答一至三句，不要重複問題。\n\n"
        f"本輪參考新聞：\n{context}"
    )

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # 只保留最近三輪問答，避免小模型負擔過重
    for message in history[-6:]:
        if message["role"] in ("user", "assistant"):
            messages.append({
                "role": message["role"],
                "content": message["content"]
            })

    messages.append({
        "role": "user",
        "content": question
    })

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 300,
            "repeat_penalty": 1.2
        }
    }).encode("utf-8")

    request = Request(
        "http://127.0.0.1:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urlopen(request, timeout=180) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    question = input("請輸入健康新聞問題：").strip()

    if not question:
        print("請輸入問題。")
        return

    news = retrieve_news(question)

    if not news:
        print("找不到相關新聞。")
        return

    print("\n正在請 Ollama 產生回答...")
    answer = ask_ollama(question, news)

    print("\n=== RAG 回答 ===")
    print(answer)

    print("\n=== 參考新聞 ===")
    for item in news:
        print(f"- 新聞標題：{item['title']}")
        print(f"  新聞連結：{item['link']}")
        print(f"  文章新增時間：{item['created_at']}")


if __name__ == "__main__":
    main()
