import { useState } from 'preact/hooks';

/** Text input that keeps its own draft while focused, so 5 Hz re-renders never clobber typing. */
export function DraftInput(props: {
  value: string;
  onCommit: (text: string) => void;
  onEnterUnchanged?: () => void;
  class?: string;
  placeholder?: string;
  title?: string;
  field?: string;
  width?: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = (text: string) => {
    setDraft(null);
    if (text.trim() !== props.value) props.onCommit(text.trim());
  };
  return (
    <input
      class={props.class}
      data-field={props.field}
      style={props.width ? { width: props.width } : undefined}
      value={draft ?? props.value}
      placeholder={props.placeholder}
      title={props.title}
      onFocus={() => setDraft(props.value)}
      onInput={(e) => setDraft((e.currentTarget as HTMLInputElement).value)}
      onBlur={(e) => commit((e.currentTarget as HTMLInputElement).value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          const el = e.currentTarget as HTMLInputElement;
          if (el.value.trim() === props.value) props.onEnterUnchanged?.();
          else commit(el.value);
          setDraft(el.value.trim());
        } else if (e.key === 'Escape') {
          setDraft(null);
          (e.currentTarget as HTMLInputElement).blur();
        }
      }}
    />
  );
}
