// Example questions shown while the conversation is empty.
import { MessageSquare } from "lucide-react";

export const PROMPTS = [
  "What did I work on recently?",
  "Which files are using the most space?",
  "Do I have duplicate files I can safely remove?",
  "Summarize the documents in my Acme folder.",
];

export default function SuggestedPrompts({ onPick }) {
  return (
    <div className="chat-empty">
      <div className="empty__icon"><MessageSquare size={20} aria-hidden="true" /></div>
      <div className="empty__title">Ask Steward about your files</div>
      <p className="faint">Answers come from your local knowledge notes and document search, with the source files listed.</p>
      <div className="chat-prompts">
        {PROMPTS.map((prompt) => (
          <button key={prompt} type="button" className="chat-prompt" onClick={() => onPick(prompt)}>
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
