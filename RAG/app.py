
import streamlit as st
from rag_chat import retrieve_news, ask_ollama, ask_ollama_chat

st.set_page_config(
    page_title="健康新聞 RAG 小幫手",
    page_icon="🩺"
)

st.title("🩺 健康新聞 RAG 小幫手")
st.caption("使用 248 篇健康新聞、BGE-M3、FAISS 與 Ollama")
st.info("本系統僅整理健康新聞資訊，不提供個人醫療診斷。")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_news" not in st.session_state:
    st.session_state.last_news = []

# Checkbox：決定後續問題是否重新檢索新聞
search_each_turn = st.checkbox(
    "每輪對話重新檢索新聞",
    value=True,
    help="勾選：每輪重新檢索；取消：沿用上次新聞"
)

def show_sources(news):
    if not news:
        return

    st.markdown("**參考新聞：**")
    for item in news:
        st.markdown(
            f"- [{item['title']}]({item['link']})  \n"
            f"  新聞發布日期：{item['date']}  \n"
            f"  文章新增時間：{item['created_at']}"
        )

# 顯示歷史對話
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message["role"] == "assistant":
            show_sources(message.get("news", []))


# 對話總結：每個問題獨立整理，避免小模型跳針
if st.button("整理剛才詢問的重點"):
    messages = st.session_state.messages

    # 取得使用者提問與其對應的回答
    pairs = []
    for i, message in enumerate(messages):
        if message["role"] != "user":
            continue

        if i + 1 < len(messages):
            reply = messages[i + 1]
            if reply["role"] == "assistant" and not reply["content"].startswith(
                "### 對話重點整理"
            ):
                pairs.append((message["content"], reply["content"]))

    if len(pairs) < 2:
        st.warning("請先完成至少兩輪問答。")
    else:
        summaries = []

        with st.spinner("正在整理對話重點..."):
            try:
                for number, (user_question, assistant_answer) in enumerate(
                    pairs[-2:], start=1
                ):
                    prompt = (
                        "請把以下健康新聞問答濃縮成一句繁體中文。\n"
                        "只根據原回答，不要增加新資訊或數字。\n"
                        "不要列點，不要重複問題。\n\n"
                        f"問題：{user_question}\n"
                        f"原回答：{assistant_answer[:500]}\n\n"
                        "一句話重點："
                    )

                    result = ask_ollama(prompt, [])

                    # 避免把過長或重複的內容直接展示
                    first_line = result.strip().splitlines()[0].strip()

                    if not first_line or len(first_line) > 150:
                        first_line = assistant_answer[:150].strip() + "…"

                    summaries.append(
                        f"**問題{number}：{user_question}**\n\n"
                        f"{first_line}"
                    )

                summary = (
                    "### 對話重點整理\n\n"
                    + "\n\n".join(summaries)
                )

                # 合併最近兩輪使用過的新聞來源，避免只列最後一輪
                sources = []
                seen_links = set()

                for message in messages:
                    if message["role"] != "assistant":
                        continue

                    for item in message.get("news", []):
                        if item["link"] not in seen_links:
                            seen_links.add(item["link"])
                            sources.append(item)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": summary,
                    "news": sources
                })

                st.rerun()

            except Exception as e:
                st.error(f"總結失敗：{e}")

question = st.chat_input("請輸入健康新聞相關問題")

if question:
    st.session_state.messages.append({
        "role": "user",
        "content": question
    })

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("正在檢索新聞並產生回答..."):
            try:
                if search_each_turn or not st.session_state.last_news:
                    news = retrieve_news(question)
                else:
                    news = st.session_state.last_news
              
                # 取得歷史對話，排除目前剛加入的使用者問題
                history = st.session_state.messages[:-1]

                # 排除「對話重點整理」，避免干擾後續問答
                history = [
                    {
                        "role": message["role"],
                        "content": message["content"]
                    }
                    for message in history
                    if not (
                        message["role"] == "assistant"
                        and message["content"].startswith("### 對話重點整理")
                    )
                ]

                # 使用 Ollama Chat API 進行多輪問答
                answer = ask_ollama_chat(
                    question=question,
                    news=news,
                    history=history
                )

                st.write(answer)
                show_sources(news)

                st.session_state.last_news = news
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "news": news
                })

            except Exception as e:
                st.error(f"問答失敗：{e}")
