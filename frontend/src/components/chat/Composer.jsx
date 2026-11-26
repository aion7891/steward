// The message box: grows with the text, Enter sends, Shift+Enter adds a new line.
import { SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import Button from "../ui/Button.jsx";

const MAX_LENGTH = 2000;

export default function Composer({ onSend, disabled }) {
  const [text, setText] = useState("");
  const boxRef = useRef(null);

  // Grow the textarea up to about 8 lines, then scroll inside it
  useEffect(() => {
    const box = boxRef.current;
    if (box) {
      box.style.height = "auto";
      box.style.height = `${Math.min(box.scrollHeight, 200)}px`;
    }
  }, [text]);

  function submit() {
    const message = text.trim();
    if (!message || disabled) {
      return;
    }
    onSend(message);
    setText("");
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form className="chat-composer" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <textarea
        ref={boxRef}
        className="chat-composer__input"
        rows={1}
        maxLength={MAX_LENGTH}
        placeholder={disabled ? "Waiting for the answer…" : "Ask about your files…  (Enter to send, Shift+Enter for a new line)"}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-label="Message"
      />
      <Button type="submit" variant="primary" icon={SendHorizontal} disabled={disabled || !text.trim()}>
        Send
      </Button>
    </form>
  );
}
