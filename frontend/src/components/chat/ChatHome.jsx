// The empty chat: a greeting, the big message box and a few things to try.
import { Copy, FolderSearch, HardDrive, History } from "lucide-react";

import Composer from "./Composer.jsx";

export const PROMPTS = [
  { icon: FolderSearch, text: "Scan ~/Downloads and tell me what to clean up" },
  { icon: Copy, text: "Do I have duplicate files I can safely remove?" },
  { icon: HardDrive, text: "Which files are using the most space?" },
  { icon: History, text: "What did I work on recently?" },
];

export default function ChatHome({ onSend, disabled }) {
  return (
    <div className="chat-home">
      <h2 className="chat-home__title">What should we tidy up today?</h2>
      <Composer variant="hero" onSend={onSend} disabled={disabled} autoFocus />
      <ul className="chat-home__prompts">
        {PROMPTS.map(({ icon: Icon, text }) => (
          <li key={text}>
            <button type="button" className="chat-home__prompt" disabled={disabled} onClick={() => onSend(text)}>
              <Icon size={16} aria-hidden="true" /> {text}
            </button>
          </li>
        ))}
      </ul>
      <p className="chat-home__note">Runs on this computer. Steward asks before it changes any file.</p>
    </div>
  );
}
