import {useEffect, useRef, useState} from "react";

export interface ProviderMenuOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface Props {
  value: string;
  options: ProviderMenuOption[];
  placeholder: string;
  onChange: (value: string) => void;
  compact?: boolean;
  "aria-label"?: string;
}

/** 自定义下拉（避免 Windows 原生 select 白底浅字看不见） */
export function ProviderMenu({value, options, placeholder, onChange, compact, "aria-label": ariaLabel}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const current = options.find((o) => o.value === value);

  return (
    <div
      ref={rootRef}
      className={`fs-provider-menu${compact ? " fs-provider-menu--compact" : ""}${open ? " is-open" : ""}`}
    >
      <button
        type="button"
        className="fs-provider-menu-btn"
        aria-label={ariaLabel}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="fs-provider-menu-value">{current?.label ?? placeholder}</span>
        <span className="fs-provider-menu-chevron" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <ul className="fs-provider-menu-list" role="listbox">
          {options.map((o) => (
            <li key={o.value || "__empty"} role="option" aria-selected={o.value === value}>
              <button
                type="button"
                className={`fs-provider-menu-item${o.value === value ? " is-active" : ""}${o.disabled ? " is-disabled" : ""}`}
                disabled={o.disabled}
                onClick={() => {
                  if (o.disabled) return;
                  onChange(o.value);
                  setOpen(false);
                }}
              >
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
