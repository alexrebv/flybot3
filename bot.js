import { sendMessage } from "./telegram.js";

export async function handleUpdate(update) {
  const msg = update.message || update.callback_query?.message;
  if (!msg) return;

  const chatId = msg.chat.id;
  const text = update.message?.text || update.callback_query?.data;

  if (text === "/start") {
    await sendMessage(chatId, "Бот запущен на fly.io 🚀");
  }
}
