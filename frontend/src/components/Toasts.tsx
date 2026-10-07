"use client";

import type { Toast } from "@/hooks/useEventra";

const TONE: Record<Toast["kind"], string> = {
  ok: "border-l-bull",
  warn: "border-l-warn",
  err: "border-l-bear",
};

export default function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[99] flex flex-col items-end gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`max-w-[380px] animate-slideIn rounded-md border border-edge-bright border-l-[3px] bg-[#0d1520] px-3 py-2 text-[11.5px] shadow-[0_10px_30px_rgba(0,0,0,0.5)] ${TONE[toast.kind]}`}
        >
          {toast.message}
        </div>
      ))}
    </div>
  );
}
