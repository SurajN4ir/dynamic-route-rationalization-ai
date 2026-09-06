type Tone = "ok" | "unavailable" | "unknown";

const TONE_CLASSES: Record<Tone, string> = {
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  unavailable: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  unknown: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};

function toneFor(status: string | undefined): Tone {
  if (status === "ok") return "ok";
  if (status === "unavailable") return "unavailable";
  return "unknown";
}

export function StatusBadge({ status }: { status: string | undefined }) {
  const tone = toneFor(status);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
    >
      {status ?? "unknown"}
    </span>
  );
}
