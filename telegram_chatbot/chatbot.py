from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from chatbot_rag import rag_query
from chatbot_utils import save_message
from openai import OpenAI
from dotenv import load_dotenv
import os
load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

client = OpenAI(
        api_key=OPENAI_KEY
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am your personal Property Assistant. How can I help you find a home today?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_query = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_query.lower() in ['hai', 'hi', 'p', 'test', 'start', 'halo', 'halooo', 'haloo', 'haii', 'hii'] or len(user_query) <= 5:
        bot_response = "Hi, ada yang bisa saya bantu?"
    
    elif 'makasi' in user_query.lower() or 'thank' in user_query.lower() or 'suwun' in user_query.lower():
        bot_response = "Siap, sama-sama! Kalau ada pertanyaan lain atau butuh info lebih lanjut, jangan ragu buat tanya ya!"

    else:
        # save user message
        save_message(user_id=user_id, chat_id=chat_id, role='user', message=user_query)

        bot_response = rag_query(
            {
                "question": user_query,
                "chat_id" : chat_id
            }
        )

        # save bot response
        save_message(user_id=user_id, chat_id=chat_id, role='bot', message=bot_response)
    await update.message.reply_text(bot_response)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is polling...")
    app.run_polling()

if __name__ == "__main__":
    main()