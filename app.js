const chatWindow = document.getElementById("chatWindow");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");

function addMessage(text, role) {
  const messageCard = document.createElement("article");
  messageCard.className = `message ${role}`;

  const meta = document.createElement("span");
  meta.className = "message-meta";
  meta.textContent = role === "user" ? "أنت" : "الوكيل";

  const content = document.createElement("div");
  content.textContent = text;

  messageCard.appendChild(meta);
  messageCard.appendChild(content);
  chatWindow.appendChild(messageCard);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function sendMessage(message) {
  const endpoint = "/ask";
  const payload = { message };

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`خطأ في الاتصال: ${response.status}`);
    }

    const result = await response.json();
    const answer = result.reply || result.response || "تعذر الحصول على رد من الخادم.";
    addMessage(answer, "agent");
  } catch (error) {
    addMessage(`حدث خطأ: ${error.message}`, "agent");
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;

  addMessage(text, "user");
  messageInput.value = "";
  messageInput.focus();

  chatForm.querySelector("button").disabled = true;
  await sendMessage(text);
  chatForm.querySelector("button").disabled = false;
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});
