import { FormEvent, useState } from 'react';

interface Props {
  onSubmit: (url: string) => void;
  disabled?: boolean;
  initial?: string;
  compact?: boolean;
}

export function URLInput({ onSubmit, disabled, initial = '', compact = false }: Props) {
  const [value, setValue] = useState(initial);

  function handle(e: FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    onSubmit(value.trim());
  }

  return (
    <form onSubmit={handle} className="w-full max-w-2xl mx-auto">
      <div
        className={`paper-card flex items-stretch overflow-hidden transition-colors focus-within:border-ink-700 ${
          compact ? 'text-base' : 'text-lg'
        }`}
      >
        <div
          className={`pl-5 flex items-center text-ink-400 font-mono select-none ${
            compact ? 'text-xs' : 'text-sm'
          }`}
        >
          https://
        </div>
        <input
          type="text"
          placeholder="your-site.com"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          className={`flex-1 bg-transparent px-3 text-ink-900 placeholder-ink-300 focus:outline-none ${
            compact ? 'py-3' : 'py-5'
          }`}
          autoFocus
          spellCheck={false}
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className={`bg-ink-900 text-paper font-medium font-display tracking-tightish disabled:opacity-30 disabled:cursor-not-allowed hover:bg-terra-deep transition ${
            compact ? 'px-5 text-sm' : 'px-7 text-base'
          }`}
        >
          {disabled ? 'Scanning…' : 'Score it'}
        </button>
      </div>
    </form>
  );
}
