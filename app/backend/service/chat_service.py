from app.backend.logger import logger

class ChatService:


    async def astream_chat(self, message, thread_id):
        logger.info(f"聊天请求: {message}")
