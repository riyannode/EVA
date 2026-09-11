import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

type ScrollAreaProps = { children: ReactNode; className?: string };
type DragState = { pointerId: number; startY: number; startScrollTop: number; maxScroll: number; maxOffset: number };

export default function ScrollArea({ children, className = "" }: ScrollAreaProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const [thumb, setThumb] = useState<{ size: number; offset: number } | null>(null);
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const sync = () => {
      const maxScroll = viewport.scrollHeight - viewport.clientHeight;
      if (maxScroll <= 0) { setThumb(null); return; }
      const size = Math.max(viewport.clientHeight * viewport.clientHeight / viewport.scrollHeight, 24);
      setThumb({ size, offset: viewport.scrollTop / maxScroll * (viewport.clientHeight - size) });
    };
    sync();
    viewport.addEventListener("scroll", sync, { passive: true });
    const observer = new ResizeObserver(sync);
    observer.observe(viewport);
    return () => { viewport.removeEventListener("scroll", sync); observer.disconnect(); };
  }, [children]);
  function startDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const viewport = viewportRef.current;
    const scrollbar = event.currentTarget.parentElement;
    if (!viewport || !scrollbar) return;
    const maxScroll = viewport.scrollHeight - viewport.clientHeight;
    const maxOffset = scrollbar.clientHeight - event.currentTarget.offsetHeight;
    if (maxScroll <= 0 || maxOffset <= 0) return;
    dragRef.current = { pointerId: event.pointerId, startY: event.clientY, startScrollTop: viewport.scrollTop, maxScroll, maxOffset };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }
  function moveDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    const viewport = viewportRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !viewport) return;
    const next = drag.startScrollTop + (event.clientY - drag.startY) * drag.maxScroll / drag.maxOffset;
    viewport.scrollTop = Math.min(drag.maxScroll, Math.max(0, next));
  }
  function endDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  }
  return <div className={`scroll-area ${className}`.trim()}><div className="scroll-area-viewport" ref={viewportRef}>{children}</div>{thumb && <div className="scroll-area-scrollbar" aria-hidden="true"><div className="scroll-area-thumb" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag} onLostPointerCapture={endDrag} style={{ height: thumb.size, transform: `translateY(${thumb.offset}px)` }} /></div>}</div>;
}
