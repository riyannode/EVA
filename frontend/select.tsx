import { createPortal } from "react-dom";
import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";

export type SelectOption = { value: string; label: ReactNode; disabled?: boolean };
type SelectProps = {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: ReactNode;
  disabled?: boolean;
  className?: string;
};

export default function Select({ value, options, onChange, ariaLabel, placeholder = "Select an option", disabled = false, className = "" }: SelectProps) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>();
  const id = useId().replaceAll(":", "");
  const listboxId = `eva-select-${id}`;
  const selectedIndex = options.findIndex(option => option.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  function enabledIndex(start: number, direction: 1 | -1) {
    if (!options.length) return -1;
    for (let offset = 0; offset < options.length; offset += 1) {
      const index = (start + direction * offset + options.length * 2) % options.length;
      if (!options[index].disabled) return index;
    }
    return -1;
  }

  function openMenu() {
    if (disabled) return;
    setActiveIndex(selectedIndex >= 0 && !options[selectedIndex].disabled ? selectedIndex : enabledIndex(0, 1));
    setOpen(true);
  }

  function closeMenu() {
    setOpen(false);
    setActiveIndex(-1);
  }

  function choose(option: SelectOption) {
    if (option.disabled) return;
    onChange(option.value);
    closeMenu();
    trigger.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "Escape") {
      if (!open) return;
      event.preventDefault();
      closeMenu();
      return;
    }
    if (event.key === "Tab") {
      closeMenu();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      if (!open) {
        openMenu();
        return;
      }
      setActiveIndex(enabledIndex((activeIndex >= 0 ? activeIndex : selectedIndex) + direction, direction));
      return;
    }
    if (open && (event.key === "Home" || event.key === "End")) {
      event.preventDefault();
      const direction = event.key === "Home" ? 1 : -1;
      setActiveIndex(enabledIndex(direction === 1 ? 0 : options.length - 1, direction));
      return;
    }
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      event.preventDefault();
      if (!open) {
        openMenu();
      } else if (activeIndex >= 0) {
        choose(options[activeIndex]);
      }
    }
  }

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (!root.current?.contains(target) && !menu.current?.contains(target)) closeMenu();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function updatePosition() {
      const bounds = trigger.current?.getBoundingClientRect();
      if (!bounds) return;
      const menuHeight = Math.min(260, options.length * 42 + 10);
      const openUp = bounds.bottom + 6 + menuHeight > window.innerHeight && bounds.top - 6 - menuHeight >= 0;
      setMenuStyle({ left: bounds.left, top: openUp ? bounds.top - menuHeight - 6 : bounds.bottom + 6, width: bounds.width });
    }
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, options.length]);

  const portalTarget = root.current?.closest("dialog") ?? (typeof document !== "undefined" ? document.body : null);
  const content = open && portalTarget ? createPortal(
    <div ref={menu} id={listboxId} className="eva-select-content" role="listbox" aria-label={ariaLabel} style={{ ...menuStyle, visibility: menuStyle ? "visible" : "hidden" }}>
      {options.map((option, index) => <button key={option.value} type="button" role="option" id={`${listboxId}-${index}`} aria-selected={option.value === value} disabled={option.disabled} data-active={index === activeIndex} className="eva-select-option" onMouseDown={event => event.preventDefault()} onMouseEnter={() => !option.disabled && setActiveIndex(index)} onClick={() => choose(option)}>{option.label}</button>)}
    </div>, portalTarget,
  ) : null;

  return <div ref={root} className={`eva-select ${className}`.trim()} data-open={open}>
    <button ref={trigger} type="button" role="combobox" className="eva-select-trigger" aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} aria-controls={listboxId} disabled={disabled} onClick={() => open ? closeMenu() : openMenu()} onKeyDown={handleKeyDown}>
      <span className="eva-select-value" data-placeholder={!selected}>{selected?.label ?? placeholder}</span>
    </button>
    {content}
  </div>;
}
