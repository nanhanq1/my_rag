from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from app.backend.config import settings
from app.backend.logger import logger

SYSTEM_PROMPT1 = """你是一个专业的企业知识库助手。"""

SYSTEM_PROMPT = """你是一个专业的企业知识库助手。回答企业知识类问题时，必须严格基于消息中提供的“企业知识库上下文”。
核心规则：
1. 回答企业知识类问题时，除非用户明确要求，否则绝对不能使用知识库上下文以外的知识回答。
2. 如果用户没有明确要求使用知识库以外的知识回答，且知识库上下文中完全没有相关信息，必须准确回复："知识库中没有找到与您的问题相关的内容。"
3. 回答要准确、简洁、专业。
4. 如果知识库上下文存在矛盾，请指出并说明。
5. 回答使用中文。
6. 如果用户的输入，明显不是提问，或明显没有从企业知识库检索内容的意图，或明显和企业知识库的内容无关时，可忽略知识库上下文，直接回答。比如：用户输入“你好”，可忽略知识库上下文，直接回答。
7. 如果对用户输入的内容意图不明显，可向用户提问，确认是否要从企业知识库检查数据。
8. 当用户的问题是关于本次对话本身的（例如“我的上一个问题是什么”“你刚才说了什么”“总结一下我们的对话”），应基于对话历史消息回答，此类问题不受“必须基于知识库”的限制，也不要回复“知识库中没有找到”。注意：发给你的用户消息可能形如“企业知识库上下文：……\n\n用户问题：XXX”，其中“用户问题：”后面的 XXX 才是用户真正问的内容，识别历史问题时应以此为准。
9. 你的回答必须是纯文本，不要返回 markdown 或 HTML 标签（不要使用 <br>、<strong> 等）。需要换行时直接换行即可。
10. 不要使用 markdown 的双星号加粗、列表符号“-”、表格等格式；列举内容时用“1、2、3、”编号，每项单独一行。"""

class ChatService:

    def __init__(self, vector_service):
       self.vector_service = vector_service
       # 大语言模型对象
       self.model = ChatOpenAI(
           model=settings.openai_model_name,
           base_url=settings.openai_base_url,
           api_key=settings.openai_api_key
       )

       # 会话记忆检查点，会话记忆
       self.checkpointer = InMemorySaver()

       # Agent
       self.agent = create_agent(
           model=self.model,
           tools=[],
           checkpointer=self.checkpointer,
           system_prompt=SYSTEM_PROMPT
       )


    async def astream_chat(self, message, thread_id):
        logger.info(f"聊天请求: {message}")
        agent_config = {"configurable": {"thread_id": thread_id}}

        context, sources = await self.vector_service.asearch(message)
        user_input = f"以下是从企业知识库检索到的上下文：\n{context}\n\n用户问题：{message}"
        # 如果检索到相关内容，先发sources给前端
        if sources:
            yield {"sources": sources}

        # 流式生成问答
        async for msg, _meta in self.agent.astream(
      {"messages": [{"role": "user", "content": user_input}]},
            agent_config,
            stream_mode="messages"
        ):
            logger.info(f"{msg=}")
            content = getattr(msg, "content", None)
            if not content:
                continue
            yield {"content": content}




