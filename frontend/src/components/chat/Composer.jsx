// The message box: grows with the text, Enter sends, Shift+Enter adds a new line.
// The "hero" variant is the big centred box on the empty chat page.
import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX_LENGTH = 2000;

export default function Composer({ onSend, disabled, variant = "dock", autoFocus = false }) {
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
    <form className={`composer composer--${variant}`} onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <textarea
        ref={boxRef}
        className="composer__input"
        rows={1}
        maxLength={MAX_LENGTH}
        autoFocus={autoFocus}
        placeholder={disabled ? "Waiting for the answer…" : "Ask Steward, or paste a folder path…"}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-label="Message"
      />
      <button type="submit" className="composer__send" disabled={disabled || !text.trim()} aria-label="Send">
        <ArrowUp size={18} aria-hidden="true" />
      </button>
    </form>
  );
}
