// The message box: grows with the text, Enter sends, Shift+Enter adds a new line.
// The "hero" variant is the big centred box on the empty chat page. While Steward works,
// the send button becomes a Stop button (when onStop is given).
import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX_LENGTH = 2000;

export default function Composer({ onSend, disabled, onStop, stopping = false, variant = "dock", autoFocus = false }) {
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
      {disabled && onStop ? (
        <button type="button" className="composer__send composer__send--stop" onClick={onStop} disabled={stopping}
          aria-label={stopping ? "Stopping" : "Stop the answer"} title={stopping ? "Stopping…" : "Stop"}>
          <Square size={14} aria-hidden="true" fill="currentColor" />
        </button>
      ) : (
        <button type="submit" className="composer__send" disabled={disabled || !text.trim()} aria-label="Send">
          <ArrowUp size={18} aria-hidden="true" />
        </button>
      )}
    </form>
  );
}
