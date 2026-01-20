import express from "express";
import { handleUpdate } from "./bot.js";

const app = express();
app.use(express.json());

app.post("/webhook", async (req, res) => {
  try {
    await handleUpdate(req.body);
    res.send("OK");
  } catch (e) {
    console.error(e);
    res.sendStatus(500);
  }
});

app.get("/", (_, res) => res.send("Bot is running"));

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log("Listening on", PORT);
});
