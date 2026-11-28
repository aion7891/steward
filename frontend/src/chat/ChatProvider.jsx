// Keeps the chat (messages, the running answer and its live steps) above all pages,
// so switching tabs or reloading never loses an answer. The server holds the conversation;
// the browser copy is only a fallback while the server can't be reached.
import { createContext, useContext, useEffect, useState } from "react";

import {
  decideChatJob, deleteConversation, getChatJob, getConversation, listConversations, startChatJob, stopChatJob,
} from "../api/steward.js";
import {
  interruptedMessage, jobResultToMessage, jobState, markTypedDecision, POLL_MS, serverMessagesToChat,
} from "../utils/chatJobs.js";
import { loadMessages, loadSessionId, newSessionId, saveMessages, saveSessionId } from "../utils/chatStorage.js";

const ChatContext = createContext(null);

/** Use the shared chat state inside any page or component. */
export function useChat() {
  return useContext(ChatContext);
}

function userMessage(text) {
  return { id: `u-${Date.now()}`, role: "user", content: text, createdAt: new Date().toISOString() };
}

export function ChatProvider({ children }) {
  const [sessionId, setSessionId] = useState(() => loadSessionId());
  const [messages, setMessages] = useState(() => loadMessages());
  const [job, setJob] = useState(null);
  const [conversations, setConversations] = useState([]);
  const busy = job !== null;

  useEffect(() => saveMessages(messages), [messages]);

  const refreshConversations = () =>
    listConversations(12).then((data) => setConversations(data.conversations || [])).catch(() => {});

  // Recent chats for the sidebar: refreshed when an answer finishes or another chat opens
  useEffect(() => { refreshConversations(); }, [busy, sessionId]);

  // While another chat is still answering in the background, keep its "working" dot up to date
  useEffect(() => {
    if (!conversations.some((c) => c.running)) return undefined;
    const timer = setTimeout(refreshConversations, 3000);
    return () => clearTimeout(timer);
  }, [conversations]);

  // Load the server's copy of the conversation and pick up an answer that is still running
  useEffect(() => {
    let cancelled = false;
    getConversation(sessionId)
      .then((data) => {
        if (cancelled) return;
        // The server's copy wins, also when it is empty (for example after chats were cleared in Settings)
        if (Array.isArray(data.messages)) setMessages(serverMessagesToChat(data.messages));
        if (data.active_job) setJob(jobState(data.active_job));
      })
      .catch(() => {});  // offline: keep the browser copy
    return () => { cancelled = true; };
  }, [sessionId]);

  // Check the running job every second until its answer is ready
  useEffect(() => {
    if (!job) return undefined;
    let stopped = false;
    const timer = setTimeout(async () => {
      try {
        const data = await getChatJob(job.id);
        if (stopped) return;
        if (data.job.status === "done") {
          setMessages((list) => [...markTypedDecision(list, data.job.result), jobResultToMessage(data.job.result)]);
          setJob(null);
        } else {
          setJob((current) => current && { ...current, status: data.job.status, steps: data.job.steps,
            thinking: data.job.thinking, stopping: current.stopping || data.job.stopping, failures: 0 });
        }
      } catch (error) {
        if (stopped) return;
        if (error.status === 404) {
          setMessages((list) => [...list, interruptedMessage(error.message)]);
          setJob(null);
        } else {
          setJob((current) => current && { ...current, failures: current.failures + 1 });  // keep trying
        }
      }
    }, POLL_MS);
    return () => { stopped = true; clearTimeout(timer); };
  }, [job]);

  async function start(call) {
    try {
      const data = await call();
      setJob(jobState(data.job));
    } catch (error) {
      setMessages((list) => [...list, jobResultToMessage({ status: "error", reply: error.message })]);
    }
  }

  function ask(text) {
    setMessages((list) => [...list, userMessage(text)]);
    start(() => startChatJob(text, sessionId));
  }

  function decide(message, approve) {
    setMessages((list) => list.map((m) => (m.id === message.id ? { ...m, decision: approve ? "approved" : "rejected" } : m)));
    start(() => decideChatJob(message.runId, approve, sessionId));
  }

  // Ask the server to stop the running answer; the next poll brings the "Stopped" message
  async function stop() {
    if (!job || job.stopping) return;
    setJob((current) => current && { ...current, stopping: true });
    try {
      await stopChatJob(job.id);
    } catch {
      setJob((current) => current && { ...current, stopping: false });  // let the user try again
    }
  }

  function retry() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) {
      setMessages((list) => list.slice(0, list.lastIndexOf(lastUser)));
      ask(lastUser.content);
    }
  }

  // Each chat has its own running answer: leaving a chat stops watching its answer here (the server
  // keeps working on it, and opening that chat again picks it up)
  function newChat() {
    setJob(null);
    setMessages([]);
    setSessionId(newSessionId());
  }

  function openChat(id) {
    setJob(null);
    setMessages([]);
    setSessionId(saveSessionId(id));
  }

  async function deleteChat(id) {
    await deleteConversation(id);  // the server refuses while that chat is still answering
    if (id === sessionId) newChat();
    refreshConversations();
  }

  const value = { sessionId, messages, job, busy, conversations, ask, decide, stop, retry, newChat, openChat, deleteChat };
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}
